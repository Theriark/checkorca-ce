"""The matcher: job names and client hints compared as tokens.

Clients and jobs are synthetic (legal R-11: fictional companies).
"""

import uuid

import pytest

from app.matcher import (
    Bound,
    ClientRef,
    JobRef,
    Matcher,
    NoMatch,
    names_client,
    same_names,
    tokens,
)

DENTAL = ClientRef(
    uuid.UUID(int=1), "Fictional Dental Clinic", ("Dental Clinic", "FDC")
)
FREIGHT = ClientRef(uuid.UUID(int=2), "Example Freight Ltd")
LAW = ClientRef(uuid.UUID(int=3), "Sample Law Office")

DENTAL_NIGHTLY = JobRef(uuid.UUID(int=11), DENTAL.id, "Nightly server backup")
FREIGHT_NIGHTLY = JobRef(uuid.UUID(int=12), FREIGHT.id, "Nightly server backup")
ARCHIVE = JobRef(uuid.UUID(int=13), DENTAL.id, "Mail archive", "MAILARCH-01")
LAW_BACKUP = JobRef(uuid.UUID(int=14), LAW.id, "Backup 1")

MATCHER = Matcher(
    [DENTAL_NIGHTLY, FREIGHT_NIGHTLY, ARCHIVE, LAW_BACKUP], [DENTAL, FREIGHT, LAW]
)


def bound(job: JobRef) -> Bound:
    return Bound(job.id, job.client_id)


@pytest.mark.parametrize(
    ("job_name", "client_hint", "job"),
    [
        ("Nightly server backup", "Fictional Dental Clinic", DENTAL_NIGHTLY),
        ("Nightly server backup", "Example Freight Ltd", FREIGHT_NIGHTLY),
        # Case, punctuation and spacing.
        ("NIGHTLY-SERVER-BACKUP", "fictional dental clinic.", DENTAL_NIGHTLY),
        ("  nightly   server_backup ", "Fictional, Dental  Clinic", DENTAL_NIGHTLY),
        ("[Nightly] (server) backup!", "EXAMPLE FREIGHT LTD", FREIGHT_NIGHTLY),
        # Aliases of the client.
        ("Nightly server backup", "FDC", DENTAL_NIGHTLY),
        ("Nightly server backup", "dental-clinic", DENTAL_NIGHTLY),
        # The match key, and the name still counts.
        ("mailarch 01", None, ARCHIVE),
        ("MAILARCH_01", "FDC", ARCHIVE),
        ("Mail Archive", "Fictional Dental Clinic", ARCHIVE),
        # Without a hint the name must be the only job of that name.
        ("Backup 1", None, LAW_BACKUP),
        # A hint of punctuation only is no hint.
        ("Backup 1", "--", LAW_BACKUP),
        # Compatibility forms (full-width letters) read as their plain form.
        ("Ｂａｃｋｕｐ １", "Sample Law Office", LAW_BACKUP),
    ],
)
def test_names_that_differ_in_case_punctuation_or_spacing_bind(
    job_name: str, client_hint: str | None, job: JobRef
) -> None:
    assert MATCHER.match(job_name, client_hint) == bound(job)


@pytest.mark.parametrize(
    ("job_name", "client_hint", "reason"),
    [
        # Near misses of the job name never bind.
        ("Backup 11", None, "no-job"),
        ("Backup", None, "no-job"),
        ("Backup 1 copy", None, "no-job"),
        ("Backup l", None, "no-job"),
        ("Nightly server backups", "Fictional Dental Clinic", "no-job"),
        ("Nightly sever backup", "Fictional Dental Clinic", "no-job"),
        ("Nightly serverbackup", "FDC", "no-job"),
        ("mailarch 1", "FDC", "no-job"),
        # Near misses of the client never bind either.
        ("Nightly server backup", "Fictional Dental", "no-client"),
        ("Nightly server backup", "Example Freight", "no-client"),
        ("Nightly server backup", "Fictional Dental Clinic Annex", "no-client"),
        ("Nightly server backup", "FD", "no-client"),
        ("Backup 1", "Example Freight Ltd", "no-client"),
        # Two clients have the job and no hint says which.
        ("Nightly server backup", None, "ambiguous"),
        ("Nightly server backup", "", "ambiguous"),
        # Nothing to compare.
        (None, "FDC", "no-job-name"),
        ("", None, "no-job-name"),
        ("--- ***", "FDC", "no-job-name"),
    ],
)
def test_near_misses_and_ambiguity_do_not_bind(
    job_name: str | None, client_hint: str | None, reason: str
) -> None:
    assert MATCHER.match(job_name, client_hint) == NoMatch(reason)


def test_two_jobs_of_one_client_with_the_same_key_are_ambiguous() -> None:
    renamed = JobRef(uuid.UUID(int=15), LAW.id, "Weekly copy", "Backup 1")
    matcher = Matcher([LAW_BACKUP, renamed], [LAW])
    assert matcher.match("Backup 1", "Sample Law Office") == NoMatch("ambiguous")
    assert matcher.match("Weekly copy", None) == bound(renamed)


def test_a_job_whose_key_equals_its_name_is_one_candidate() -> None:
    job = JobRef(uuid.UUID(int=16), LAW.id, "SQL dump", "sql-dump")
    assert Matcher([job], [LAW]).match("SQL DUMP", None) == bound(job)


def test_a_job_of_a_client_the_matcher_does_not_know_needs_no_hint() -> None:
    # The loader leaves out archived clients and their jobs; a job without
    # its client never matches a hint.
    matcher = Matcher([LAW_BACKUP], [])
    assert matcher.match("Backup 1", None) == bound(LAW_BACKUP)
    assert matcher.match("Backup 1", "Sample Law Office") == NoMatch("no-client")


def test_tokens() -> None:
    assert tokens("Nightly-Backup_01!") == ("nightly", "backup", "01")
    assert tokens("  Straße  ") == ("strasse",)
    assert tokens("Clínica") == ("clínica",)
    # A decomposed accent composes first (NFKC), so both spellings are equal.
    assert tokens("Clínica") == tokens("Clínica")
    assert tokens(None) == ()
    assert tokens("") == ()
    assert tokens("...") == ()


def test_same_names_compares_name_and_hint() -> None:
    assert same_names(("Nightly backup", "FDC"), ("nightly-backup", "fdc"))
    assert same_names(("Nightly backup", None), ("Nightly backup", ""))
    assert not same_names(("Nightly backup", None), ("Nightly backup", "FDC"))
    assert not same_names(("Nightly backup", "FDC"), ("Nightly backups", "FDC"))


def test_names_client_reads_the_name_and_the_aliases() -> None:
    assert names_client(DENTAL.name, DENTAL.aliases, "fdc")
    assert names_client(DENTAL.name, DENTAL.aliases, "Fictional dental clinic")
    assert names_client(DENTAL.name, DENTAL.aliases, None)
    assert not names_client(DENTAL.name, DENTAL.aliases, "Dental")
    assert not names_client(FREIGHT.name, (), "FDC")
