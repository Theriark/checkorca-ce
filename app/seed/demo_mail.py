"""Synthetic alert mails for the demo data (app/seed/demo.py).

One template per CE parser pack, in the shape of that pack's own fixtures
(app/parsers/packs/fixtures; legal R-11: example.com and .test addresses,
fictional names). Every mail carries the job's name, its client where the
vendor names one, the outcome and the run's times, so the real parser
claims it with the vendor's pack and the matcher binds it to the demo job
(tests/seed/test_demo.py parses every template). Times are UTC and the Date
header says +0000, so times written without a zone read as UTC.
"""

from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from email.utils import format_datetime
from typing import Final, Literal

Outcome = Literal["success", "warning", "failed"]

# Packs whose mail names the client (client_hint); the others do not, so the
# names of their demo jobs differ across clients.
NAMES_CLIENT: Final = frozenset(
    {"acronis-cp-cloud", "nable-cove", "msp360", "generic-keywords"}
)
_MONTHS: Final = (
    "January",
    "February",
    "March",
    "April",
    "May",
    "June",
    "July",
    "August",
    "September",
    "October",
    "November",
    "December",
)
_DAYS: Final = (
    "Monday",
    "Tuesday",
    "Wednesday",
    "Thursday",
    "Friday",
    "Saturday",
    "Sunday",
)
_TITLES: Final[dict[Outcome, str]] = {
    "success": "Success",
    "warning": "Warning",
    "failed": "Failed",
}


@dataclass(frozen=True, slots=True)
class Run:
    """One reported run of a demo job; the mail is sent when it finished."""

    job: str
    client: str
    outcome: Outcome
    started: datetime
    finished: datetime
    message_id: str


def _utc(moment: datetime) -> datetime:
    return moment.astimezone(UTC)


def _iso(moment: datetime) -> str:
    """2026-11-22 01:00:03"""
    return _utc(moment).strftime("%Y-%m-%d %H:%M:%S")


def _clock(value: datetime) -> str:
    """1:00:04 AM"""
    hour = value.hour % 12 or 12
    half = "AM" if value.hour < 12 else "PM"
    return f"{hour}:{value.minute:02d}:{value.second:02d} {half}"


def _us(moment: datetime) -> str:
    """11/22/2026 1:00:04 AM"""
    value = _utc(moment)
    return f"{value.month}/{value.day}/{value.year} {_clock(value)}"


def _cloud(moment: datetime) -> str:
    """Nov 22, 2026, 8:00:01 PM"""
    value = _utc(moment)
    month = _MONTHS[value.month - 1][:3]
    return f"{month} {value.day}, {value.year}, {_clock(value)}"


def _veeam(moment: datetime) -> str:
    """Sunday, 22 November 2026 22:00:12"""
    value = _utc(moment)
    day = _DAYS[value.weekday()]
    month = _MONTHS[value.month - 1]
    return f"{day}, {value.day} {month} {value.year} {value:%H:%M:%S}"


def _duration(run: Run) -> str:
    seconds = int((run.finished - run.started).total_seconds())
    return f"{seconds // 3600}:{seconds % 3600 // 60:02d}:{seconds % 60:02d}"


def _mail(run: Run, sender: str, subject: str, lines: list[str]) -> bytes:
    head = [
        f"From: {sender}",
        "To: alerts@example.net",
        f"Subject: {subject}",
        f"Date: {format_datetime(_utc(run.finished))}",
        f"Message-ID: {run.message_id}",
        "MIME-Version: 1.0",
        "Content-Type: text/plain; charset=utf-8",
        "",
    ]
    return ("\r\n".join(head + lines) + "\r\n").encode("utf-8")


def _veeam_mail(run: Run) -> bytes:
    word = _TITLES[run.outcome]
    ok, warnings, errors = {
        "success": (3, 0, 0),
        "warning": (2, 1, 0),
        "failed": (2, 0, 1),
    }[run.outcome]
    issues = {
        "success": [],
        "warning": ["vm-files-02\tWarning\tWarning: 2 files skipped (synthetic)"],
        "failed": ["vm-db-01\tFailed\tError: Snapshot failed (synthetic)"],
    }[run.outcome]
    started = _utc(run.started)
    finished = _utc(run.finished)
    lines = [
        "Synthetic demo data for Checkorca-CE; not a real mail.",
        f"Backup job: {run.job}",
        f"{word}\t{3 - errors} of 3 VMs processed",
        _veeam(run.started),
        f"Success\t{ok}\tStart time\t{started:%H:%M:%S}\tTotal size\t180.0 GB",
        f"Warning\t{warnings}\tEnd time\t{finished:%H:%M:%S}\tData read\t24.1 GB",
        f"Error\t{errors}\tDuration\t{_duration(run)}\tTransferred\t11.9 GB",
        *issues,
        "Veeam Backup & Replication 12.3",
    ]
    subject = f"[{word}] {run.job} (3 machines)"
    return _mail(run, '"VBR Server" <vbr@example.com>', subject, lines)


def _synology_mail(run: Run, product: str, label: str, task: str) -> bytes:
    verb = {
        "success": "has completed",
        "warning": "has partially completed",
        "failed": "has failed",
    }[run.outcome]
    lines = [
        "Dear user,",
        "",
        f"{task} {run.job} on NAS-01 {verb}.",
        "",
        f"{label}: {run.job}",
        "Server: NAS-01",
        f"Start time: {_iso(run.started)}",
        f"End time: {_iso(run.finished)}",
    ]
    if run.outcome == "failed":
        lines.append("Error: The destination is offline (synthetic).")
    lines += [
        "",
        f"This message was sent by {product} on NAS-01.",
        "(Synthetic demo data for Checkorca-CE; not a real mail.)",
        "",
        "Sincerely,",
        "Synology DiskStation",
    ]
    subject = f"[NAS-01] {product} - Backup task {run.job} {verb}"
    return _mail(run, "NAS-01 <nas-01@example.com>", subject, lines)


def _abb_mail(run: Run) -> bytes:
    return _synology_mail(run, "Active Backup for Business", "Task", "Backup task")


def _hyperbackup_mail(run: Run) -> bytes:
    return _synology_mail(run, "Hyper Backup", "Task name", "Data backup task")


def _acronis_titles(outcome: Outcome) -> tuple[str, str]:
    return {
        "success": ("Backup succeeded", "Succeeded"),
        "warning": ("Backup succeeded with warnings", "Succeeded with warnings"),
        "failed": ("Backup failed", "Failed"),
    }[outcome]


def _acronis_legacy_mail(run: Run) -> bytes:
    title, status = _acronis_titles(run.outcome)
    lines = [
        title,
        f"Device: {run.job}",
        "Plan: Entire machine to NAS",
        f"Status: {status}",
        f"Started: {_us(run.started)}",
        f"Finished: {_us(run.finished)}",
        "Backed up: 64.2 GB",
    ]
    if run.outcome == "failed":
        lines.append("Error message: The backup location is not available.")
    if run.outcome == "warning":
        lines.append("Warning message: 2 files were skipped.")
    lines.append("Acronis Cyber Protect 16 (synthetic demo data for Checkorca-CE)")
    subject = f"{title}: {run.job} - Entire machine to NAS"
    return _mail(run, '"Cyber Protect Server" <ams@example.com>', subject, lines)


def _acronis_cloud_mail(run: Run) -> bytes:
    title, status = _acronis_titles(run.outcome)
    lines = [
        title,
        f"Customer: {run.client}",
        f"Workload: {run.job}",
        "Protection plan: Workstations daily",
        f"Status: {status}",
        f"Started: {_cloud(run.started)}",
        f"Finished: {_cloud(run.finished)}",
        "Backed up: 2.3 GB",
        "Acronis Cyber Protect Cloud (synthetic demo data for Checkorca-CE)",
    ]
    subject = f"{title}: {run.job}"
    return _mail(run, '"Cyber Protection" <noreply@example.com>', subject, lines)


def _cove_mail(run: Run) -> bytes:
    status, errors = {
        "success": ("Completed", 0),
        "warning": ("Completed with errors", 3),
        "failed": ("Failed", 1),
    }[run.outcome]
    lines = [
        "Cove Data Protection session report (synthetic demo data)",
        f"Device: {run.job}",
        f"Customer: {run.client}",
        "Data source: Files and Folders",
        f"Session status: {status}",
        f"Session start: {_iso(run.started)}",
        f"Session end: {_iso(run.finished)}",
        "Selected size: 512.4 GB",
        "Processed size: 3.1 GB",
        f"Errors: {errors}",
    ]
    subject = f"Session report: {run.job} Files and Folders"
    return _mail(run, '"Backup Reports" <reports@example.com>', subject, lines)


def _msp360_mail(run: Run) -> bytes:
    status = {
        "success": "Success",
        "warning": "Completed with warnings",
        "failed": "Failed",
    }[run.outcome]
    lines = [
        f'Backup plan "{run.job}" report',
        f"Plan: {run.job}",
        "Computer: WS-01",
        f"Company: {run.client}",
        f"Status: {status}",
        f"Start time: {_us(run.started)}",
        f"End time: {_us(run.finished)}",
        "Files copied: 412",
        "Total size: 2.31 GB",
        "MSP360 Managed Backup (synthetic demo data for Checkorca-CE)",
    ]
    subject = f'Backup plan "{run.job}" on WS-01 - {_TITLES[run.outcome]}'
    sender = '"Backup Notifications" <backup-notify@example.com>'
    return _mail(run, sender, subject, lines)


def _generic_mail(run: Run) -> bytes:
    word = _TITLES[run.outcome]
    lines = [
        "Backup summary (synthetic demo data)",
        "",
        f"Client: {run.client}",
        "Host: FS-01",
        f"Status: {word}",
        f"Started: {_iso(run.started)}",
        f"Finished: {_iso(run.finished)}",
        "Processed: 120.5 GB",
        f"Run ID: run-{_utc(run.started):%Y%m%d-%H%M}",
    ]
    subject = f"[{word}] {run.job}"
    return _mail(run, "Backup Server <backup@example.com>", subject, lines)


TEMPLATES: Final[dict[str, Callable[[Run], bytes]]] = {
    "veeam-br": _veeam_mail,
    "synology-abb": _abb_mail,
    "synology-hyperbackup": _hyperbackup_mail,
    "acronis-cp-legacy": _acronis_legacy_mail,
    "acronis-cp-cloud": _acronis_cloud_mail,
    "nable-cove": _cove_mail,
    "msp360": _msp360_mail,
    "generic-keywords": _generic_mail,
}


def render_mail(pack_id: str, run: Run) -> bytes:
    """The RFC 822 bytes of the run's alert mail, as the vendor sends it."""
    return TEMPLATES[pack_id](run)
