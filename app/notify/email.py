"""The email channel kind: notifications through the admin's SMTP relay.

config: host, port (587), starttls (true), username (optional), from_address
and to (1 to 20 addresses). The relay password is the channel's secret,
Fernet-encrypted in channel.secret_enc and never returned (D-6); a channel
with a user name needs one. Changing the host, port, STARTTLS or user name
needs the password again, so a stored password never goes to a new server.

smtplib blocks, so a delivery runs in a thread with SMTP_TIMEOUT seconds for
every network step and SESSION_LIMIT for all of them. Once the relay accepted
the message, the delivery counts as done whatever QUIT answers. With starttls
the relay must offer STARTTLS and present a certificate the system trusts;
the login happens only after it. The relay is not checked by the SSRF guard:
MSPs often send through an internal relay and only an admin can set it
(docs/security.md). Errors become one sentence for the notification history,
never the password or the relay's own words.
"""

import asyncio
import ipaddress
import re
import smtplib
import socket
import ssl
import time
from collections.abc import Collection, Mapping
from email.message import EmailMessage
from email.utils import formatdate, make_msgid
from typing import Any, Final

from app.ext.notifications import (
    ChannelConfigError,
    DeliveryError,
    Message,
    Outbound,
)
from app.repos.users import normalise_email
from app.settings import MAIL_DOMAIN_PATTERN

DEFAULT_PORT: Final = 587
MAX_RECIPIENTS: Final = 20
MAX_HOST_LENGTH: Final = 253
MAX_USERNAME_LENGTH: Final = 320
MAX_SUBJECT_LENGTH: Final = 200
# Seconds for the connection and for every SMTP command, and for the whole
# session: less than SEND_TIMEOUT (app/notify/delivery.py), so the thread
# has ended when the dispatcher records the attempt.
SMTP_TIMEOUT: Final = 20.0
SESSION_LIMIT: Final = 75.0
_HOST = re.compile(MAIL_DOMAIN_PATTERN)
KEYS: Final = frozenset({"host", "port", "starttls", "username", "from_address", "to"})
# Characters a plain address does not need and an address header reads as
# structure (RFC 5322 specials, without @ and the dot).
ADDRESS_SPECIALS: Final = frozenset('<>,;:"()[]\\')


def one_line(value: str) -> str:
    """Every run of white space (line breaks included) becomes one space."""
    return " ".join(value.split())


def _host(value: Any) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ChannelConfigError("host", "Set the relay's host name or address.")
    host = value.strip().lower().rstrip(".")
    try:
        ipaddress.ip_address(host)
    except ValueError:
        if len(host) > MAX_HOST_LENGTH or not _HOST.fullmatch(host):
            raise ChannelConfigError(
                "host", "Use a host name such as smtp.example.com or an address."
            ) from None
    return host


def _port(value: Any) -> int:
    if value is None:
        return DEFAULT_PORT
    if isinstance(value, bool) or not isinstance(value, int) or not 1 <= value <= 65535:
        raise ChannelConfigError("port", "Use a port from 1 to 65535.")
    return value


def _flag(name: str, value: Any, default: bool) -> bool:
    if value is None:
        return default
    if not isinstance(value, bool):
        raise ChannelConfigError(name, "Use true or false.")
    return value


def _address(name: str, value: Any) -> str:
    """One plain address: no display name, list separator, quote or control
    character, so one entry is one recipient."""
    if not isinstance(value, str):
        raise ChannelConfigError(name, "Use an e-mail address.")
    try:
        address = normalise_email(value)
    except ValueError:
        raise ChannelConfigError(name, "Use an e-mail address.") from None
    if any(c in ADDRESS_SPECIALS or ord(c) < 32 or ord(c) == 127 for c in address):
        raise ChannelConfigError(name, "Use one plain address such as ops@example.com.")
    return address


def _recipients(value: Any) -> list[str]:
    if not isinstance(value, list) or not value:
        raise ChannelConfigError("to", "Add at least one recipient address.")
    if len(value) > MAX_RECIPIENTS:
        raise ChannelConfigError("to", f"Use at most {MAX_RECIPIENTS} recipients.")
    found: list[str] = []
    for item in value:
        address = _address("to", item)
        if address not in found:
            found.append(address)
    return found


def _username(value: Any) -> str | None:
    if value is None:
        return None
    if not isinstance(value, str) or len(value) > MAX_USERNAME_LENGTH:
        raise ChannelConfigError(
            "username", f"Use a user name of at most {MAX_USERNAME_LENGTH} characters."
        )
    name = value.strip()
    if any(ord(character) < 32 or ord(character) == 127 for character in name):
        raise ChannelConfigError("username", "Remove the control characters.")
    return name or None


def build_message(config: Mapping[str, Any], message: Message) -> EmailMessage:
    """The e-mail of a notification. Header values are single lines, so a
    name with a line break cannot add a header."""
    sender = str(config["from_address"])
    email = EmailMessage()
    email["Subject"] = one_line(message.subject)[:MAX_SUBJECT_LENGTH]
    email["From"] = sender
    email["To"] = ", ".join(config["to"])
    email["Date"] = formatdate(usegmt=True)
    email["Message-ID"] = make_msgid(domain=sender.rsplit("@", 1)[1])
    email["Auto-Submitted"] = "auto-generated"
    email.set_content(message.text)
    if message.html is not None:
        email.add_alternative(message.html, subtype="html")
    return email


class EmailKind:
    """The CE channel kind email."""

    name = "email"
    secret_label = "Relay password"
    secret_targets: Collection[str] = frozenset(
        {"host", "port", "starttls", "username"}
    )

    def check_config(
        self, config: Mapping[str, Any], *, has_secret: bool
    ) -> dict[str, Any]:
        unknown = sorted(set(config) - KEYS)
        if unknown:
            raise ChannelConfigError(unknown[0], "Unknown setting.")
        username = _username(config.get("username"))
        if username is not None and not has_secret:
            raise ChannelConfigError(
                "secret", "Set the relay password for this user name."
            )
        if "from_address" not in config:
            raise ChannelConfigError("from_address", "Set the sender address.")
        return {
            "host": _host(config.get("host")),
            "port": _port(config.get("port")),
            "starttls": _flag("starttls", config.get("starttls"), True),
            "username": username,
            "from_address": _address("from_address", config["from_address"]),
            "to": _recipients(config.get("to")),
        }

    async def send(
        self,
        config: Mapping[str, Any],
        secret: str | None,
        message: Message,
        outbound: Outbound,
    ) -> None:
        email = build_message(config, message)
        await asyncio.to_thread(deliver, config, secret, email)


def login(session: smtplib.SMTP, username: str, password: str) -> None:
    """Log in to the relay. smtplib tries the next mechanism after a refusal,
    and many relays hang up on that second try: a relay that closes the
    connection during the login refused it."""
    try:
        session.login(username, password)
    except smtplib.SMTPServerDisconnected:
        raise DeliveryError("The relay refused the user name or password.") from None


def bound(session: smtplib.SMTP, deadline: float) -> None:
    """Give the next SMTP step the time left of the session, SMTP_TIMEOUT
    at most; DeliveryError when none is left."""
    left = deadline - time.monotonic()
    if left <= 0:
        raise DeliveryError(
            f"The relay took longer than {SESSION_LIMIT:.0f} seconds in all."
        )
    if session.sock is not None:
        session.sock.settimeout(min(SMTP_TIMEOUT, left))


def close(session: smtplib.SMTP, *, sent: bool) -> None:
    """End the session. After the relay accepted the message, a bad answer
    to QUIT or a dropped connection changes nothing (it is not sent again);
    after a failure the connection is only closed."""
    if sent:
        try:
            session.quit()
            return
        except (smtplib.SMTPException, OSError):
            pass
    session.close()


def deliver(config: Mapping[str, Any], secret: str | None, email: EmailMessage) -> None:
    """Send one e-mail through the relay (blocking); DeliveryError on failure."""
    host = str(config["host"])
    port = int(config["port"])
    helo = str(config["from_address"]).rsplit("@", 1)[1]
    deadline = time.monotonic() + SESSION_LIMIT
    session: smtplib.SMTP | None = None
    sent = False
    try:
        session = smtplib.SMTP(host, port, local_hostname=helo, timeout=SMTP_TIMEOUT)
        bound(session, deadline)
        session.ehlo()
        if config["starttls"]:
            if not session.has_extn("starttls"):
                raise DeliveryError(
                    "The relay does not offer STARTTLS. Turn STARTTLS off "
                    "only for a relay on a trusted network."
                )
            bound(session, deadline)
            session.starttls(context=ssl.create_default_context())
            bound(session, deadline)
            session.ehlo()
        if config.get("username"):
            bound(session, deadline)
            login(session, str(config["username"]), secret or "")
        bound(session, deadline)
        session.send_message(email)
        sent = True
    except DeliveryError:
        raise
    except smtplib.SMTPAuthenticationError:
        raise DeliveryError("The relay refused the user name or password.") from None
    except smtplib.SMTPNotSupportedError:
        raise DeliveryError(
            "The relay does not accept a login; remove the user name."
        ) from None
    except smtplib.SMTPSenderRefused:
        raise DeliveryError("The relay refused the sender address.") from None
    except smtplib.SMTPRecipientsRefused:
        raise DeliveryError("The relay refused every recipient address.") from None
    except smtplib.SMTPServerDisconnected:
        raise DeliveryError("The relay closed the connection.") from None
    except smtplib.SMTPException as error:
        raise DeliveryError(
            f"The relay answered with an error ({type(error).__name__})."
        ) from None
    except ssl.SSLCertVerificationError:
        raise DeliveryError(
            "The relay's TLS certificate is not trusted by this server."
        ) from None
    except ssl.SSLError:
        raise DeliveryError("The TLS handshake with the relay failed.") from None
    except TimeoutError:
        raise DeliveryError(
            f"The relay did not answer within {SMTP_TIMEOUT:.0f} seconds."
        ) from None
    except ConnectionRefusedError:
        raise DeliveryError(
            f"The relay refused the connection on port {port}."
        ) from None
    except socket.gaierror:
        raise DeliveryError(f"The relay host {host} cannot be resolved.") from None
    except OSError as error:
        raise DeliveryError(
            f"The relay cannot be reached ({type(error).__name__})."
        ) from None
    finally:
        if session is not None:
            close(session, sent=sent)
