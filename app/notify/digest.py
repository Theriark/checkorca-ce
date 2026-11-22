"""The morning digest (phase C8-B): its numbers and the CE ReportRenderer.

build_digest reads the runs of live jobs due in the digest window of a day
(the 24 hours, in the digest zone, up to settings.digest_time_local of that
day) and counts them: verified, warning, failed and silent (overdue or
missed). Each job whose newest due run in the window is missed, overdue,
failed or warning becomes one item, silent first, then failed, then warning.

DigestRenderer turns that into a subject, an HTML body and a text body. The
HTML is one table layout with inline styles (mail clients drop style
sheets), no script, no image and no remote content; every client and job
name and every note is escaped, so a hostile name stays text. The subject
holds counts and the date only, never a name. digest/preview shows the
result; phase C9 sends it every morning through the same renderer.
"""

import html
import uuid
from collections.abc import Sequence
from datetime import date, datetime, time
from typing import Final
from zoneinfo import ZoneInfo

from sqlalchemy.ext.asyncio import AsyncSession

from app import PRODUCT_NAME
from app.access import AccessPolicy, Principal
from app.ext.reports import Digest, DigestItem, RenderedReport
from app.notify.windows import digest_window
from app.repos.dashboard import (
    DUE_STATES,
    SILENT_STATES,
    DashboardRepository,
    HistoryRow,
)

# Jobs listed in one digest at most; the rest are counted.
MAX_ITEMS: Final = 100
# Occurrences read for one digest at most.
MAX_ROWS: Final = 100_000
# Worst first, as on the dashboard: silent, then failed, then warning.
ITEM_ORDER: Final[dict[str, int]] = {
    "missed": 0,
    "overdue": 1,
    "failed": 2,
    "warning": 3,
}
STATE_WORDS: Final[dict[str, str]] = {
    "missed": "Missed",
    "overdue": "Overdue",
    "failed": "Failed",
    "warning": "Warning",
}
# Text and background of the state chips (WCAG AA contrast on white).
STATE_COLOURS: Final[dict[str, tuple[str, str]]] = {
    "missed": ("#5a1e8c", "#f1e8fb"),
    "overdue": ("#5a1e8c", "#f1e8fb"),
    "failed": ("#a40e26", "#fde8eb"),
    "warning": ("#7a4b00", "#fff4d6"),
}
INK: Final = "#14213d"
MUTED: Final = "#4a5568"
LINE: Final = "#e2e8f0"
FONT: Final = "Inter, 'Segoe UI', Arial, sans-serif"


def summarize(
    *,
    day: date,
    timezone: str,
    start: datetime,
    end: datetime,
    rows: Sequence[HistoryRow],
    generated_at: datetime,
    url: str,
    max_items: int = MAX_ITEMS,
) -> Digest:
    """The digest of the occurrences in the window (oldest first)."""
    counts = {"verified": 0, "warning": 0, "failed": 0, "silent": 0}
    newest: dict[uuid.UUID, HistoryRow] = {}
    for row in rows:
        if row.state not in DUE_STATES:
            continue
        counts["silent" if row.state in SILENT_STATES else row.state] += 1
        newest[row.job_id] = row
    flagged = sorted(
        (row for row in newest.values() if row.state in ITEM_ORDER),
        key=lambda row: (
            ITEM_ORDER[row.state],
            row.client_name.casefold(),
            row.job_name.casefold(),
            row.scheduled_for,
        ),
    )
    items = tuple(
        DigestItem(
            client=row.client_name,
            job=row.job_name,
            state=row.state,
            scheduled_for=row.scheduled_for,
            deadline=row.deadline,
            note=row.note,
        )
        for row in flagged[:max_items]
    )
    return Digest(
        day=day,
        timezone=timezone,
        start=start,
        end=end,
        generated_at=generated_at,
        verified=counts["verified"],
        warning=counts["warning"],
        failed=counts["failed"],
        silent=counts["silent"],
        items=items,
        more_items=max(0, len(flagged) - max_items),
        url=url,
    )


async def build_digest(
    db: AsyncSession,
    policy: AccessPolicy,
    principal: Principal,
    *,
    day: date,
    timezone: str,
    digest_time: time,
    now: datetime,
    url: str,
) -> Digest:
    """The digest of day, read from the database (one query)."""
    start, end = digest_window(day, ZoneInfo(timezone), digest_time)
    rows = await DashboardRepository(db, policy).history(
        principal, start=start, end=end, live_only=True, limit=MAX_ROWS
    )
    return summarize(
        day=day,
        timezone=timezone,
        start=start,
        end=end,
        rows=rows,
        generated_at=now,
        url=url,
    )


def subject_of(digest: Digest) -> str:
    """Counts and the date only: no name from the database."""
    head = f"{PRODUCT_NAME} morning check {digest.day.isoformat()}"
    if not digest.expected:
        return f"{head}: no runs were due"
    problems = [
        f"{count} {word}"
        for count, word in (
            (digest.failed, "failed"),
            (digest.silent, "silent"),
            (digest.warning, "warning"),
        )
        if count
    ]
    if not problems:
        return f"{head}: all {digest.verified} runs verified"
    return f"{head}: {', '.join(problems)}, {digest.verified} verified"


def coverage_text(digest: Digest) -> str:
    if not digest.expected:
        return "no runs were due"
    percent = 100 * digest.verified / digest.expected
    return f"{digest.verified} of {digest.expected} runs verified ({percent:.0f}%)"


def _local(moment: datetime, zone: ZoneInfo) -> str:
    return moment.astimezone(zone).strftime("%Y-%m-%d %H:%M")


def _e(value: str) -> str:
    return html.escape(value, quote=True)


def _cell(text: str, *, header: bool = False) -> str:
    tag = "th" if header else "td"
    weight = "600" if header else "400"
    style = (
        f"padding:8px 12px;border-bottom:1px solid {LINE};text-align:left;"
        f"font-weight:{weight};vertical-align:top"
    )
    return f'<{tag} style="{style}">{text}</{tag}>'


def _chip(state: str) -> str:
    ink, background = STATE_COLOURS[state]
    style = (
        "display:inline-block;padding:2px 8px;border-radius:10px;"
        f"color:{ink};background:{background};font-weight:600;font-size:13px"
    )
    return f'<span style="{style}">{_e(STATE_WORDS[state])}</span>'


def render_html(digest: Digest) -> str:
    zone = ZoneInfo(digest.timezone)
    window = (
        f"Runs due from {_local(digest.start, zone)} to "
        f"{_local(digest.end, zone)} ({digest.timezone})"
    )
    counts = "".join(
        _cell(f'{label}<br><strong style="font-size:20px">{value}</strong>')
        for label, value in (
            ("Verified", digest.verified),
            ("Failed", digest.failed),
            ("Silent", digest.silent),
            ("Warning", digest.warning),
        )
    )
    parts = [
        "<!DOCTYPE html>",
        '<html lang="en"><head><meta charset="utf-8">',
        f"<title>{_e(subject_of(digest))}</title></head>",
        f'<body style="margin:0;padding:24px;background:#f4f6f9;color:{INK};'
        f'font-family:{FONT};font-size:15px;line-height:1.5">',
        '<table role="presentation" style="width:100%;max-width:680px;'
        "margin:0 auto;background:#ffffff;border-collapse:collapse;"
        f'border:1px solid {LINE}">',
        '<tr><td style="padding:24px">',
        '<h1 style="margin:0 0 4px;font-size:22px">Morning check, '
        f"{_e(digest.day.isoformat())}</h1>",
        f'<p style="margin:0 0 16px;color:{MUTED}">{_e(window)}</p>',
        '<table role="presentation" style="width:100%;border-collapse:collapse">',
        f"<tr>{counts}</tr></table>",
        f'<p style="margin:16px 0">Coverage: {_e(coverage_text(digest))}.</p>',
    ]
    if digest.items:
        parts += [
            '<h2 style="margin:24px 0 8px;font-size:17px">Needs attention</h2>',
            '<table style="width:100%;border-collapse:collapse">',
            "<tr>"
            + _cell("Client", header=True)
            + _cell("Job", header=True)
            + _cell("State", header=True)
            + _cell("Due", header=True)
            + "</tr>",
        ]
        for item in digest.items:
            due = _e(_local(item.scheduled_for, zone))
            if item.note:
                due += f'<br><span style="color:{MUTED}">{_e(item.note)}</span>'
            parts.append(
                "<tr>"
                + _cell(_e(item.client))
                + _cell(_e(item.job))
                + _cell(_chip(item.state))
                + _cell(due)
                + "</tr>"
            )
        parts.append("</table>")
        if digest.more_items:
            parts.append(
                f'<p style="margin:8px 0;color:{MUTED}">And {digest.more_items} '
                "more jobs on the Morning check.</p>"
            )
    else:
        parts.append('<p style="margin:16px 0">Nothing needs attention.</p>')
    parts += [
        f'<p style="margin:24px 0 0"><a href="{_e(digest.url)}" '
        'style="color:#1d4ed8">Open the Morning check</a></p>',
        f'<p style="margin:16px 0 0;color:{MUTED};font-size:13px">'
        f"Sent by {_e(PRODUCT_NAME)}.</p>",
        "</td></tr></table></body></html>",
    ]
    return "\n".join(parts)


def render_text(digest: Digest) -> str:
    zone = ZoneInfo(digest.timezone)
    lines = [
        f"Morning check, {digest.day.isoformat()}",
        f"Runs due from {_local(digest.start, zone)} to {_local(digest.end, zone)}"
        f" ({digest.timezone})",
        "",
        f"Verified: {digest.verified}",
        f"Failed: {digest.failed}",
        f"Silent: {digest.silent}",
        f"Warning: {digest.warning}",
        f"Coverage: {coverage_text(digest)}",
        "",
    ]
    if digest.items:
        lines.append("Needs attention:")
        for item in digest.items:
            line = (
                f"- {STATE_WORDS[item.state]}: {item.client} / {item.job}, "
                f"due {_local(item.scheduled_for, zone)}"
            )
            if item.note:
                line += f" ({item.note})"
            # One line per item, whatever the names hold.
            lines.append(" ".join(line.split()))
        if digest.more_items:
            lines.append(f"And {digest.more_items} more jobs on the Morning check.")
    else:
        lines.append("Nothing needs attention.")
    lines += ["", f"Open the Morning check: {digest.url}", f"Sent by {PRODUCT_NAME}."]
    return "\n".join(lines) + "\n"


class DigestRenderer:
    """The CE ReportRenderer."""

    def render(self, digest: Digest) -> RenderedReport:
        return RenderedReport(
            subject=subject_of(digest),
            html=render_html(digest),
            text=render_text(digest),
        )
