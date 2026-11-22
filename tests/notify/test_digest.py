"""The morning digest's numbers and the CE ReportRenderer (phase C8-B): no
script, every name escaped, the subject without names, and the local-time
windows across a change of the clocks.

Names are synthetic (legal R-11: fictional companies).
"""

import uuid
from datetime import UTC, date, datetime, time, timedelta
from zoneinfo import ZoneInfo

from app.ext.reports import Digest, ReportRenderer
from app.notify.digest import DigestRenderer, summarize
from app.notify.windows import (
    day_bounds,
    digest_window,
    local_date,
    morning_line,
    night_window,
)
from app.repos.dashboard import HistoryRow

LISBON = ZoneInfo("Europe/Lisbon")
NIGHT = datetime(2027, 1, 5, 22, tzinfo=UTC)
HOSTILE = '<script>alert("x")</script> & <img src=x onerror=alert(1)>'


def row(
    job: str,
    state: str,
    *,
    client: str = "Fictional Dental Clinic",
    at: datetime = NIGHT,
    job_id: uuid.UUID | None = None,
    note: str | None = None,
) -> HistoryRow:
    return HistoryRow(
        client_id=uuid.UUID(int=1),
        client_name=client,
        job_id=job_id or uuid.uuid5(uuid.NAMESPACE_URL, job),
        job_name=job,
        job_kind="backup",
        parser_pack_id=None,
        scheduled_for=at,
        deadline=at + timedelta(hours=8),
        state=state,
        note=note,
        result_status=None,
        started_at=None,
        finished_at=None,
        received_at=None,
    )


def digest(rows: list[HistoryRow], max_items: int = 100) -> Digest:
    start = datetime(2027, 1, 5, 7, 30, tzinfo=UTC)
    return summarize(
        day=date(2027, 1, 6),
        timezone="Europe/Lisbon",
        start=start,
        end=start + timedelta(days=1),
        rows=rows,
        generated_at=start + timedelta(days=1),
        url="https://ce-dev-checkorca.example.test/",
        max_items=max_items,
    )


def test_counts_and_items_take_the_newest_run_of_each_job() -> None:
    hourly = uuid.uuid4()
    summary = digest(
        [
            row("Hourly sync job", "failed", job_id=hourly, at=NIGHT),
            row(
                "Hourly sync job",
                "verified",
                job_id=hourly,
                at=NIGHT + timedelta(hours=1),
            ),
            row("Offsite copy", "missed", client="Example Freight Ltd"),
            row("Database dump", "failed"),
            row("Mail archive", "warning", client="Sample Law Office"),
            row("Late copy", "overdue", note="started, never finished"),
            row("Tonight", "pending"),
            row("Planned", "maintenance"),
        ]
    )
    assert (summary.verified, summary.failed, summary.silent, summary.warning) == (
        1,
        2,
        2,
        1,
    )
    assert summary.expected == 6
    # Silent first, then failed, then warning; the recovered job is not listed.
    assert [(item.job, item.state) for item in summary.items] == [
        ("Offsite copy", "missed"),
        ("Late copy", "overdue"),
        ("Database dump", "failed"),
        ("Mail archive", "warning"),
    ]
    assert summary.more_items == 0


def test_the_renderer_is_the_report_renderer_seam() -> None:
    renderer: ReportRenderer = DigestRenderer()
    report = renderer.render(digest([row("Database dump", "failed")]))
    assert report.subject == (
        "Checkorca-CE morning check 2027-01-06: 1 failed, 0 verified"
    )
    assert report.html.startswith("<!DOCTYPE html>")
    assert "Needs attention" in report.html
    assert "Failed: Fictional Dental Clinic / Database dump, due 2027-01-05 22:00" in (
        report.text
    )
    assert "Coverage: 0 of 1 runs verified (0%)" in report.text


def test_subjects_hold_counts_only() -> None:
    renderer = DigestRenderer()
    quiet = renderer.render(digest([]))
    assert quiet.subject == "Checkorca-CE morning check 2027-01-06: no runs were due"
    assert "Nothing needs attention." in quiet.html
    assert "Coverage: no runs were due" in quiet.text
    good = renderer.render(digest([row("Nightly", "verified")]))
    assert good.subject.endswith(": all 1 runs verified")
    named = renderer.render(digest([row(HOSTILE, "failed", client=HOSTILE)]))
    assert HOSTILE not in named.subject and "script" not in named.subject


def test_hostile_names_stay_text() -> None:
    report = DigestRenderer().render(
        digest([row(HOSTILE, "missed", client=HOSTILE, note=HOSTILE)])
    )
    html = report.html.lower()
    assert "<script" not in html
    assert "<img" not in html
    assert "&lt;script&gt;alert(&quot;x&quot;)&lt;/script&gt; &amp; &lt;img" in html
    # The text body keeps the names as they are, on one line per item.
    item_lines = [line for line in report.text.splitlines() if line.startswith("- ")]
    assert len(item_lines) == 1 and HOSTILE in item_lines[0]


def test_a_long_list_is_cut_and_counted() -> None:
    rows = [row(f"Job {number:03d}", "failed") for number in range(5)]
    summary = digest(rows, max_items=3)
    assert [item.job for item in summary.items] == ["Job 000", "Job 001", "Job 002"]
    assert summary.more_items == 2
    report = DigestRenderer().render(summary)
    assert "And 2 more jobs on the Morning check." in report.html
    assert "And 2 more jobs on the Morning check." in report.text


def test_days_and_nights_follow_the_digest_zone() -> None:
    # Summer time starts on 28 March 2027 in Lisbon: that day has 23 hours.
    start, end = day_bounds(date(2027, 3, 28), LISBON)
    assert (start, end - start) == (
        datetime(2027, 3, 28, tzinfo=UTC),
        timedelta(hours=23),
    )
    assert local_date(datetime(2027, 7, 1, 23, 30, tzinfo=UTC), LISBON) == date(
        2027, 7, 2
    )
    # Before 18:00 the night that ends today at 12:00; from 18:00 tonight's.
    morning = datetime(2027, 7, 2, 8, tzinfo=UTC)
    assert night_window(morning, LISBON) == (
        datetime(2027, 7, 1, 17, tzinfo=UTC),
        datetime(2027, 7, 2, 11, tzinfo=UTC),
    )
    evening = datetime(2027, 7, 2, 17, 30, tzinfo=UTC)
    assert night_window(evening, LISBON)[0] == datetime(2027, 7, 2, 17, tzinfo=UTC)
    first, last = night_window(morning, LISBON)
    assert morning_line(first, last, LISBON, time(7, 30)) == datetime(
        2027, 7, 2, 6, 30, tzinfo=UTC
    )
    assert morning_line(first, first + timedelta(hours=1), LISBON, time(7, 30)) is None
    assert digest_window(date(2027, 7, 2), LISBON, time(7, 30)) == (
        datetime(2027, 7, 1, 6, 30, tzinfo=UTC),
        datetime(2027, 7, 2, 6, 30, tzinfo=UTC),
    )
