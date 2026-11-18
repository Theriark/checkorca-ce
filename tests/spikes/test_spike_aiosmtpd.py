"""Spike 5: aiosmtpd 1.4.6 receives a message on Python 3.12.

Two ways to run the receiver are checked: the threaded Controller on a free
port, and an SMTP server on the running event loop, which is how the worker of
phase C4-I starts it next to its tick loop. The message is synthetic.
"""

import asyncio
import smtplib
import socket
import sys
import time
from collections.abc import Callable
from email import message_from_bytes, policy
from email.message import EmailMessage
from importlib.metadata import version

from aiosmtpd.controller import Controller
from aiosmtpd.smtp import SMTP, Envelope, Session

SENDER = "backup-server@example.com"
RECIPIENT = "alerts@inbox.test"
SUBJECT = "[Success] Nightly file backup (synthetic C0-B spike)"


class Inbox:
    """aiosmtpd handler that keeps every envelope it is given."""

    def __init__(self) -> None:
        self.envelopes: list[Envelope] = []

    async def handle_DATA(
        self, server: SMTP, session: Session, envelope: Envelope
    ) -> str:
        self.envelopes.append(envelope)
        return "250 Message accepted for delivery"


def free_port() -> int:
    with socket.socket() as probe:
        probe.bind(("127.0.0.1", 0))
        return int(probe.getsockname()[1])


def send(port: int) -> dict[str, tuple[int, bytes]]:
    message = EmailMessage()
    message["From"] = SENDER
    message["To"] = RECIPIENT
    message["Subject"] = SUBJECT
    message["Message-ID"] = "<c0b-spike@example.com>"
    message.set_content("Job: Nightly file backup\nResult: Success\n")
    # local_hostname avoids a DNS lookup of the runner's name.
    with smtplib.SMTP(
        "127.0.0.1", port, local_hostname="sender.test", timeout=10
    ) as client:
        return client.send_message(message)


def assert_received(inbox: Inbox) -> None:
    assert len(inbox.envelopes) == 1
    envelope = inbox.envelopes[0]
    assert envelope.mail_from == SENDER
    assert envelope.rcpt_tos == [RECIPIENT]
    assert isinstance(envelope.content, bytes)
    received = message_from_bytes(envelope.content, policy=policy.default)
    assert received["Subject"] == SUBJECT
    assert "Result: Success" in received.get_body().get_content()


def test_controller_on_a_free_port_receives_one_message(
    report: Callable[..., None],
) -> None:
    inbox = Inbox()
    port = free_port()
    controller = Controller(
        inbox, hostname="127.0.0.1", port=port, server_hostname="checkorca.test"
    )
    controller.start()
    try:
        started = time.perf_counter()
        assert send(port) == {}
        elapsed_ms = (time.perf_counter() - started) * 1000
    finally:
        controller.stop()
    assert_received(inbox)
    report(
        "aiosmtpd-controller",
        version=version("aiosmtpd"),
        python=sys.version.split()[0],
        send_ms=f"{elapsed_ms:.1f}",
    )


async def test_server_on_the_running_loop_receives_one_message(
    report: Callable[..., None],
) -> None:
    inbox = Inbox()
    loop = asyncio.get_running_loop()
    server = await loop.create_server(
        lambda: SMTP(inbox, hostname="checkorca.test"), "127.0.0.1", 0
    )
    try:
        port = int(server.sockets[0].getsockname()[1])
        started = time.perf_counter()
        # smtplib blocks, so it runs in a thread while the loop serves.
        refused = await asyncio.wait_for(asyncio.to_thread(send, port), timeout=10)
        elapsed_ms = (time.perf_counter() - started) * 1000
    finally:
        server.close()
        await asyncio.wait_for(server.wait_closed(), timeout=5)
    assert refused == {}
    assert_received(inbox)
    report("aiosmtpd-loop", version=version("aiosmtpd"), send_ms=f"{elapsed_ms:.1f}")
