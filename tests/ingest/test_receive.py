"""The inbox rules every receiver applies: size, sender allowlist,
Authentication-Results dkim=pass, and what counts as an e-mail message.
Addresses are synthetic (R-11: example.com, example.net, .test)."""

import time

import pytest

from app.db.models import Inbox
from app.ingest import mime
from app.ingest.receive import MessageRefused, check_message, is_mail
from app.ingest.store import MAX_MESSAGE_BYTES, MessageTooLarge


def inbox(allowlist: list[str] | None = None, require_auth: bool = False) -> Inbox:
    return Inbox(
        kind="smtp",
        label="Rules",
        code="a" * 24,
        sender_allowlist=allowlist or [],
        require_auth_results=require_auth,
    )


def mail(sender: str, *results: str) -> bytes:
    lines = [f"From: {sender}", "Subject: [Success] Nightly server backup"]
    lines += [f"Authentication-Results: {value}" for value in results]
    return ("\r\n".join(lines) + "\r\n\r\nJob finished.\r\n").encode()


def refusal(rules: Inbox, raw: bytes) -> str | None:
    try:
        check_message(rules, raw)
    except MessageRefused as error:
        return error.reason
    return None


@pytest.mark.parametrize(
    ("sender", "allowed"),
    [
        ("Backup Server <backup@example.com>", True),
        ("BACKUP@EXAMPLE.COM", True),
        ("alerts@example.net", True),
        ("=?utf-8?q?Caf=C3=A9_NAS?= <nas@example.com>", True),
        ("other@example.net", False),
        ("backup@sub.example.com", False),
        ("backup@example.com.attacker.test", False),
        ("no address at all", False),
        ("backup@example.com, intruder@attacker.test", False),
    ],
)
def test_the_sender_allowlist(sender: str, allowed: bool) -> None:
    rules = inbox(["@example.com", "alerts@example.net"])
    assert refusal(rules, mail(sender)) == (None if allowed else "sender")


def test_an_empty_allowlist_allows_every_sender() -> None:
    assert refusal(inbox(), mail("anyone@attacker.test")) is None
    assert refusal(inbox(), b"Subject: no From header\r\n\r\nx") is None


PASS = "mx.example.org; dkim=pass header.d=example.com"
FAIL = "mx.example.org; dkim=fail header.d=example.com"
OTHER = "mx.example.org; dkim=pass header.d=notexample.com"
BY_I = "mx.example.org; dkim=pass (good key) header.i=@example.com"
TWO = "mx.example.org; dkim=pass header.d=attacker.test; dkim=pass header.d=example.com"
SPF = "mx.example.org; spf=pass smtp.mailfrom=example.com"
FORGED = "forged.test; dkim=pass header.d=example.com"
# An AUID with a local part: the domain is after the @.
AUID = "mx.example.org; dkim=pass header.i=alerts@example.com"
# The signer chose a local part that looks like the From domain.
LOCAL_PART = "mx.example.org; dkim=pass header.i=example.com@attacker.test"
# header.d wins over header.i, whatever their order.
I_THEN_D = "mx.example.org; dkim=pass header.i=@attacker.test header.d=example.com"


@pytest.mark.parametrize(
    ("sender", "results", "passed"),
    [
        ("a@example.com", [PASS], True),
        ("a@mail.example.com", [PASS], True),
        ("a@example.com", [BY_I], True),
        ("a@example.com", [TWO], True),
        ("a@example.com", [AUID], True),
        ("a@example.com", [LOCAL_PART], False),
        ("a@example.com", [I_THEN_D], True),
        ("a@example.com", [FAIL], False),
        ("a@example.com", [OTHER], False),
        ("a@example.com", [SPF], False),
        ("a@example.com", [], False),
        ("no address", [PASS], False),
        # Only the topmost header counts: the receiving server writes it.
        ("a@example.com", [FAIL, FORGED], False),
    ],
)
def test_authentication_results_needs_dkim_pass_for_the_sender_domain(
    sender: str, results: list[str], passed: bool
) -> None:
    rules = inbox(require_auth=True)
    expected = None if passed else "authentication"
    assert refusal(rules, mail(sender, *results)) == expected


def test_both_rules_together_name_the_first_that_fails() -> None:
    rules = inbox(["@example.com"], require_auth=True)
    assert refusal(rules, mail("a@example.com", PASS)) is None
    assert refusal(rules, mail("a@attacker.test", PASS)) == "sender"
    assert refusal(rules, mail("a@example.com")) == "authentication"


def test_the_size_cap_comes_first() -> None:
    with pytest.raises(MessageTooLarge):
        check_message(inbox(), b"x" * (MAX_MESSAGE_BYTES + 1))


def test_a_header_block_over_256_kb_is_too_large() -> None:
    headers = b"X-Filler: " + b"y" * mime.MAX_HEADER_BYTES + b"\r\n"
    with pytest.raises(MessageTooLarge, match="headers"):
        check_message(inbox(), headers + b"\r\nbody")
    # Without a blank line every byte is a header byte.
    with pytest.raises(MessageTooLarge, match="headers"):
        check_message(inbox(), b"Subject: x\r\n" + b"z" * mime.MAX_HEADER_BYTES)
    small = b"Subject: x\r\n\r\n" + b"z" * mime.MAX_HEADER_BYTES
    check_message(inbox(), small)


def test_encoded_word_headers_are_read_in_bounded_time() -> None:
    """RFC 2047 decoding is quadratic: values are cut before it runs."""
    word = b"=?utf-8?q?a?= "
    # Just under the 256 KB header limit, every value far over the cut.
    flood = word * (150_000 // len(word))
    raw = b"From: " + flood + b"<a@example.com>\r\nSubject: " + flood[:90_000]
    raw += b"\r\nDate: Mon, 4 Jan 2027 06:29:00 +0000\r\n\r\nbody"
    assert mime.header_bytes(raw) <= mime.MAX_HEADER_BYTES
    started = time.perf_counter()
    with pytest.raises(MessageRefused):
        check_message(inbox(["@example.net"], require_auth=True), raw)
    headers = mime.parse_headers(raw)
    mime.header_list(headers)
    mime.content_hash(raw, headers)
    assert time.perf_counter() - started < 2


def test_the_refusal_text_names_no_address() -> None:
    with pytest.raises(MessageRefused) as refused:
        check_message(inbox(["@example.com"]), mail("intruder@attacker.test"))
    assert "attacker" not in str(refused.value)


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        (b"From: a@example.com\r\n\r\nbody", True),
        (b"Subject: hello\n\nbody", True),
        (b"Date: Mon, 4 Jan 2027 06:29:00 +0000\r\n\r\n", True),
        (b"Message-ID: <x@example.com>\r\n\r\n", True),
        (b"just some text\r\nmore text", False),
        (b"X-Other: 1\r\n\r\nbody", False),
        (b"\x89PNG\r\n\x1a\n", False),
        (b"", False),
    ],
)
def test_what_counts_as_an_e_mail_message(raw: bytes, expected: bool) -> None:
    assert is_mail(raw) is expected
