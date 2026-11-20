"""Every fixture of every built-in pack gives its expected results.

A pack is app/parsers/packs/<id>.yaml with its fixtures in
app/parsers/packs/fixtures/<id>/: <name>.eml and <name>.expected.json, listed
in the pack. New packs (C6-I) only add files; this module finds them.
"""

from dataclasses import replace

import pytest

from app.parsers.engine import Parsed, apply, mail_from_raw, parse
from app.parsers.loader import FIXTURES_DIR, Fixture, builtin_packs, pack_fixtures
from app.parsers.model import Pack

PACKS = builtin_packs()
FIXTURES = [fixture for pack in PACKS for fixture in pack_fixtures(pack)]


def fixture_id(fixture: Fixture) -> str:
    return f"{fixture.pack_id}/{fixture.name}"


def test_the_generic_keywords_pack_is_built_in() -> None:
    assert "generic-keywords" in {pack.id for pack in PACKS}
    assert len({pack.id for pack in PACKS}) == len(PACKS)


@pytest.mark.parametrize("fixture", FIXTURES, ids=fixture_id)
def test_a_fixture_gives_its_expected_results(fixture: Fixture) -> None:
    outcome = parse(PACKS, mail_from_raw(fixture.raw))
    if not fixture.expected:
        # Mail the pack must not parse: another pack or none claims it.
        assert not (isinstance(outcome, Parsed) and outcome.pack_id == fixture.pack_id)
        return
    assert isinstance(outcome, Parsed), outcome
    assert outcome.pack_id == fixture.pack_id
    got = tuple(replace(result, spans=()) for result in outcome.results)
    assert got == fixture.expected


@pytest.mark.parametrize("fixture", FIXTURES, ids=fixture_id)
def test_a_fixture_belongs_to_its_class(fixture: Fixture) -> None:
    statuses = [result.status for result in fixture.expected]
    if fixture.kind == "unmatched":
        assert statuses == []
    elif fixture.kind == "digest":
        assert len(statuses) > 1
    else:
        assert statuses == [fixture.kind]


@pytest.mark.parametrize("fixture", FIXTURES, ids=fixture_id)
def test_every_span_points_at_its_value(fixture: Fixture) -> None:
    mail = mail_from_raw(fixture.raw)
    pack = next(pack for pack in PACKS if pack.id == fixture.pack_id)
    outcome = apply(pack, mail)
    assert isinstance(outcome, Parsed), outcome
    texts = {"body": mail.body, "subject": mail.subject, "from": mail.sender}
    texts["to"] = mail.to
    for result in outcome.results:
        for span in result.spans:
            found = texts[span.source][span.start : span.end]
            assert found.strip(), span
            if span.field in ("job_name", "client_hint", "run_id"):
                assert " ".join(found.split()) == getattr(result, span.field)


@pytest.mark.parametrize("pack", PACKS, ids=lambda pack: pack.id)
def test_every_fixture_file_is_listed_by_its_pack(pack: Pack) -> None:
    listed = {ref.name for ref in pack.fixtures}
    folder = FIXTURES_DIR / pack.id
    files = {path.name for path in folder.iterdir()} if folder.exists() else set()
    expected = {f"{name}.eml" for name in listed}
    expected |= {f"{name}.expected.json" for name in listed}
    assert files == expected


@pytest.mark.parametrize("pack", PACKS, ids=lambda pack: pack.id)
def test_an_unverified_pack_has_synthetic_fixtures_only(pack: Pack) -> None:
    if pack.status == "unverified-synthetic":
        assert {ref.origin for ref in pack.fixtures} <= {"synthetic"}


def test_every_fixture_is_synthetic_or_real() -> None:
    assert FIXTURES
    assert {fixture.origin for fixture in FIXTURES} <= {"synthetic", "real"}
