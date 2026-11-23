"""The slack, teams and webhook channel kinds (phase C9-I): one JSON body
POSTed to one admin-chosen URL.

The URL is the channel's credential: the admin sends it as config.url, the
API stores it as the channel secret (Fernet-encrypted, write-only) and the
stored config answers url_set and url_host only (docs/notifications.md).

Every request goes through check_target (app/security/ssrf.py) first: http
and https only, the host resolved, every address public unless the Outbound
rules allow it. The connection is then made to one of Target.addresses, not
to the name again, so a DNS answer cannot change between the check and the
request (rebinding); TLS still verifies and names target.host, and no
redirect is followed (a redirect to a private address is therefore never
reached). One request has REQUEST_TIMEOUT seconds in all, under the
90-second delivery limit (app/notify/delivery.py).

Errors are one readable sentence that names no secret and no part of the URL
after the host: the path may hold the webhook token.
"""

import asyncio
import json
import ssl
from collections.abc import Collection, Mapping
from typing import Any, Final
from urllib.parse import urlsplit

from app import PRODUCT_NAME, __version__
from app.ext.notifications import (
    ChannelConfigError,
    DeliveryError,
    Message,
    Outbound,
)
from app.notify.payloads import payload_of, slack_body, teams_body
from app.security.ssrf import SCHEMES, Target, TargetRefused, check_target

# Seconds for the whole request (connection, write, status line), after the
# guard's own DNS step of 5 seconds.
REQUEST_TIMEOUT: Final = 10.0
MAX_URL_LENGTH: Final = 2000
# The config keys seen in check_config: url is what the admin sends;
# url_set and url_host are the stored answer of a channel that has a URL.
INPUT_KEYS: Final = frozenset({"url"})
ANSWER_KEYS: Final = frozenset({"url_set", "url_host"})
USER_AGENT: Final = f"{PRODUCT_NAME}/{__version__}"


def host_of(url: str) -> str:
    """The host of a webhook URL, after checking the parts check_target also
    checks (scheme, user name, host); ChannelConfigError otherwise. Only the
    form: whether the host may be called is decided later, per request, by
    the SSRF guard."""
    text = url.strip()
    if len(text) > MAX_URL_LENGTH:
        raise ChannelConfigError(
            "url", f"Use a URL of at most {MAX_URL_LENGTH} characters."
        )
    if text.split() != [text]:
        raise ChannelConfigError(
            "url", "The URL may not contain spaces or control characters."
        )
    try:
        parts = urlsplit(text)
        port = parts.port
    except ValueError:
        raise ChannelConfigError("url", "The URL cannot be read.") from None
    if parts.scheme.lower() not in SCHEMES:
        raise ChannelConfigError(
            "url", "The URL must start with http:// or https://."
        )
    if parts.username is not None or parts.password is not None:
        raise ChannelConfigError(
            "url", "The URL may not carry a user name or password."
        )
    host = (parts.hostname or "").rstrip(".")
    if not host:
        raise ChannelConfigError("url", "The URL has no host.")
    if port is not None and not 1 <= port <= 65535:
        raise ChannelConfigError("url", "Use a port from 1 to 65535.")
    return host


def status_error(code: int) -> str:
    """Why an HTTP status is not a delivery."""
    if 300 <= code < 400:
        return f"The target answered {code} and redirects are not followed."
    return f"The target answered {code}."


def build_request(target: Target, url: str, body: bytes) -> bytes:
    """The HTTP/1.1 request as bytes: the path and query of the URL, the
    checked host in Host, no redirect followed, one JSON body."""
    parts = urlsplit(url)
    path = parts.path or "/"
    if parts.query:
        path = f"{path}?{parts.query}"
    default = 443 if target.scheme == "https" else 80
    if target.port == default:
        host_header = target.host
    else:
        host_header = f"{target.host}:{target.port}"
    head = (
        f"POST {path} HTTP/1.1\r\n"
        f"Host: {host_header}\r\n"
        "Content-Type: application/json\r\n"
        f"Content-Length: {len(body)}\r\n"
        f"User-Agent: {USER_AGENT}\r\n"
        "Accept: application/json\r\n"
        "Connection: close\r\n"
        "\r\n"
    )
    # A path or query with characters outside ASCII is refused rather than
    # mangled: the admin sees what the URL is.
    return head.encode("ascii") + body


async def exchange(address: str, target: Target, request: bytes) -> int:
    """One request to one checked address; the HTTP status code. The
    connection is made to the address while TLS still names and verifies
    target.host."""
    if target.scheme == "https":
        reader, writer = await asyncio.open_connection(
            address,
            target.port,
            ssl=ssl.create_default_context(),
            server_hostname=target.host,
        )
    else:
        reader, writer = await asyncio.open_connection(address, target.port)
    try:
        writer.write(request)
        await writer.drain()
        try:
            line = await reader.readline()
        except (EOFError, ValueError):
            raise DeliveryError("The target did not answer with HTTP.") from None
    finally:
        # close() starts the transport's close; the request is done once the
        # status line is read, and the server was told Connection: close.
        writer.close()
    parts = line.split(maxsplit=2)
    if (
        len(parts) < 2
        or not parts[0].startswith(b"HTTP/")
        or not parts[1].isdigit()
        or len(parts[1]) != 3
    ):
        raise DeliveryError("The target did not answer with HTTP.")
    return int(parts[1])


async def deliver(
    target: Target, url: str, body: bytes, *, timeout: float | None = None
) -> None:
    """POST the body to the URL at its checked target; DeliveryError when it
    did not arrive. The addresses are tried in order; a connection that
    fails moves to the next one, everything else ends the delivery. timeout
    defaults to REQUEST_TIMEOUT, read at call time (tests shrink it)."""
    seconds = REQUEST_TIMEOUT if timeout is None else timeout
    try:
        request = build_request(target, url, body)
    except UnicodeEncodeError:
        raise DeliveryError("The URL has characters this server cannot call.") from None
    unreachable: str | None = None
    refused_only = True
    code: int | None = None
    try:
        async with asyncio.timeout(seconds):
            for address in target.addresses:
                try:
                    code = await exchange(address, target, request)
                except ConnectionRefusedError:
                    unreachable = "ConnectionRefusedError"
                    continue
                except ssl.SSLCertVerificationError:
                    raise DeliveryError(
                        "The target's TLS certificate is not trusted by this server."
                    ) from None
                except ssl.SSLError:
                    raise DeliveryError(
                        "The TLS handshake with the target failed."
                    ) from None
                except OSError as error:
                    refused_only = False
                    unreachable = type(error).__name__
                    continue
                assert code is not None
                if 200 <= code < 300:
                    return
                raise DeliveryError(status_error(code))
    except TimeoutError:
        raise DeliveryError(
            f"The target did not answer within {seconds:.0f} seconds."
        ) from None
    if refused_only:
        raise DeliveryError(f"The target refused the connection on port {target.port}.")
    raise DeliveryError(f"The target cannot be reached ({unreachable}).")


class WebhookKind:
    """The webhook channel kind: the payload v1 as one JSON body
    (docs/webhook-payload.schema.json)."""

    name = "webhook"
    secret_label = "Webhook URL"
    # The URL is the secret and always arrives with its own value, so no
    # setting moves a stored secret to a new target.
    secret_targets: Collection[str] = frozenset()
    # The admin sends the URL in config.url; it is stored as the secret.
    url_key: str | None = "url"

    def body_of(self, message: Message) -> dict[str, Any]:
        return payload_of(message)

    def check_config(
        self, config: Mapping[str, Any], *, has_secret: bool
    ) -> dict[str, Any]:
        unknown = sorted(set(config) - INPUT_KEYS - ANSWER_KEYS)
        if unknown:
            raise ChannelConfigError(unknown[0], "Unknown setting.")
        url = config.get("url")
        if url is not None and not isinstance(url, str):
            raise ChannelConfigError("url", "Use the channel's URL as text.")
        if url is not None and url.strip():
            return {"url_set": True, "url_host": host_of(url)}
        if has_secret:
            # A URL is stored (the channel's secret): the stored answer keeps
            # saying so, whatever the request re-sent.
            host = config.get("url_host")
            return {
                "url_set": True,
                "url_host": host if isinstance(host, str) else None,
            }
        raise ChannelConfigError("url", "Set the channel's URL.")

    async def send(
        self,
        config: Mapping[str, Any],
        secret: str | None,
        message: Message,
        outbound: Outbound,
    ) -> None:
        if not secret:
            raise DeliveryError("The channel has no URL.")
        try:
            target = await check_target(
                secret,
                allow_private=outbound.allow_private,
                allowed_hosts=outbound.allowed_hosts,
            )
        except TargetRefused as error:
            raise DeliveryError(str(error)) from None
        body = json.dumps(self.body_of(message)).encode()
        await deliver(target, secret, body)


class SlackKind(WebhookKind):
    """The slack channel kind: the same facts as a Slack message (plain text
    plus a header and a few section blocks, every name escaped)."""

    name = "slack"
    secret_label = "Slack webhook URL"

    def body_of(self, message: Message) -> dict[str, Any]:
        return slack_body(message)


class TeamsKind(WebhookKind):
    """The teams channel kind: the same facts as a Teams message card (title,
    escaped text, the digest counts as sections)."""

    name = "teams"
    secret_label = "Teams webhook URL"

    def body_of(self, message: Message) -> dict[str, Any]:
        return teams_body(message)
