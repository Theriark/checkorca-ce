"""The parse hook (phase C5-B): pending messages to results, on every tick.

1. The built-in packs are written to parser_pack (nothing is written when no
   pack changed), then the enabled packs come from the ParserPackSource and
   are compiled on the parser thread; a pack that no longer loads is left out
   and logged.
2. The matcher is built once over the jobs and clients that are not archived.
3. Up to PARSE_BATCH messages, oldest first, one at a time, for at most
   PARSE_BUDGET seconds: the message is taken with FOR UPDATE SKIP LOCKED,
   parsed on the parser thread and its outcome stored in the same
   transaction. The budget keeps a tick well inside TICK_SECONDS, so the
   heartbeat stays fresh and the hooks after this one run on time, even when
   every mail takes the full 5 s engine deadline (a slow custom pack); the
   messages left over wait for the next tick.

Parsed: record_result for each result, bound to its job when the matcher is
sure, parse_state parsed, and client_id when every result belongs to one
client. Unmatched: parse_state unmatched with the reason (no-pack, tie,
no-records). ParseFailed: parse_state error with the reason (timeout,
deadline, too-many-records, memory) and the JSON Pointer of the pattern.

One parser thread parses one mail at a time: the regex module measures its
50 ms timeout in CPU time of the whole process (docs/parsers.md), so two
parses at once would halve each other's time. The test bench never runs here
(app/api/bench.py). A message that fails in any other way (a stored message
that cannot be read, a result the table refuses) is marked error with reason
unreadable, rejected or internal; it never stops the tick.
"""

import asyncio
import logging
from collections.abc import Callable, Sequence
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime
from typing import TYPE_CHECKING, Final

from sqlalchemy.ext.asyncio import AsyncSession

from app.access import SYSTEM
from app.db.models import RawMessage
from app.ext.parsers import PackText
from app.ingest.store import MessageTooLarge, ResultRejected, raw_bytes, record_result
from app.matcher import Bound, Matcher
from app.parsers.engine import Outcome, Parsed, ParseFailed, mail_from_raw, parse
from app.parsers.loader import PackInvalid, builtin_pack_texts, parse_pack_cached
from app.parsers.model import Pack
from app.repos.jobs import JobRepository
from app.repos.messages import RawMessageRepository
from app.repos.packs import PackRepository

if TYPE_CHECKING:
    from app.worker.loop import WorkerContext

# Messages parsed in one tick; the rest wait for the next one.
PARSE_BATCH: Final = 200
# Seconds of one tick no new message starts after (monotonic clock). One
# message started just before may still take the 5 s engine deadline.
PARSE_BUDGET: Final = 30.0

logger = logging.getLogger(__name__)

# The parser thread: one, for the whole process.
_PARSER: Final = ThreadPoolExecutor(max_workers=1, thread_name_prefix="parser")


async def on_parser_thread[T](function: Callable[..., T], *args: object) -> T:
    """Run function on the parser thread and wait for it."""
    loop = asyncio.get_running_loop()
    return await loop.run_in_executor(_PARSER, function, *args)


def compile_packs(texts: Sequence[PackText]) -> tuple[Pack, ...]:
    """The packs that load; one that does not is logged and left out."""
    packs: list[Pack] = []
    for text in texts:
        try:
            packs.append(parse_pack_cached(text.yaml))
        except PackInvalid as invalid:
            logger.error(
                "parser pack %s does not load (%d issues); left out",
                text.id,
                len(invalid.issues),
            )
    return tuple(packs)


def parse_message(packs: Sequence[Pack], body_zlib: bytes) -> Outcome:
    """The outcome for one stored message (runs on the parser thread)."""
    return parse(packs, mail_from_raw(raw_bytes(body_zlib)))


class ParseHook:
    """The tick hook. The packs come from context.pack_source; batch is the
    number of messages a tick parses at most, budget the seconds after which
    it starts no new one."""

    def __init__(self, batch: int = PARSE_BATCH, budget: float = PARSE_BUDGET) -> None:
        self.batch = batch
        self.budget = budget

    async def __call__(self, context: "WorkerContext", now: datetime) -> None:
        stop_at = context.clock.monotonic() + self.budget
        async with context.sessionmaker() as db:
            await PackRepository(db, context.policy).sync_builtin(
                SYSTEM, await asyncio.to_thread(builtin_pack_texts), now
            )
            await db.commit()
            texts = await context.pack_source.packs(db, context.policy, SYSTEM)
            matcher = await JobRepository(db, context.policy).matcher(SYSTEM)
        packs = await on_parser_thread(compile_packs, texts)
        for parsed in range(self.batch):
            if context.clock.monotonic() >= stop_at:
                logger.info("parse budget spent after %d messages", parsed)
                break
            if not await self.parse_next(context, packs, matcher, now):
                break

    async def parse_next(
        self,
        context: "WorkerContext",
        packs: Sequence[Pack],
        matcher: Matcher,
        now: datetime,
    ) -> bool:
        """Parse the oldest pending message; False when none waits."""
        async with context.sessionmaker() as db:
            messages = RawMessageRepository(db, context.policy)
            message = await messages.next_pending(SYSTEM)
            if message is None:
                return False
            message_id = message.id
            try:
                outcome = await on_parser_thread(
                    parse_message, packs, message.body_zlib
                )
                await store_outcome(db, context, message, outcome, matcher, now)
                await db.commit()
                return True
            except MessageTooLarge:
                reason = "unreadable"
            except ResultRejected:
                reason = "rejected"
            except Exception as error:
                logger.error("parsing message %s failed", message_id, exc_info=error)
                reason = "internal"
            await db.rollback()
            await messages.fail_pending(SYSTEM, message_id, reason, now)
            await db.commit()
        logger.warning("message %s left unparsed: %s", message_id, reason)
        return True


async def store_outcome(
    db: AsyncSession,
    context: "WorkerContext",
    message: RawMessage,
    outcome: Outcome,
    matcher: Matcher,
    now: datetime,
) -> None:
    """Store what the parser made of the message, in the caller's transaction."""
    messages = RawMessageRepository(db, context.policy)
    if isinstance(outcome, Parsed):
        for result in outcome.results:
            found = matcher.match(result.job_name, result.client_hint)
            job_id = found.job_id if isinstance(found, Bound) else None
            await record_result(
                db,
                context.policy,
                SYSTEM,
                result,
                received_at=message.received_at,
                job_id=job_id,
                raw_message_id=message.id,
            )
        await messages.record_parse(
            SYSTEM, message, state="parsed", at=now, pack_id=outcome.pack_id
        )
        await messages.refresh_client(SYSTEM, message.id)
    elif isinstance(outcome, ParseFailed):
        await messages.record_parse(
            SYSTEM,
            message,
            state="error",
            at=now,
            pack_id=outcome.pack_id,
            reason=outcome.reason,
            path=outcome.path,
        )
    else:
        await messages.record_parse(
            SYSTEM, message, state="unmatched", at=now, reason=outcome.reason
        )


parse_messages = ParseHook()
