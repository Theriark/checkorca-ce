"""The email channel kind (app/notify/email.py): its settings, and delivery
through a capturing SMTP relay on 127.0.0.1 (aiosmtpd) with and without a
login. Every address is synthetic (legal R-11: example.com)."""

import email
import email.policy
import socket
from typing import Any

import pytest

from app.ext.notifications import ChannelConfigError, DeliveryError, Message, Outbound
from app.notify.email import EmailKind, build_message
from helpers import RelayCapture, smtp_relay

RELAY_USER = "alerts-relay"
# A secret-looking value that must never show in an error.
RELAY_PASSWORD = "Canary-relay-" + "p" * 16
LOGIN = (RELAY_USER, RELAY_PASSWORD)
BASE: dict[str, Any] = {
    "host": "127.0.0.1",
    "from_address": "checkorca@example.com",
    "to": ["ops@example.com"],
    "starttls": False,
}
NO_SENDER = {key: value for key, value in BASE.items() if key != "from_address"}


def message(**fields: Any) -> Message:
    values: dict[str, Any] = {
        "event": "missed",
        "subject": "Checkorca-CE: Fictional Dental Clinic / Nightly backup missed",
        "text": "Fictional Dental Clinic / Nightly backup missed its run.\n",
        "url": "http://localhost:8080/jobs/1",
    }
    return Message(**(values | fields))


def check(config: dict[str, Any], *, has_secret: bool = False) -> dict[str, Any]:
    return EmailKind().check_config(config, has_secret=has_secret)


def test_the_settings_get_their_defaults_and_normal_form() -> None:
    checked = check(
        {
            "host": " SMTP.Example.com. ",
            "from_address": " Checkorca@Example.com ",
            "to": ["OPS@example.com", "ops@example.com", "noc@example.com"],
        }
    )
    assert checked == {
        "host": "smtp.example.com",
        "port": 587,
        "starttls": True,
        "username": None,
        "from_address": "checkorca@example.com",
        "to": ["ops@example.com", "noc@example.com"],
    }
    assert check(BASE | {"host": "mock-platform", "port": 1025})["port"] == 1025
    assert check(BASE | {"host": "fd00::25"})["host"] == "fd00::25"
    login = check(BASE | {"username": " relay-user "}, has_secret=True)
    assert login["username"] == "relay-user"
    assert check(BASE | {"username": "  "})["username"] is None


@pytest.mark.parametrize(
    ("config", "field"),
    [
        ({**BASE, "bcc": "x@example.com"}, "bcc"),
        ({**BASE, "host": ""}, "host"),
        ({**BASE, "host": "smtp_example.com"}, "host"),
        ({**BASE, "host": 25}, "host"),
        ({**BASE, "port": 0}, "port"),
        ({**BASE, "port": "25"}, "port"),
        ({**BASE, "port": True}, "port"),
        ({**BASE, "starttls": "yes"}, "starttls"),
        ({**BASE, "to": []}, "to"),
        ({**BASE, "to": "ops@example.com"}, "to"),
        ({**BASE, "to": ["not an address"]}, "to"),
        ({**BASE, "to": [f"user{n}@example.com" for n in range(21)]}, "to"),
        (NO_SENDER, "from_address"),
        ({**BASE, "from_address": "nobody"}, "from_address"),
        ({**BASE, "username": "relay\nuser"}, "username"),
        ({**BASE, "username": 7}, "username"),
        ({**BASE, "username": "relay-user"}, "secret"),
    ],
)
def test_unusable_settings_name_their_field(config: dict[str, Any], field: str) -> None:
    with pytest.raises(ChannelConfigError) as refused:
        check(config)
    assert refused.value.field == field
    assert refused.value.message


def test_the_message_headers_are_single_lines() -> None:
    hostile = "Checkorca-CE: Evil\r\nBcc: victim@example.com\nX-Injected: yes"
    built = build_message(check(BASE), message(subject=hostile, html="<p>Hi</p>"))
    raw = built.as_bytes(policy=email.policy.SMTP)
    parsed = email.message_from_bytes(raw, policy=email.policy.default)
    assert parsed["Bcc"] is None and parsed["X-Injected"] is None
    flat = "Checkorca-CE: Evil Bcc: victim@example.com X-Injected: yes"
    assert parsed["Subject"] == flat
    assert parsed["To"] == "ops@example.com"
    assert parsed["Auto-Submitted"] == "auto-generated"
    assert parsed.get_content_type() == "multipart/alternative"


async def test_a_message_reaches_the_relay() -> None:
    capture = RelayCapture()
    async with smtp_relay(capture) as port:
        recipients = ["ops@example.com", "noc@example.com"]
        config = check(BASE | {"port": port, "to": recipients})
        await EmailKind().send(config, None, message(), Outbound())
    ((sender, received_by, raw),) = capture.messages
    assert sender == "checkorca@example.com"
    assert received_by == recipients
    parsed = email.message_from_bytes(raw, policy=email.policy.default)
    assert parsed["Subject"].startswith("Checkorca-CE: Fictional Dental Clinic")
    body = parsed.get_body(preferencelist=("plain",))
    assert body is not None and "missed its run" in body.get_content()


async def test_the_relay_login_uses_the_secret() -> None:
    capture = RelayCapture()
    kind = EmailKind()
    async with smtp_relay(capture, login=LOGIN) as port:
        config = check(BASE | {"port": port, "username": RELAY_USER}, has_secret=True)
        await kind.send(config, RELAY_PASSWORD, message(), Outbound())
        assert len(capture.messages) == 1
        with pytest.raises(DeliveryError) as refused:
            await kind.send(config, "wrong-" + RELAY_PASSWORD, message(), Outbound())
    assert refused.value.detail == "The relay refused the user name or password."
    assert RELAY_PASSWORD not in refused.value.detail
    assert len(capture.messages) == 1


async def test_a_login_the_relay_does_not_offer_is_explained() -> None:
    async with smtp_relay(RelayCapture()) as port:
        config = check(BASE | {"port": port, "username": RELAY_USER}, has_secret=True)
        with pytest.raises(DeliveryError, match="does not accept a login"):
            await EmailKind().send(config, RELAY_PASSWORD, message(), Outbound())


async def test_starttls_is_required_when_set() -> None:
    capture = RelayCapture()
    async with smtp_relay(capture) as port:
        config = check(BASE | {"port": port, "starttls": True})
        with pytest.raises(DeliveryError, match="does not offer STARTTLS"):
            await EmailKind().send(config, None, message(), Outbound())
    assert capture.messages == []


async def test_a_closed_port_is_a_readable_failure() -> None:
    with socket.socket() as probe:
        probe.bind(("127.0.0.1", 0))
        port = int(probe.getsockname()[1])
    config = check(BASE | {"port": port})
    with pytest.raises(DeliveryError) as refused:
        await EmailKind().send(config, None, message(), Outbound())
    assert refused.value.detail == f"The relay refused the connection on port {port}."
