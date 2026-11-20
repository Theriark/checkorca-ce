"""The pack loader: Pack YAML to a compiled pack, or issues with a path.

Packs and names are synthetic (R-11: example.com, fictional companies).
"""

import json
from pathlib import Path
from typing import Any

import pytest
import yaml
from jsonschema import Draft202012Validator

from app.parsers import loader
from app.parsers.loader import (
    MAX_DEPTH,
    MAX_MESSAGE,
    MAX_PACK_BYTES,
    SCHEMA_PATH,
    Fixture,
    PackInvalid,
    PackIssue,
    builtin_pack_texts,
    builtin_packs,
    expected_result,
    load_pack_file,
    pack_fixtures,
    parse_pack,
    parse_pack_cached,
    schema_issues,
)


def minimal() -> dict[str, Any]:
    return {
        "id": "example-tool",
        "version": 1,
        "vendor": "Example Tool",
        "status": "unverified-synthetic",
        "match": {"all": [{"from": r"@example\.com"}]},
        "status_rules": [{"status": "success", "regex": "(?i)success"}],
    }


def text_of(document: object) -> str:
    return yaml.safe_dump(document, sort_keys=False)


def with_changes(**changes: Any) -> str:
    document = minimal()
    document.update(changes)
    return text_of(document)


def issues_of(text: str) -> list[PackIssue]:
    with pytest.raises(PackInvalid) as caught:
        parse_pack(text)
    return list(caught.value.issues)


def paths_of(text: str) -> list[str]:
    return [issue.path for issue in issues_of(text)]


def fixtures(*classes: str) -> list[dict[str, str]]:
    return [
        {"name": f"sample-{index}", "origin": "synthetic", "class": kind}
        for index, kind in enumerate(classes)
    ]


def test_the_schema_is_a_valid_2020_12_schema() -> None:
    Draft202012Validator.check_schema(json.loads(SCHEMA_PATH.read_text("utf-8")))


def test_a_minimal_pack_loads() -> None:
    pack = parse_pack(text_of(minimal()))
    assert (pack.id, pack.version, pack.vendor) == ("example-tool", 1, "Example Tool")
    assert pack.status == "unverified-synthetic"
    assert pack.docs_url is None
    assert pack.split is None
    assert pack.match_any == ()
    (condition,) = pack.match_all
    assert (condition.where, condition.path) == ("from", "/match/all/0/from")
    assert condition.pattern.search("alerts@example.com")
    (rule,) = pack.status_rules
    assert (rule.status, rule.where) == ("success", "record")
    assert rule.path == "/status_rules/0/regex"
    assert pack.fields == pack.details == pack.fixtures == ()


def test_every_part_of_a_full_pack_is_compiled() -> None:
    text = with_changes(
        status="verified",
        docs_url="https://docs.example.com/alerts",
        match={"all": [{"from": "a"}], "any": [{"subject": "b"}, {"body": "c"}]},
        split={"record": "(?m)^Job:"},
        extract={
            "job_name": {"regex": "Job: (?P<name>.+)"},
            "client_hint": {"literal": "Fictional Dental Clinic"},
            "started_at": {
                "regex": "at (?P<at>.+)",
                "in": "subject",
                "format": "%d/%m/%Y %H:%M",
            },
            "details": {"size": {"regex": "Size: (?P<size>.+)", "in": "body"}},
        },
        status_rules=[
            {"status": "failed", "regex": "failed", "in": "subject"},
            {"status": "success", "regex": "ok"},
        ],
        fixtures=fixtures("success", "failed", "warning"),
    )
    pack = parse_pack(text)
    assert pack.status == "verified"
    assert pack.docs_url == "https://docs.example.com/alerts"
    any_paths = [condition.path for condition in pack.match_any]
    assert any_paths == ["/match/any/0/subject", "/match/any/1/body"]
    assert pack.split is not None and pack.split.pattern == "(?m)^Job:"
    job, client, started = pack.fields
    assert (job.name, job.group, job.where) == ("job_name", "name", "record")
    assert job.literal is None
    assert (client.literal, client.pattern) == ("Fictional Dental Clinic", None)
    assert (started.where, started.time_format) == ("subject", "%d/%m/%Y %H:%M")
    (size,) = pack.details
    assert (size.name, size.where) == ("size", "body")
    assert size.path == "/extract/details/size"
    assert [rule.where for rule in pack.status_rules] == ["subject", "record"]
    assert [ref.kind for ref in pack.fixtures] == ["success", "failed", "warning"]


def test_a_pack_without_status_rules_is_refused() -> None:
    document = minimal()
    del document["status_rules"]
    message = "'status_rules' is a required property"
    assert issues_of(text_of(document)) == [PackIssue("", message)]


@pytest.mark.parametrize(
    ("changes", "path"),
    [
        ({"status_rules": []}, "/status_rules"),
        (
            {"status_rules": [{"status": "fine", "regex": "x"}]},
            "/status_rules/0/status",
        ),
        ({"status_rules": [{"status": "success"}]}, "/status_rules/0"),
        (
            {"status_rules": [{"status": "success", "regex": ""}]},
            "/status_rules/0/regex",
        ),
        ({"status": "beta"}, "/status"),
        ({"id": "Example Tool"}, "/id"),
        ({"version": "1"}, "/version"),
        ({"version": 0}, "/version"),
        ({"colour": "blue"}, ""),
        ({"match": {}}, "/match"),
        ({"match": {"all": []}}, "/match/all"),
        ({"match": {"all": [{"from": "a", "to": "b"}]}}, "/match/all/0"),
        ({"match": {"all": [{"cc": "a"}]}}, "/match/all/0"),
        ({"docs_url": "http://docs.example.com"}, "/docs_url"),
        ({"docs_url": "https://docs.example.com\n"}, "/docs_url"),
        ({"split": {}}, "/split"),
        ({"extract": {"size": {"literal": "1"}}}, "/extract"),
        ({"extract": {"job_name": {}}}, "/extract/job_name"),
        (
            {"extract": {"run_id": {"regex": "(?P<x>.)", "in": "cc"}}},
            "/extract/run_id/in",
        ),
        ({"extract": {"details": {"Bad Key": {"literal": "x"}}}}, "/extract/details"),
        (
            {"fixtures": [{"name": "Sample", "origin": "real", "class": "success"}]},
            "/fixtures/0/name",
        ),
        (
            {"fixtures": [{"name": "a", "origin": "made-up", "class": "success"}]},
            "/fixtures/0/origin",
        ),
    ],
)
def test_the_schema_names_the_path_of_a_mistake(
    changes: dict[str, Any], path: str
) -> None:
    assert path in paths_of(with_changes(**changes))


def test_a_long_value_is_quoted_short() -> None:
    (issue,) = issues_of(with_changes(vendor="x" * 5000))
    assert issue.path == "/vendor"
    assert len(issue.message) == MAX_MESSAGE
    assert issue.message.endswith("...")


def test_a_verified_pack_needs_fixtures_and_docs() -> None:
    assert issues_of(with_changes(status="verified")) == [
        PackIssue("", "'docs_url' is a required property"),
        PackIssue("", "'fixtures' is a required property"),
    ]


def test_a_verified_pack_needs_at_least_3_fixtures() -> None:
    text = with_changes(
        status="verified",
        docs_url="https://docs.example.com",
        fixtures=fixtures("success", "failed"),
    )
    assert paths_of(text) == ["/fixtures"]


def test_a_verified_pack_needs_fixtures_of_3_classes() -> None:
    text = with_changes(
        status="verified",
        docs_url="https://docs.example.com",
        fixtures=fixtures("success", "failed", "failed", "success"),
    )
    message = "a verified pack needs fixtures of at least 3 classes; found 2"
    assert issues_of(text) == [PackIssue("/fixtures", message)]


def test_an_unverified_pack_needs_no_fixtures() -> None:
    assert parse_pack(with_changes(fixtures=fixtures("success"))).fixtures


@pytest.mark.parametrize(
    ("changes", "path"),
    [
        (
            {"status_rules": [{"status": "failed", "regex": "("}]},
            "/status_rules/0/regex",
        ),
        ({"match": {"any": [{"subject": "[a-"}]}}, "/match/any/0/subject"),
        ({"split": {"record": "(?P<x"}}, "/split/record"),
        ({"extract": {"job_name": {"regex": "a)"}}}, "/extract/job_name/regex"),
        (
            {"extract": {"details": {"size": {"regex": "*"}}}},
            "/extract/details/size/regex",
        ),
    ],
)
def test_a_regex_that_does_not_compile_is_named(
    changes: dict[str, Any], path: str
) -> None:
    (issue,) = issues_of(with_changes(**changes))
    assert issue.path == path
    assert issue.message.startswith("not a valid regular expression")


@pytest.mark.parametrize("pattern", ["Job: (.+)", "(?P<a>x)(?P<b>y)"])
def test_an_extract_regex_needs_exactly_one_named_group(pattern: str) -> None:
    (issue,) = issues_of(with_changes(extract={"job_name": {"regex": pattern}}))
    assert issue.path == "/extract/job_name/regex"
    assert issue.message.startswith("needs exactly one named group")


@pytest.mark.parametrize(
    ("field", "message"),
    [
        ({"regex": "(?P<x>.)", "literal": "x"}, "give either regex or literal"),
        ({"in": "subject"}, "give either regex or literal"),
        ({"literal": "x", "in": "subject"}, "in and format apply to a regex"),
        ({"literal": "x", "format": "%Y"}, "in and format apply to a regex"),
    ],
)
def test_a_field_gives_regex_or_literal(field: dict[str, str], message: str) -> None:
    (issue,) = issues_of(with_changes(extract={"started_at": field}))
    assert issue.path == "/extract/started_at"
    assert issue.message.startswith(message)


@pytest.mark.parametrize(
    "literal",
    [r'"a\0b"', r'"a\x01b"', r'"a\U0000D800b"', r'" padded"', r'"two  spaces"'],
)
def test_a_literal_is_plain_text(literal: str) -> None:
    text = text_of(minimal()) + f"extract:\n  details:\n    k: {{literal: {literal}}}\n"
    (issue,) = issues_of(text)
    assert issue.path == "/extract/details/k/literal"
    assert issue.message.startswith("must be plain text")


@pytest.mark.parametrize("time_format", ["%d %d", "%Q", "%s"])
def test_a_time_format_must_read_back(time_format: str) -> None:
    field = {"regex": "(?P<at>.+)", "format": time_format}
    (issue,) = issues_of(with_changes(extract={"started_at": field}))
    assert issue.path == "/extract/started_at/format"
    assert issue.message.startswith("not a strptime format")


@pytest.mark.parametrize("time_format", ["%d/%m/%Y %H:%M", "%Y-%m-%dT%H:%M:%S%z"])
def test_a_usable_time_format_loads(time_format: str) -> None:
    field = {"regex": "(?P<at>.+)", "format": time_format}
    (started,) = parse_pack(with_changes(extract={"started_at": field})).fields
    assert started.time_format == time_format


@pytest.mark.parametrize(
    ("text", "path"),
    [
        ("version: 0x" + "f" * 5000 + "\n", "/version"),
        ("version: -0b" + "1" * 20000 + "\n", "/version"),
        ("version: 9223372036854775808\n", "/version"),
        (
            "extract:\n  details:\n    ? 0x" + "f" * 5000 + "\n    : x\n",
            "/extract/details",
        ),
        ("fixtures:\n  - [0x" + "f" * 5000 + "]\n", "/fixtures/0/0"),
    ],
)
def test_a_huge_number_is_refused(text: str, path: str) -> None:
    (issue,) = issues_of(text)
    assert issue == PackIssue(path, "a number must be smaller than 2**63")


@pytest.mark.parametrize(
    ("line", "path"),
    [
        (r'id: "example-tool\n"', "/id"),
        (
            r'fixtures: [{name: "sample\n", origin: synthetic, class: success}]',
            "/fixtures/0/name",
        ),
        (r'extract: {details: {"size\n": {literal: x}}}', "/extract/details"),
        ("extract: {details: {1: {literal: x}}}", "/extract/details"),
    ],
)
def test_names_are_strings_without_a_line_break(line: str, path: str) -> None:
    text = text_of(minimal()).replace("id: example-tool\n", "") + line + "\n"
    assert path in paths_of(text)


def test_fixture_names_are_unique() -> None:
    sample = {"name": "sample", "origin": "synthetic", "class": "success"}
    # Two dicts: safe_dump writes one dict used twice as an alias.
    text = with_changes(fixtures=[sample, dict(sample)])
    assert paths_of(text) == ["/fixtures/1/name"]


def test_every_issue_is_reported_in_path_order() -> None:
    text = with_changes(
        split={"record": "("},
        status_rules=[{"status": "failed", "regex": "("}],
        extract={"job_name": {"regex": "x"}},
    )
    assert paths_of(text) == [
        "/extract/job_name/regex",
        "/split/record",
        "/status_rules/0/regex",
    ]


LAUGHS = """\
a: &a ["lol", "lol", "lol", "lol", "lol", "lol", "lol", "lol", "lol"]
b: &b [*a, *a, *a, *a, *a, *a, *a, *a, *a]
c: &c [*b, *b, *b, *b, *b, *b, *b, *b, *b]
d: [*c, *c, *c, *c, *c, *c, *c, *c, *c]
"""


def test_aliases_are_refused() -> None:
    (issue,) = issues_of(LAUGHS)
    assert issue.path == ""
    assert issue.message.startswith("aliases (*name) are not allowed (line 2,")


def test_an_anchor_without_an_alias_is_fine() -> None:
    text = text_of(minimal()).replace("vendor: Example Tool", "vendor: &v Example Tool")
    assert parse_pack(text).vendor == "Example Tool"


@pytest.mark.parametrize("depth", [MAX_DEPTH + 1, 30_000])
def test_deep_nesting_is_refused_before_it_is_built(depth: int) -> None:
    (issue,) = issues_of("[" * depth + "]" * depth)
    assert issue.message.startswith("the document is nested too deeply")


def test_nesting_up_to_the_limit_reaches_the_schema() -> None:
    text = "[" * MAX_DEPTH + "]" * MAX_DEPTH
    assert issues_of(text)[0].message.endswith("is not of type 'object'")


def test_a_duplicate_key_is_refused() -> None:
    text = text_of(minimal()) + "vendor: Other Tool\n"
    message = "duplicate key 'vendor' (line 11, column 1)"
    assert issues_of(text) == [PackIssue("", message)]


def test_a_nested_duplicate_key_names_its_mapping() -> None:
    text = "match:\n  all:\n    - {from: a, from: b}\n"
    assert paths_of(text) == ["/match/all/0"]
    assert paths_of("a/b~c:\n  x: 1\n  x: 2\n") == ["/a~1b~0c"]


def test_a_pack_over_64_kib_is_refused() -> None:
    text = text_of(minimal()) + "#" * MAX_PACK_BYTES
    message = f"a pack may have at most {MAX_PACK_BYTES} bytes"
    assert issues_of(text) == [PackIssue("", message)]


@pytest.mark.parametrize(
    ("text", "message"),
    [
        ("id: [unclosed\n", "line 2"),
        ("a: 1\n---\nb: 2\n", "but found another document"),
        ("!!python/object/apply:os.system ['true']\n", "could not determine"),
        ("version: " + "9" * 5000 + "\n", "the text is not valid YAML"),
        ("id: \U0000d800\n", "the text is not valid YAML"),
        ("id: \x00\n", "the text is not valid YAML"),
    ],
)
def test_text_that_is_not_safe_yaml_is_refused(text: str, message: str) -> None:
    (issue,) = issues_of(text)
    assert issue.path == ""
    assert message in issue.message


@pytest.mark.parametrize("text", ["", "- a\n- b\n", "just text\n"])
def test_a_document_that_is_not_a_mapping_is_refused(text: str) -> None:
    (issue,) = issues_of(text)
    assert issue.path == ""
    assert issue.message.endswith("is not of type 'object'")


def test_a_yaml_date_is_not_a_version() -> None:
    text = text_of(minimal()).replace("version: 1", "version: 2026-11-20")
    assert paths_of(text) == ["/version"]


def test_schema_issues_of_a_valid_document_are_empty() -> None:
    assert schema_issues(minimal()) == []


def test_pack_invalid_lists_its_issues() -> None:
    error = PackInvalid([PackIssue("", "first"), PackIssue("/id", "second")])
    assert str(error) == "/: first; /id: second"
    assert isinstance(error, ValueError)


def test_a_position_is_optional() -> None:
    assert loader._at("problem", None) == "problem"


def test_a_pack_file_is_named_after_its_id(tmp_path: Path) -> None:
    (tmp_path / "example-tool.yaml").write_text(text_of(minimal()))
    other = minimal() | {"id": "other-tool"}
    (tmp_path / "zz-other.yaml").write_text(text_of(other))
    with pytest.raises(PackInvalid) as caught:
        builtin_packs(tmp_path)
    message = "must be 'zz-other', the name of the file"
    assert caught.value.issues == (PackIssue("/id", message),)
    (tmp_path / "zz-other.yaml").unlink()
    (tmp_path / "other-tool.yaml").write_text(text_of(other))
    ids = [pack.id for pack in builtin_packs(tmp_path)]
    assert ids == ["example-tool", "other-tool"]
    assert load_pack_file(tmp_path / "other-tool.yaml").id == "other-tool"
    texts = builtin_pack_texts(tmp_path)
    assert [(pack.id, text) for pack, text in texts] == [
        ("example-tool", text_of(minimal())),
        ("other-tool", text_of(other)),
    ]


def test_the_built_in_packs_come_with_their_texts() -> None:
    texts = builtin_pack_texts()
    assert [pack.id for pack, _ in texts] == [pack.id for pack in builtin_packs()]
    for pack, text in texts:
        assert parse_pack(text).version == pack.version


def test_a_cached_pack_is_compiled_once_per_text() -> None:
    text = text_of(minimal())
    assert parse_pack_cached(text) is parse_pack_cached(text)
    assert parse_pack_cached(text).id == "example-tool"
    for _ in range(2):
        with pytest.raises(PackInvalid):
            parse_pack_cached("id: [")


def write_fixture(tmp_path: Path, expected: str) -> list[Fixture]:
    document = minimal() | {"fixtures": fixtures("success")}
    pack = parse_pack(text_of(document))
    folder = tmp_path / pack.id
    folder.mkdir(exist_ok=True)
    (folder / "sample-0.eml").write_bytes(b"Subject: x\n\nbody\n")
    (folder / "sample-0.expected.json").write_text(expected)
    return list(pack_fixtures(pack, tmp_path))


def test_a_fixture_is_read_with_its_expected_results(tmp_path: Path) -> None:
    expected = [
        {
            "status": "success",
            "job_name": "Nightly server backup",
            "client_hint": None,
            "started_at": "2026-11-19T01:00:00+00:00",
            "details": {"size": "1 GB"},
        }
    ]
    (fixture,) = write_fixture(tmp_path, json.dumps(expected))
    assert (fixture.pack_id, fixture.name) == ("example-tool", "sample-0")
    assert (fixture.origin, fixture.kind) == ("synthetic", "success")
    assert fixture.raw == b"Subject: x\n\nbody\n"
    (result,) = fixture.expected
    assert result.job_name == "Nightly server backup"
    assert result.started_at is not None and result.started_at.utcoffset() is not None
    assert result.finished_at is None
    assert result.details == {"size": "1 GB"}


def test_a_missing_fixture_file_raises(tmp_path: Path) -> None:
    pack = parse_pack(text_of(minimal() | {"fixtures": fixtures("success")}))
    with pytest.raises(FileNotFoundError):
        list(pack_fixtures(pack, tmp_path))


def test_an_expected_file_holds_a_list(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="must hold a list"):
        write_fixture(tmp_path, '{"status": "success"}')


@pytest.mark.parametrize(
    ("item", "message"),
    [
        ("success", "must be an object"),
        ({"status": "success", "colour": "x"}, "unknown keys: colour"),
        ({"status": "fine"}, "status must be one of"),
        ({"status": "success", "details": []}, "details must be an object"),
        ({"status": "success", "job_name": 1}, "job_name must be a text or null"),
        ({"status": "success", "started_at": 1}, "must be an ISO 8601 text"),
        ({"status": "success", "finished_at": "2026-11-19T01:00:00"}, "time zone"),
    ],
)
def test_an_expected_result_is_checked(item: object, message: str) -> None:
    with pytest.raises(ValueError, match=message):
        expected_result(item, "sample.expected.json/0")
