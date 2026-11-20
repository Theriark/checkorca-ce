"""Loading a parser pack: Pack YAML text to a compiled Pack, or its issues.

Pack text comes from the repository (the built-in packs in packs/) and, from
phase C5-B, from a signed-in admin, so it is read defensively:

- at most MAX_PACK_BYTES;
- PyYAML's safe loader only (plain data, no Python objects);
- no aliases: a few lines of anchors and aliases expand into an exponential
  document once something walks it (the schema validator, json.dumps);
- no duplicate keys (YAML would keep the last one silently) and at most
  MAX_DEPTH levels of nesting, checked on the event stream before anything
  recursive runs.

Then pack.schema.json (JSON Schema 2020-12) and the checks a schema cannot
express: every regex compiles, an extract regex has exactly one named group,
a field gives regex or literal, fixture names are unique and a verified pack
has fixtures of at least VERIFIED_CLASSES classes.

Every problem is a PackIssue: a JSON Pointer path into the pack ("" for the
whole document) and a message. C5-B returns them from the API and C5-F shows
them beside the editor.
"""

import functools
import json
from collections.abc import Iterator, Sequence
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Final, cast

import regex
import yaml
from jsonschema import Draft202012Validator

from app.ingest.results import RESULT_STATUSES, ParsedResult
from app.parsers.model import (
    FIELDS,
    TIME_FIELDS,
    Condition,
    Extractor,
    FixtureClass,
    FixtureOrigin,
    FixtureRef,
    Header,
    Pack,
    PackStatus,
    Scope,
    StatusRule,
)

MAX_PACK_BYTES: Final = 64 * 1024
# A valid pack nests four levels (extract, details, a field, its keys).
MAX_DEPTH: Final = 10
# A message quotes at most this much of the pack.
MAX_MESSAGE: Final = 300
VERIFIED_CLASSES: Final = 3

PACKS_DIR: Final = Path(__file__).parent / "packs"
FIXTURES_DIR: Final = PACKS_DIR / "fixtures"
SCHEMA_PATH: Final = Path(__file__).parent / "schema" / "pack.schema.json"


@dataclass(frozen=True, slots=True)
class PackIssue:
    """path: a JSON Pointer into the pack, "" for the whole document."""

    path: str
    message: str


class PackInvalid(ValueError):
    """The pack cannot be used; issues says where and why."""

    def __init__(self, issues: Sequence[PackIssue]) -> None:
        self.issues = tuple(issues)
        super().__init__(
            "; ".join(f"{issue.path or '/'}: {issue.message}" for issue in self.issues)
        )


@dataclass(frozen=True, slots=True)
class Fixture:
    """A sample mail of a pack and the results it must give (empty: the pack
    must not parse it)."""

    pack_id: str
    name: str
    origin: FixtureOrigin
    kind: FixtureClass
    raw: bytes
    expected: tuple[ParsedResult, ...]


def _short(message: str) -> str:
    if len(message) <= MAX_MESSAGE:
        return message
    return message[: MAX_MESSAGE - 3] + "..."


def _pointer(parts: Sequence[str | int]) -> str:
    escaped = (str(part).replace("~", "~0").replace("/", "~1") for part in parts)
    return "".join("/" + part for part in escaped)


def _at(message: str, mark: Any) -> str:
    # A yaml.Mark, or the C extension's Mark; None when the text has no place.
    if mark is None:
        return message
    return f"{message} (line {mark.line + 1}, column {mark.column + 1})"


def _check_events(text: str) -> None:
    """Refuse aliases and deep nesting before anything recursive reads the text."""
    depth = 0
    for event in yaml.parse(text, Loader=yaml.SafeLoader):
        if isinstance(event, yaml.AliasEvent):
            message = _at("aliases (*name) are not allowed", event.start_mark)
            raise PackInvalid([PackIssue("", message)])
        if isinstance(event, yaml.MappingStartEvent | yaml.SequenceStartEvent):
            depth += 1
            if depth > MAX_DEPTH:
                message = _at("the document is nested too deeply", event.start_mark)
                raise PackInvalid([PackIssue("", message)])
        elif isinstance(event, yaml.MappingEndEvent | yaml.SequenceEndEvent):
            depth -= 1


def _check_keys(root: yaml.Node | None) -> None:
    """Refuse a mapping that has the same key twice."""
    stack: list[tuple[yaml.Node, list[str | int]]] = []
    if root is not None:
        stack.append((root, []))
    while stack:
        node, parts = stack.pop()
        if isinstance(node, yaml.MappingNode):
            seen: set[str] = set()
            for key, value in node.value:
                name = str(key.value)
                if name in seen:
                    path = _pointer(parts)
                    message = _at(f"duplicate key {name!r}", key.start_mark)
                    raise PackInvalid([PackIssue(path, _short(message))])
                seen.add(name)
                stack.append((value, [*parts, name]))
        elif isinstance(node, yaml.SequenceNode):
            for index, item in enumerate(node.value):
                stack.append((item, [*parts, index]))


def read_yaml(text: str) -> object:
    """The YAML document as plain data; PackInvalid for anything else."""
    if len(text.encode("utf-8", "replace")) > MAX_PACK_BYTES:
        message = f"a pack may have at most {MAX_PACK_BYTES} bytes"
        raise PackInvalid([PackIssue("", message)])
    try:
        _check_events(text)
        _check_keys(yaml.compose(text, Loader=yaml.SafeLoader))
        return yaml.load(text, Loader=yaml.SafeLoader)
    except PackInvalid:
        raise
    except yaml.MarkedYAMLError as exc:
        message = _at(exc.problem or exc.context or "invalid YAML", exc.problem_mark)
        raise PackInvalid([PackIssue("", _short(message))]) from None
    except (yaml.YAMLError, ValueError):
        # ReaderError (a character YAML does not allow) and ValueError (an
        # integer of more than 4,300 digits) carry no position worth showing.
        raise PackInvalid([PackIssue("", "the text is not valid YAML")]) from None


@functools.cache
def _validator() -> Draft202012Validator:
    schema = json.loads(SCHEMA_PATH.read_text("utf-8"))
    Draft202012Validator.check_schema(schema)
    return Draft202012Validator(schema)


def schema_issues(document: object) -> list[PackIssue]:
    """What pack.schema.json finds wrong with the document, ordered by path."""
    found = {
        PackIssue(_pointer(list(error.absolute_path)), _short(error.message))
        for error in _validator().iter_errors(document)
    }
    return sorted(found, key=lambda issue: (issue.path, issue.message))


class _Compiler:
    """Builds the Pack from a document the schema accepted, collecting issues."""

    def __init__(self, document: dict[str, Any]) -> None:
        self.document = document
        self.issues: list[PackIssue] = []

    def pattern(self, path: str, source: str) -> regex.Pattern[str] | None:
        try:
            return regex.compile(source)
        except (regex.error, ValueError, OverflowError, RecursionError) as exc:
            message = f"not a valid regular expression: {exc}"
            self.issues.append(PackIssue(path, _short(message)))
            return None

    def conditions(self, key: str) -> tuple[Condition, ...]:
        found: list[Condition] = []
        for index, condition in enumerate(self.document["match"].get(key, [])):
            ((where, source),) = condition.items()
            path = f"/match/{key}/{index}/{where}"
            compiled = self.pattern(path, source)
            if compiled is not None:
                found.append(Condition(cast(Header, where), compiled, path))
        return tuple(found)

    def extractor(self, name: str, spec: dict[str, Any], path: str) -> Extractor | None:
        if ("regex" in spec) == ("literal" in spec):
            self.issues.append(PackIssue(path, "give either regex or literal"))
            return None
        if "literal" in spec:
            if "in" in spec or "format" in spec:
                message = "in and format apply to a regex, not to a literal"
                self.issues.append(PackIssue(path, message))
                return None
            return Extractor(name, path, literal=spec["literal"])
        compiled = self.pattern(f"{path}/regex", spec["regex"])
        if compiled is None:
            return None
        groups = list(compiled.groupindex)
        if len(groups) != 1:
            message = (
                "needs exactly one named group, such as (?P<value>...); "
                f"found {len(groups)}"
            )
            self.issues.append(PackIssue(f"{path}/regex", message))
            return None
        return Extractor(
            name,
            path,
            pattern=compiled,
            group=groups[0],
            where=cast(Scope, spec.get("in", "record")),
            time_format=spec.get("format"),
        )

    def extractors(self) -> tuple[tuple[Extractor, ...], tuple[Extractor, ...]]:
        extract: dict[str, Any] = self.document.get("extract", {})
        fields = [
            self.extractor(name, extract[name], f"/extract/{name}")
            for name in FIELDS
            if name in extract
        ]
        details = [
            self.extractor(name, spec, f"/extract/details/{name}")
            for name, spec in extract.get("details", {}).items()
        ]
        return (
            tuple(item for item in fields if item is not None),
            tuple(item for item in details if item is not None),
        )

    def status_rules(self) -> tuple[StatusRule, ...]:
        rules: list[StatusRule] = []
        for index, rule in enumerate(self.document["status_rules"]):
            path = f"/status_rules/{index}/regex"
            compiled = self.pattern(path, rule["regex"])
            if compiled is not None:
                where = cast(Scope, rule.get("in", "record"))
                rules.append(StatusRule(rule["status"], compiled, where, path))
        return tuple(rules)

    def fixtures(self) -> tuple[FixtureRef, ...]:
        refs: list[FixtureRef] = []
        names: set[str] = set()
        for index, item in enumerate(self.document.get("fixtures", [])):
            if item["name"] in names:
                path = f"/fixtures/{index}/name"
                self.issues.append(PackIssue(path, "fixture names must be unique"))
            names.add(item["name"])
            refs.append(FixtureRef(item["name"], item["origin"], item["class"]))
        if self.document["status"] == "verified":
            classes = {ref.kind for ref in refs}
            if len(classes) < VERIFIED_CLASSES:
                message = (
                    f"a verified pack needs fixtures of at least {VERIFIED_CLASSES} "
                    f"classes; found {len(classes)}"
                )
                self.issues.append(PackIssue("/fixtures", message))
        return tuple(refs)

    def pack(self) -> Pack:
        document = self.document
        match_all = self.conditions("all")
        match_any = self.conditions("any")
        split: regex.Pattern[str] | None = None
        if "split" in document:
            split = self.pattern("/split/record", document["split"]["record"])
        fields, details = self.extractors()
        status_rules = self.status_rules()
        fixtures = self.fixtures()
        if self.issues:
            raise PackInvalid(sorted(self.issues, key=lambda issue: issue.path))
        return Pack(
            id=document["id"],
            version=document["version"],
            vendor=document["vendor"],
            status=cast(PackStatus, document["status"]),
            docs_url=document.get("docs_url"),
            match_all=match_all,
            match_any=match_any,
            split=split,
            fields=fields,
            details=details,
            status_rules=status_rules,
            fixtures=fixtures,
        )


def parse_pack(text: str) -> Pack:
    """The compiled pack of a Pack YAML text. Raises PackInvalid."""
    document = read_yaml(text)
    issues = schema_issues(document)
    if issues:
        raise PackInvalid(issues)
    return _Compiler(cast(dict[str, Any], document)).pack()


def load_pack_file(path: Path) -> Pack:
    """A pack file; its id must be its file name without .yaml."""
    pack = parse_pack(path.read_text("utf-8"))
    if pack.id != path.stem:
        message = f"must be {path.stem!r}, the name of the file"
        raise PackInvalid([PackIssue("/id", message)])
    return pack


def builtin_packs(directory: Path = PACKS_DIR) -> tuple[Pack, ...]:
    """Every pack file of the directory, in file name order."""
    return tuple(load_pack_file(path) for path in sorted(directory.glob("*.yaml")))


def _time(value: object, where: str) -> datetime | None:
    if value is None:
        return None
    if not isinstance(value, str):
        raise ValueError(f"{where} must be an ISO 8601 text or null")
    parsed = datetime.fromisoformat(value)
    if parsed.utcoffset() is None:
        raise ValueError(f"{where} must carry a time zone")
    return parsed


def _text(value: object, where: str) -> str | None:
    if value is None or isinstance(value, str):
        return value
    raise ValueError(f"{where} must be a text or null")


_RESULT_KEYS: Final = frozenset({"status", "details", *FIELDS})


def expected_result(item: object, where: str) -> ParsedResult:
    """One result of an expected.json file (spans are not compared)."""
    if not isinstance(item, dict):
        raise ValueError(f"{where} must be an object")
    unknown = set(item) - _RESULT_KEYS
    if unknown:
        raise ValueError(f"{where} has unknown keys: {', '.join(sorted(unknown))}")
    status = item.get("status")
    if status not in RESULT_STATUSES:
        raise ValueError(f"{where}/status must be one of {', '.join(RESULT_STATUSES)}")
    details = item.get("details", {})
    if not isinstance(details, dict):
        raise ValueError(f"{where}/details must be an object")
    times = {name: _time(item.get(name), f"{where}/{name}") for name in TIME_FIELDS}
    return ParsedResult(
        status=status,
        job_name=_text(item.get("job_name"), f"{where}/job_name"),
        client_hint=_text(item.get("client_hint"), f"{where}/client_hint"),
        run_id=_text(item.get("run_id"), f"{where}/run_id"),
        started_at=times["started_at"],
        finished_at=times["finished_at"],
        details=details,
    )


def _expected(path: Path) -> tuple[ParsedResult, ...]:
    items = json.loads(path.read_text("utf-8"))
    if not isinstance(items, list):
        raise ValueError(f"{path.name} must hold a list of results")
    return tuple(
        expected_result(item, f"{path.name}/{index}")
        for index, item in enumerate(items)
    )


def pack_fixtures(pack: Pack, directory: Path = FIXTURES_DIR) -> Iterator[Fixture]:
    """The fixtures the pack lists: <directory>/<pack id>/<name>.eml and
    <name>.expected.json. A missing or malformed file raises."""
    folder = directory / pack.id
    for ref in pack.fixtures:
        yield Fixture(
            pack_id=pack.id,
            name=ref.name,
            origin=ref.origin,
            kind=ref.kind,
            raw=(folder / f"{ref.name}.eml").read_bytes(),
            expected=_expected(folder / f"{ref.name}.expected.json"),
        )
