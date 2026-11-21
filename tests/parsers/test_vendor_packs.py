"""The vendor packs of C6-I with every built-in pack loaded.

test_fixtures.py checks that each fixture gives its expected results. This
module checks what holds between the packs (dev-work-plan C6-I, the claim rule
of C5-I): each vendor's mail is claimed by its own pack only, a changed
subject falls back to the body rules or to Unmatched and never to success,
and a mail without result words stays unknown. Fixtures are synthetic
(legal R-11: example.com, .test, fictional companies).
"""

import re
from dataclasses import replace

import pytest

from app.parsers.engine import Mail, Parsed, Unmatched, bench, mail_from_raw, parse
from app.parsers.loader import Fixture, builtin_packs, pack_fixtures
from app.parsers.model import Pack

PACKS = builtin_packs()
GENERIC = "generic-keywords"
VENDOR_IDS = (
    "acronis-cp-cloud",
    "acronis-cp-legacy",
    "msp360",
    "nable-cove",
    "synology-abb",
    "synology-hyperbackup",
    "veeam-br",
)
VENDOR_PACKS = [pack for pack in PACKS if pack.id in VENDOR_IDS]
VENDOR_FIXTURES = [
    fixture
    for pack in VENDOR_PACKS
    for fixture in pack_fixtures(pack)
    if fixture.expected
]
GENERIC_FIXTURES = [
    fixture for pack in PACKS if pack.id == GENERIC for fixture in pack_fixtures(pack)
]
# The words a result is read from; a mail without them reports nothing.
RESULT_WORDS = re.compile(
    r"(?i)succe\w*|complete\w*|finished|\bok\b|warning\w*|partial\w*"
    r"|fail\w*|error\w*|abort\w*|cancel\w*|running|in\s*process|in\s*progress"
    r"|over\s*quota|interrupted|not\s*started|not\s*run|missed"
)
NEUTRAL_SUBJECT = "Fwd: report"


def fixture_id(fixture: Fixture) -> str:
    return f"{fixture.pack_id}/{fixture.name}"


def fixture_of(pack: Pack, kind: str) -> Fixture:
    return next(fixture for fixture in pack_fixtures(pack) if fixture.kind == kind)


def statuses(outcome: object) -> list[str]:
    assert isinstance(outcome, Parsed | Unmatched), outcome
    if isinstance(outcome, Unmatched):
        return []
    return [result.status for result in outcome.results]


def test_the_built_in_packs_are_generic_keywords_and_the_seven_vendor_packs() -> None:
    assert sorted(pack.id for pack in PACKS) == sorted([GENERIC, *VENDOR_IDS])


def test_ce_ships_no_datto_and_no_veeam_m365_pack() -> None:
    for pack in PACKS:
        text = f"{pack.id} {pack.vendor}".lower()
        assert "datto" not in text
        assert "365" not in text and "vbo" not in text


@pytest.mark.parametrize("pack", VENDOR_PACKS, ids=lambda pack: pack.id)
def test_a_vendor_pack_is_unverified_synthetic_with_its_docs(pack: Pack) -> None:
    assert pack.status == "unverified-synthetic"
    assert pack.docs_url is not None and pack.docs_url.startswith("https://")
    assert pack.version >= 1 and pack.vendor
    # Two or more conditions, so it outscores generic-keywords (one).
    assert len(pack.match_all) + len(pack.match_any) >= 2
    kinds = {ref.kind for ref in pack.fixtures}
    assert {"success", "warning", "failed"} <= kinds
    assert {ref.origin for ref in pack.fixtures} == {"synthetic"}


@pytest.mark.parametrize("fixture", VENDOR_FIXTURES, ids=fixture_id)
def test_vendor_mail_is_claimed_by_its_own_pack_only(fixture: Fixture) -> None:
    shown = bench(PACKS, mail_from_raw(fixture.raw))
    scores = {score.pack_id: score.matched for score in shown.scores}
    assert shown.claimed_by == fixture.pack_id, scores
    assert scores[fixture.pack_id] >= 2
    others = {pack_id: scores[pack_id] for pack_id in VENDOR_IDS}
    del others[fixture.pack_id]
    assert set(others.values()) == {0}, others
    assert scores[GENERIC] < scores[fixture.pack_id]


@pytest.mark.parametrize("fixture", GENERIC_FIXTURES, ids=fixture_id)
def test_no_vendor_pack_claims_generic_mail(fixture: Fixture) -> None:
    shown = bench(PACKS, mail_from_raw(fixture.raw))
    scores = {score.pack_id: score.matched for score in shown.scores}
    assert {scores[pack_id] for pack_id in VENDOR_IDS} == {0}, scores


def neutral(mail: Mail) -> Mail:
    return replace(mail, subject=NEUTRAL_SUBJECT)


@pytest.mark.parametrize("pack", VENDOR_PACKS, ids=lambda pack: pack.id)
@pytest.mark.parametrize("kind", ["failed", "warning"])
def test_a_changed_subject_falls_back_to_the_body_never_to_success(
    pack: Pack, kind: str
) -> None:
    """The subject template is edited (or a forward rewrites it): the body
    rules decide, or nothing claims the mail. Never success."""
    mail = mail_from_raw(fixture_of(pack, kind).raw)
    outcome = parse(PACKS, neutral(mail))
    if isinstance(outcome, Parsed):
        assert outcome.pack_id == pack.id
        assert statuses(outcome) == [kind]
    else:
        assert statuses(outcome) == []


@pytest.mark.parametrize("pack", VENDOR_PACKS, ids=lambda pack: pack.id)
def test_a_success_subject_never_hides_a_failed_body(pack: Pack) -> None:
    """The failure in the body wins over a subject that reads as success."""
    success = mail_from_raw(fixture_of(pack, "success").raw)
    failed = mail_from_raw(fixture_of(pack, "failed").raw)
    outcome = parse(PACKS, replace(failed, subject=success.subject))
    assert isinstance(outcome, Parsed) and outcome.pack_id == pack.id
    assert statuses(outcome) == ["failed"]


@pytest.mark.parametrize("pack", VENDOR_PACKS, ids=lambda pack: pack.id)
def test_a_mail_without_result_words_stays_unknown(pack: Pack) -> None:
    """Unknown never becomes success: the success mail with its result words
    taken out is claimed by its pack and gives unknown."""
    mail = mail_from_raw(fixture_of(pack, "success").raw)
    blank = replace(
        mail,
        subject=RESULT_WORDS.sub("xxxx", mail.subject),
        body=RESULT_WORDS.sub("xxxx", mail.body),
    )
    outcome = parse(PACKS, blank)
    assert isinstance(outcome, Parsed) and outcome.pack_id == pack.id
    assert statuses(outcome) == ["unknown"]
    # Nor with a neutral subject.
    assert "success" not in statuses(parse(PACKS, neutral(blank)))


def test_unknown_generic_mail_stays_unknown_with_the_vendor_packs() -> None:
    (fixture,) = [item for item in GENERIC_FIXTURES if item.kind == "unknown"]
    outcome = parse(PACKS, mail_from_raw(fixture.raw))
    assert isinstance(outcome, Parsed) and outcome.pack_id == GENERIC
    assert statuses(outcome) == ["unknown"]
