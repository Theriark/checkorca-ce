"""Reading hostile mail: headers, Message-ID, content hash and text."""

import pytest

from app.ingest import mime


def headers_of(raw: bytes) -> list[list[str]]:
    return mime.header_list(mime.parse_headers(raw))


def test_invalid_bytes_and_nul_never_reach_the_database() -> None:
    raw = b"Subject: caf\xe9 \x00report\r\nX-Folded: one\r\n two\r\n\r\nbody"
    headers = headers_of(raw)
    assert headers[0] == ["Subject", "caf� report"]
    assert headers[1] == ["X-Folded", "one two"]


def test_header_count_and_length_are_capped() -> None:
    raw = b"".join(b"X-Many: %d\r\n" % n for n in range(300))
    raw += b"X-Long: " + b"a" * 9000 + b"\r\n\r\nbody"
    headers = headers_of(raw)
    assert len(headers) == mime.MAX_HEADERS
    raw = b"X-Long: " + b"a" * 9000 + b"\r\n\r\nbody"
    assert len(headers_of(raw)[0][1]) == mime.MAX_HEADER_VALUE


def test_a_value_is_cut_before_it_is_decoded(monkeypatch: pytest.MonkeyPatch) -> None:
    seen: list[int] = []
    decode = mime.decode_header

    def measured(value: str) -> list[tuple[bytes | str, str | None]]:
        seen.append(len(value))
        return decode(value)

    monkeypatch.setattr(mime, "decode_header", measured)
    decoded = mime.header_value("=?utf-8?q?a?= " * 50_000)
    assert seen == [mime.MAX_DECODED_INPUT]
    # The cut may split the last encoded word; the ones before it decode.
    assert decoded.startswith("aaaa") and len(decoded) <= mime.MAX_DECODED_INPUT


def test_a_raw_value_is_unfolded_never_decoded_and_never_cut() -> None:
    value = "a=?utf-8?q?x=3B_y?=\r\n\tb\x00"
    assert mime.raw_header_value(value) == "a=?utf-8?q?x=3B_y?= b"
    assert mime.raw_header_value("z" * mime.MAX_DECODED_INPUT) is not None
    assert mime.raw_header_value("z" * (mime.MAX_DECODED_INPUT + 1)) is None


def test_header_bytes_ends_at_the_first_blank_line() -> None:
    assert mime.header_bytes(b"A: 1\r\n\r\nbody\r\n\r\n") == 4
    assert mime.header_bytes(b"A: 1\n\nbody") == 4
    assert mime.header_bytes(b"A: 1\r\nB: 2") == 10


def test_a_broken_encoded_word_is_kept_as_sent() -> None:
    raw = b"Subject: =?x-unknown?q?abc?=\r\n\r\n"
    assert headers_of(raw) == [["Subject", "=?x-unknown?q?abc?="]]


def test_message_id_is_kept_as_sent_or_dropped() -> None:
    def message_id(value: bytes) -> str | None:
        raw = b"Message-ID: " + value + b"\r\n\r\n"
        return mime.message_id(mime.parse_headers(raw))

    assert message_id(b" <a.1@example.com> ") == "<a.1@example.com>"
    assert message_id(b"") is None
    assert message_id(b"<" + b"a" * 1000 + b"@example.com>") is None
    assert mime.message_id(mime.parse_headers(b"Subject: x\r\n\r\n")) is None


def test_body_of_finds_the_first_blank_line() -> None:
    assert mime.body_of(b"A: 1\r\n\r\nbody\r\n\r\nmore") == b"body\r\n\r\nmore"
    assert mime.body_of(b"A: 1\n\nbody") == b"body"
    assert mime.body_of(b"A: 1\r\n") == b""


def test_the_content_hash_covers_the_identifying_headers_and_the_body() -> None:
    def content(raw: bytes) -> str:
        return mime.content_hash(raw, mime.parse_headers(raw))

    base = (
        b"Date: Mon, 4 Jan 2027 06:29:00 +0000\r\nFrom: backup@example.com\r\n"
        b"To: alerts@example.com\r\nSubject: Backup srv1: OK\r\n\r\nOK\r\n"
    )
    # A relay adds Received headers and may change line endings: same message.
    relayed = b"Received: by relay.example.com\r\n" + base
    assert content(base) == content(relayed)
    assert content(base) == content(base.replace(b"\r\n", b"\n"))
    # Anything that tells one alert from another gives another key.
    for old, new in (
        (b"Mon, 4", b"Tue, 5"),
        (b"backup@", b"other@"),
        (b"alerts@", b"team@"),
        (b"srv1: OK", b"srv1: FAILED"),
        (b"\r\n\r\nOK", b"\r\n\r\nKO"),
    ):
        assert content(base) != content(base.replace(old, new)), new


def test_a_message_without_date_is_only_deduplicated_by_message_id() -> None:
    # No Date header, or an empty one: every delivery gets a key of its own.
    for raw in (b"Subject: done\r\n\r\ndone\r\n", b"Date: \r\n\r\ndone\r\n"):
        headers = mime.parse_headers(raw)
        keys = {mime.content_hash(raw, headers) for _ in range(2)}
        assert len(keys) == 2


def test_text_prefers_plain_and_skips_attachments() -> None:
    raw = (
        b"Content-Type: multipart/mixed; boundary=b1\r\n\r\n"
        b"--b1\r\nContent-Type: text/plain\r\n"
        b"Content-Disposition: attachment; filename=log.txt\r\n\r\nsecret log\r\n"
        b"--b1\r\nContent-Type: multipart/alternative; boundary=b2\r\n\r\n"
        b"--b2\r\nContent-Type: text/html\r\n\r\n<p>Backup <b>failed</b></p>\r\n"
        b"--b2\r\nContent-Type: text/plain; charset=iso-8859-1\r\n"
        b"Content-Transfer-Encoding: quoted-printable\r\n\r\n"
        b"Sauvegarde =E9chou=E9e\r\n"
        b"--b2--\r\n--b1--\r\n"
    )
    text, truncated = mime.message_text(raw)
    assert text.strip() == "Sauvegarde échouée"
    assert not truncated


def test_an_html_only_message_gives_its_visible_text() -> None:
    raw = (
        b"Content-Type: text/html; charset=utf-8\r\n\r\n"
        b"<html><head><style>p {color: red}</style></head><body>"
        b"<p onclick=x>Backup failed</p><script>alert(1)</script>"
        b"<p>&lt;script&gt; is shown as text</p></body></html>"
    )
    text, truncated = mime.message_text(raw)
    assert text == "Backup failed\n\n<script> is shown as text"
    assert "alert" not in text and "color" not in text and "onclick" not in text
    assert not truncated


def test_text_with_an_unknown_charset_or_no_text_part() -> None:
    raw = b"Content-Type: text/plain; charset=x-unknown\r\n\r\nhello \xff"
    assert mime.message_text(raw) == ("hello �", False)
    raw = b"Content-Type: image/png\r\n\r\nPNG"
    assert mime.message_text(raw) == ("", False)
    raw = (
        b"Content-Type: multipart/mixed; boundary=b\r\n\r\n"
        b"--b\r\nContent-Type: application/zip\r\n\r\nPK\r\n--b--\r\n"
    )
    assert mime.message_text(raw) == ("", False)


def test_long_text_is_cut_and_marked() -> None:
    raw = b"Subject: x\r\n\r\n" + b"a" * (mime.MAX_TEXT + 10)
    text, truncated = mime.message_text(raw)
    assert len(text) == mime.MAX_TEXT
    assert truncated
