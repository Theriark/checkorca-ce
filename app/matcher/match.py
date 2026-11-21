"""Which job a result belongs to (phase C5).

A result names its job (job_name) and often its client (client_hint) in the
words of the tool that sent it. Both are compared as tokens: the text in
Unicode NFKC form, case folded, and split at every run of punctuation, symbols
and spaces, so "Nightly-Backup" and "nightly backup" are the same name and
"Backup 1" and "Backup 11" are not. A job is known by its match_key and by its
name; a client by its name and its aliases.

- job_name must equal a job's match_key or its name, token for token;
- with a client_hint, the job's client must have a name or an alias equal to
  it; without one, no other job may have that name;
- exactly one such job binds the result. None, or more than one, is no
  confident match and the result waits in Unmatched.

Pure code: the caller loads the jobs and clients (JobRepository.matcher).
"""

import re
import unicodedata
import uuid
from collections.abc import Iterable
from dataclasses import dataclass
from typing import Final, Literal

# Every run of characters that is not a letter or a digit separates tokens.
_SEPARATORS: Final = re.compile(r"[\W_]+")

type Tokens = tuple[str, ...]
NoMatchReason = Literal["no-job-name", "no-job", "no-client", "ambiguous"]


def tokens(text: str | None) -> Tokens:
    """The words of a name as the matcher compares them."""
    if not text:
        return ()
    folded = unicodedata.normalize("NFKC", text).casefold()
    return tuple(part for part in _SEPARATORS.split(folded) if part)


def same_names(
    first: tuple[str | None, str | None], second: tuple[str | None, str | None]
) -> bool:
    """Whether two (job_name, client_hint) pairs name the same job the same
    way: the "identical mail" of assign and create-job."""
    return all(tokens(a) == tokens(b) for a, b in zip(first, second, strict=True))


def names_client(name: str, aliases: Iterable[str], client_hint: str | None) -> bool:
    """Whether the hint is the client's name or one of its aliases; an empty
    hint names every client."""
    hint = tokens(client_hint)
    return not hint or hint == tokens(name) or any(hint == tokens(a) for a in aliases)


@dataclass(frozen=True, slots=True)
class JobRef:
    """A job the matcher may bind to (not archived, of a client not archived)."""

    id: uuid.UUID
    client_id: uuid.UUID
    name: str
    match_key: str | None = None


@dataclass(frozen=True, slots=True)
class ClientRef:
    id: uuid.UUID
    name: str
    aliases: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class Bound:
    """The result belongs to this job of this client."""

    job_id: uuid.UUID
    client_id: uuid.UUID


@dataclass(frozen=True, slots=True)
class NoMatch:
    """No confident match: no job name, no job of that name, no job of that
    name for that client, or more than one job."""

    reason: NoMatchReason


class Matcher:
    """Binds results to jobs; built once for many results (a worker tick)."""

    def __init__(self, jobs: Iterable[JobRef], clients: Iterable[ClientRef]) -> None:
        self._jobs: dict[Tokens, list[JobRef]] = {}
        for job in jobs:
            keys = {tokens(job.name), tokens(job.match_key)}
            for key in keys:
                if key:
                    self._jobs.setdefault(key, []).append(job)
        self._clients: dict[uuid.UUID, frozenset[Tokens]] = {}
        for client in clients:
            names = (tokens(client.name), *(tokens(alias) for alias in client.aliases))
            self._clients[client.id] = frozenset(name for name in names if name)

    def match(self, job_name: str | None, client_hint: str | None) -> Bound | NoMatch:
        name = tokens(job_name)
        if not name:
            return NoMatch("no-job-name")
        candidates = self._jobs.get(name, [])
        if not candidates:
            return NoMatch("no-job")
        hint = tokens(client_hint)
        if hint:
            candidates = [
                job
                for job in candidates
                if hint in self._clients.get(job.client_id, frozenset())
            ]
            if not candidates:
                return NoMatch("no-client")
        if len(candidates) > 1:
            return NoMatch("ambiguous")
        (job,) = candidates
        return Bound(job.id, job.client_id)
