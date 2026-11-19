"""The ingest seams: a mailbox account never shows its password."""

import uuid

from app.ext.ingest import MailboxAccount

CANARY = "Canary-" + "m" * 16


def test_a_mailbox_account_hides_its_password() -> None:
    account = MailboxAccount(
        inbox_id=uuid.uuid4(),
        host="imap.example.com",
        port=993,
        username="alerts@example.com",
        password=CANARY,
        folder="INBOX",
        tls=True,
    )
    for shown in (repr(account), str(account), f"{account!r}", f"{account}"):
        assert CANARY not in shown
        assert "imap.example.com" in shown
    assert account.password == CANARY
