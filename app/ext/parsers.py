"""Parser seam (rnd-report-2 5.3): ParserPackSource.

Which packs parse mail, in the order they are tried. CE ships TablePackSource:
the enabled built-in and custom packs of the parser_pack table. EE can add
packs from elsewhere (a signed vendor pack feed) without changing the worker
or the test bench, which compile what the source gives with the same loader
and the same bounds.

Frozen with the other seams in phase C12 (EXTENSION_API_LEVEL 1).
"""

from collections.abc import Sequence
from dataclasses import dataclass
from typing import Protocol

from sqlalchemy.ext.asyncio import AsyncSession

from app.access import AccessPolicy, Principal
from app.repos.packs import PackRepository


@dataclass(frozen=True, slots=True)
class PackText:
    """A pack as Pack YAML text, and where it comes from (builtin or custom)."""

    id: str
    source: str
    yaml: str


class ParserPackSource(Protocol):
    """Gives the packs that parse mail."""

    async def packs(
        self, db: AsyncSession, policy: AccessPolicy, principal: Principal
    ) -> Sequence[PackText]:
        """The enabled packs, in the order the engine tries them."""
        ...


class TablePackSource:
    """CE: the enabled packs of the parser_pack table, ordered by id."""

    async def packs(
        self, db: AsyncSession, policy: AccessPolicy, principal: Principal
    ) -> Sequence[PackText]:
        rows = await PackRepository(db, policy).enabled(principal)
        return [PackText(row.id, row.source, row.yaml) for row in rows]
