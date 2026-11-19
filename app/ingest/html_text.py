"""HTML mail to plain text (rnd-report-2 5.9).

Alert mail is often HTML only. The parser engine and the message detail need
its words, never its markup: the stripper keeps the text of the document,
drops what a browser would not show as text (script, style, title, template,
comments and the like) and turns block elements into line breaks so table rows
and paragraphs stay apart. Entities are decoded, so an escaped "<script>" in
the source comes out as those characters of text; callers always show the
result escaped, never as HTML.

The standard library parser does the tokenising: it never fetches anything,
runs nothing and accepts broken markup. The caller caps the input (a message
is at most 5 MB).
"""

import re
from html.parser import HTMLParser
from typing import Final

# Their content is not text a reader sees. head is not here: its end tag may
# be left out, and its text-bearing children (title, style, script) are.
_HIDDEN: Final = frozenset(
    {
        "iframe",
        "noscript",
        "object",
        "script",
        "style",
        "svg",
        "template",
        "title",
    }
)
# A line break before and after.
_BLOCKS: Final = frozenset(
    {
        "address",
        "article",
        "aside",
        "blockquote",
        "caption",
        "div",
        "dl",
        "fieldset",
        "figcaption",
        "figure",
        "footer",
        "form",
        "h1",
        "h2",
        "h3",
        "h4",
        "h5",
        "h6",
        "header",
        "hr",
        "main",
        "nav",
        "ol",
        "p",
        "pre",
        "section",
        "table",
        "tbody",
        "tfoot",
        "thead",
        "ul",
    }
)
# Rows and list items: a line break before, so they stay on adjacent lines.
_ROWS: Final = frozenset({"dd", "dt", "li", "tr"})
# Table cells sit side by side, apart.
_CELLS: Final = frozenset({"td", "th"})

# Whitespace in the source is one space, as a browser shows it; only <pre>
# keeps its line breaks.
_WHITESPACE = re.compile(r"\s+")
_SPACES = re.compile(r"[ \f\v\r\xa0]+")
_BLANK_LINES = re.compile(r"\n{3,}")


class _TextCollector(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.parts: list[str] = []
        # Depth inside hidden elements (text counts only at 0) and inside <pre>.
        self.hidden = 0
        self.pre = 0

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag in _HIDDEN:
            self.hidden += 1
            return
        if tag == "pre":
            self.pre += 1
        if tag == "br" or tag in _BLOCKS or tag in _ROWS:
            self.parts.append("\n")
        elif tag in _CELLS:
            self.parts.append("\t")

    def handle_startendtag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        # <br/> breaks a line; a self-closed <script/> opens nothing.
        if tag == "br" or tag in _BLOCKS:
            self.parts.append("\n")

    def handle_endtag(self, tag: str) -> None:
        if tag in _HIDDEN:
            self.hidden = max(0, self.hidden - 1)
            return
        if tag == "pre":
            self.pre = max(0, self.pre - 1)
        if tag in _BLOCKS:
            self.parts.append("\n")

    def handle_data(self, data: str) -> None:
        if self.hidden:
            return
        if self.pre:
            self.parts.append(data.replace("\t", " "))
        else:
            self.parts.append(_WHITESPACE.sub(" ", data))


def html_to_text(html: str) -> str:
    """The visible text of an HTML document, one line per block element.

    Runs of spaces become one space, the cells of a table row are separated
    by a tab and at most one blank line stays between blocks.
    """
    collector = _TextCollector()
    collector.feed(html)
    collector.close()
    lines = []
    for line in "".join(collector.parts).split("\n"):
        cells = [_SPACES.sub(" ", cell).strip() for cell in line.split("\t")]
        lines.append("\t".join(cell for cell in cells if cell))
    return _BLANK_LINES.sub("\n\n", "\n".join(lines)).strip()
