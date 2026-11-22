"""Jobs as CSV: the columns, the export writer and the import reader.

Columns (Interfaces chapter): client, job, kind, schedule_kind, schedule_expr,
timezone, max_runtime_minutes, grace_minutes, escalate_minutes,
warning_policy, consecutive_failures_to_alert, match_key, parser_pack_id.

Spreadsheet formula injection: a cell that starts with = + - @ tab or carriage
return (after any leading apostrophes) is written with one more apostrophe in
front, so a spreadsheet shows it as text. The reader takes that apostrophe
off again, so an export imports back unchanged.
"""

import csv
import io
from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from typing import Final

COLUMNS: Final = (
    "client",
    "job",
    "kind",
    "schedule_kind",
    "schedule_expr",
    "timezone",
    "max_runtime_minutes",
    "grace_minutes",
    "escalate_minutes",
    "warning_policy",
    "consecutive_failures_to_alert",
    "match_key",
    "parser_pack_id",
)
REQUIRED_COLUMNS: Final = frozenset(
    {"client", "job", "schedule_kind", "schedule_expr", "timezone"}
)
MAX_IMPORT_BYTES: Final = 1024 * 1024
MAX_IMPORT_ROWS: Final = 5000
FORMULA_START: Final = frozenset("=+-@\t\r")


class CsvFileError(ValueError):
    """The file as a whole cannot be read; the text is for users."""


def guard_cell(value: str) -> str:
    """The cell as a spreadsheet must show it: never as a formula."""
    if value.lstrip("'")[:1] in FORMULA_START:
        return "'" + value
    return value


def unguard_cell(value: str) -> str:
    """Undo guard_cell."""
    if value.startswith("'") and value.lstrip("'")[:1] in FORMULA_START:
        return value[1:]
    return value


def render_table(
    columns: Sequence[str], rows: Iterable[Sequence[str | int | None]]
) -> str:
    """CSV text: the header line, then one guarded line per row (the exports
    of phase C8-B use it too)."""
    buffer = io.StringIO()
    writer = csv.writer(buffer, lineterminator="\r\n")
    writer.writerow(columns)
    for row in rows:
        writer.writerow(
            [guard_cell("" if value is None else str(value)) for value in row]
        )
    return buffer.getvalue()


def render(rows: Iterable[Sequence[str | int | None]]) -> str:
    """The jobs CSV text: the header line, then one guarded line per row."""
    return render_table(COLUMNS, rows)


@dataclass(frozen=True, slots=True)
class CsvRow:
    """One data row: its number (the header is row 1), its non-empty cells and
    the columns of the file."""

    number: int
    cells: dict[str, str]
    columns: frozenset[str]


def parse(data: bytes) -> list[CsvRow]:
    """The rows of an import file; CsvFileError when the file is unusable.

    Cells are trimmed and unguarded; empty cells are left out, so the column's
    default applies. Rows with only empty cells are skipped. A row with more
    cells than the header names keeps the extra ones under the key "" (reported
    by the importer).
    """
    if len(data) > MAX_IMPORT_BYTES:
        raise CsvFileError(f"The file is larger than {MAX_IMPORT_BYTES} bytes.")
    try:
        text = data.decode("utf-8-sig")
    except UnicodeDecodeError:
        raise CsvFileError("The file is not UTF-8 text.") from None
    try:
        records = list(csv.reader(io.StringIO(text, newline=""), strict=True))
    except csv.Error:
        raise CsvFileError("The file is not valid CSV.") from None
    if not records:
        raise CsvFileError("The file is empty; the first line names the columns.")
    # Empty header cells (spreadsheets add them) name no column; a value
    # under one is reported like any extra cell.
    header = [name.strip().lower() for name in records[0]]
    named = [name for name in header if name]
    unknown = sorted(set(named) - set(COLUMNS))
    if unknown:
        raise CsvFileError(
            f"Unknown column: {unknown[0][:40]}. Columns: {', '.join(COLUMNS)}."
        )
    if len(set(named)) != len(named):
        raise CsvFileError("A column appears twice in the first line.")
    missing = sorted(REQUIRED_COLUMNS - set(header))
    if missing:
        raise CsvFileError(f"Missing column: {', '.join(missing)}.")
    columns = frozenset(header)
    rows: list[CsvRow] = []
    for index, record in enumerate(records[1:], start=2):
        cells: dict[str, str] = {}
        for position, raw in enumerate(record):
            value = unguard_cell(raw.strip())
            if value:
                name = header[position] if position < len(header) else ""
                cells[name] = value
        if cells:
            rows.append(CsvRow(number=index, cells=cells, columns=columns))
    if len(rows) > MAX_IMPORT_ROWS:
        raise CsvFileError(f"The file has more than {MAX_IMPORT_ROWS} rows.")
    return rows
