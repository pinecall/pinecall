"""Contact memory: the facts recalled per turn, read whole, written as ops, ended and forgotten."""

import dataclasses
import math
import uuid
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime
from typing import Literal, Protocol

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from runtime.actor import Scope
from runtime.billing import service as billing
from runtime.compliance import service as compliance
from runtime.enums import Env, ReadKind
from runtime.exceptions import NotFound, ValidationError
from runtime.kit.time import A_DAY_S, now
from runtime.knowledge.models import ContactMemory
from runtime.knowledge.repository import FactFound, Hit, MemoryRepository
from runtime.knowledge.service import ranking
from runtime.knowledge.service.embedder import Embedder

DEFAULT_FACTS_PER_TURN = 6
# A fact learned a half-life ago weighs half of one learned now.
HALF_LIFE_DAYS = 90
# How many facts one request of the embedder embeds again.
REEMBED_BATCH = 64

# There is no delete: a fact is only ever superseded or ended, and the history keeps it.
type OpName = Literal["add", "update", "invalidate"]
OP_NAMES: tuple[OpName, ...] = ("add", "update", "invalidate")
WRITES: frozenset[OpName] = frozenset({"add", "update"})
NAMES_A_FACT: frozenset[OpName] = frozenset({"update", "invalidate"})


class NoSuchFact(NotFound):
    """No current fact by that id in the scope."""

    # One sentence for a fact missing, already ended, or another org's: nothing is told apart.
    def __init__(self, fact_id: uuid.UUID) -> None:
        super().__init__(f"no current fact {fact_id} in this key's org and env")


@dataclass(frozen=True, slots=True)
class RecalledFact:
    """A fact recalled, and its score relative to the best of the recall."""

    fact: FactFound
    score: float


@dataclass(frozen=True, slots=True)
class Recall:
    """A recall of one contact's facts: the query, the moment recency is measured from, and how many."""

    contact: str
    query: str
    at: datetime
    k: int = DEFAULT_FACTS_PER_TURN


@dataclass(frozen=True, slots=True)
class Taught:
    """When a contact's memory was taught, and on which call: what every written fact carries."""

    contact: str
    call: str | None
    at: datetime


@dataclass(frozen=True, slots=True)
class Op:
    """One change the extraction model asked of a contact's memory."""

    op: OpName
    text: str = ""
    category: str | None = None
    of: str | None = None


# Until 2026-11 the vectors travelled beside the ops as a list of their own, read one at a time as
# each fact was written: an update whose row had ended in the meantime was skipped before its vector
# was read, and every fact after it was kept under the vector of the one before, with no error.
@dataclass(frozen=True, slots=True)
class EmbeddedOp:
    """An op and the vector of its text; None for an op that writes no text."""

    op: Op
    vector: list[float] | None = None


# Memory has no fallback to the org's own facts: a scope recalls its own or nothing. The vendor is
# asked before the transaction opens, so no connection waits on it.
async def recall(
    sessions: async_sessionmaker[AsyncSession], embedder: Embedder, scope: Scope, request: Recall
) -> list[RecalledFact]:
    """The contact's best facts for the query: both branches fused, then recency and confidence."""
    (vector,) = await embedder.embed([request.query])
    async with sessions.begin() as session:
        return await recall_by_vector(session, scope, request, vector, model=embedder.model)


async def recall_by_vector(
    session: AsyncSession, scope: Scope, request: Recall, vector: Sequence[float], *, model: str
) -> list[RecalledFact]:
    """The recall for a query whose vector is in hand, among the facts the same model embedded."""
    hits = await MemoryRepository(session).recall(
        scope, request.contact, model=model, vector=vector, words=request.query, room=ranking.CANDIDATES_PER_BRANCH
    )
    return rank(hits, at=request.at, k=request.k)


def rank(hits: Sequence[Hit[FactFound]], *, at: datetime, k: int) -> list[RecalledFact]:
    """The k best hits once each is weighed by recency and confidence, relative to the best."""
    weighed = [
        dataclasses.replace(hit, fused=hit.fused * recency(hit.row.valid_from, at) * hit.row.confidence) for hit in hits
    ]
    return [RecalledFact(fact=hit.row, score=hit.fused) for hit in ranking.relative_to_the_best(weighed)[:k]]


def recency(learned: datetime, at: datetime) -> float:
    """1.0 for a fact learned now, halving every half-life; a date after now counts as now."""
    days = max((at - learned).total_seconds(), 0.0) / A_DAY_S
    return math.pow(0.5, days / HALF_LIFE_DAYS)


async def list_current(session: AsyncSession, scope: Scope, contact: str) -> Sequence[ContactMemory]:
    """The contact's facts that hold now, oldest first."""
    return await MemoryRepository(session).list_current(scope, contact)


# The whole history, superseded facts included; a call reads the current ones through `recall`.
async def read_history(session: AsyncSession, scope: Scope, contact: str, *, by: str) -> Sequence[ContactMemory]:
    """Every fact ever kept of the contact in the scope, current first, newest first; the read is written down."""
    await compliance.record_read(session, scope, contact, ReadKind.memory, by=by)
    return await MemoryRepository(session).list_history(scope, contact)


# ── the facts calls taught, a page at a time ──


# Which agent taught a fact is said by the head of the call that taught it, and the heads are
# `calls`', above this domain: the endpoint asks them for the rows, and the page is cut here.
class TaughtFact(Protocol):
    """A current fact, and the agent whose call taught it."""

    @property
    def fact(self) -> ContactMemory:
        """The fact as memory keeps it."""
        ...

    @property
    def agent(self) -> str:
        """The agent whose call taught it."""
        ...


@dataclass(frozen=True, slots=True)
class TaughtPage:
    """A page of facts with who taught each, newest first, and the cursor of the next."""

    facts: Sequence[TaughtFact]
    next: str | None


# Asked for with one row more than it shows: the row past the limit says another page follows.
def page_taught(rows: Sequence[TaughtFact], limit: int) -> TaughtPage:
    """The page out of `limit + 1` rows read, and the cursor of its last fact when more follow."""
    shown = rows[:limit]
    return TaughtPage(facts=shown, next=cursor_of(shown[-1].fact) if len(rows) > limit else None)


def cursor_of(fact: ContactMemory) -> str:
    """The cursor a page of facts answers as `next`: the fact's validity start and its id."""
    return f"{fact.valid_from.isoformat()}|{fact.id}"


def parse_cursor(after: str | None) -> tuple[datetime, uuid.UUID] | None:
    """The `next` a page answered, read back; None for the first page."""
    if not after:
        return None
    moment, _, named = after.partition("|")
    try:
        return datetime.fromisoformat(moment), uuid.UUID(named)
    except ValueError as unread:
        raise ValidationError(f"{after!r} is not a cursor: pass the `next` a page answered, or nothing") from unread


def like_pattern(words: str | None) -> str | None:
    """The words as a LIKE pattern anywhere in a text, its wildcards escaped; None for no words."""
    if not words:
        return None
    return "%" + words.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_") + "%"


async def count_facts(session: AsyncSession, org: str, env: Env) -> int:
    """How many current facts the org keeps in the env, across every holder and contact."""
    return await MemoryRepository(session).count_current(org, env)


# The stock is held while it is counted, so two hang-ups at the cap are counted in turn. A memory at
# its cap keeps nothing new and is still read: a cap is about keeping.
async def admit_fact(session: AsyncSession, scope: Scope) -> None:
    """Admit one more fact into the org's memory in the env, its stock held for this transaction."""
    await billing.hold_stock(session, scope.org, scope.env, "memory_facts")
    await billing.admit_memory(session, scope.org, scope.env, kept=await count_facts(session, scope.org, scope.env))


# Every row, superseded ones included: an erasure that left the history would erase nothing. Reading
# and erasing are the contact's rights: no quota ever refuses them.
async def forget(session: AsyncSession, scope: Scope, contact: str) -> int:
    """Delete every fact of the contact in the scope; how many went, zero included."""
    return await MemoryRepository(session).delete_of_contact(scope, contact)


# The row stays, ended: the history still shows it.
async def invalidate(session: AsyncSession, scope: Scope, fact_id: uuid.UUID) -> None:
    """End one current fact of the scope from now on; refused when there is none by that id."""
    if not await MemoryRepository(session).end(scope, fact_id, at=now()):
        raise NoSuchFact(fact_id)


# Embedded before anything is written: an update never ends a fact without its replacement.
async def embed_ops(embedder: Embedder, ops: Sequence[Op]) -> list[EmbeddedOp]:
    """Each op with the vector of its text, the adds and updates embedded in one go."""
    writing = [op for op in ops if op.op in WRITES]
    vectors = iter(await embedder.embed([op.text for op in writing]) if writing else [])
    return [EmbeddedOp(op, next(vectors) if op.op in WRITES else None) for op in ops]


async def apply_ops(
    session: AsyncSession, scope: Scope, taught: Taught, ops: Sequence[EmbeddedOp], *, model: str
) -> list[ContactMemory]:
    """Write the ops as one: an update ends the row it replaces, an invalidate ends one; the facts written."""
    repository = MemoryRepository(session)
    written: list[ContactMemory] = []
    for embedded in ops:
        op = embedded.op
        superseded = None
        if op.of is not None:
            superseded = await repository.find_current(scope, uuid.UUID(op.of))
            # Nothing is written when the old row had already ended.
            if superseded is None:
                continue
            superseded.invalidated_at = taught.at
        if embedded.vector is None:
            continue
        fact = ContactMemory(
            org=scope.org,
            env=scope.env,
            holder=scope.holder,
            contact=taught.contact,
            text=op.text,
            category=op.category,
            embedding=embedded.vector,
            valid_from=taught.at,
            source_call=taught.call,
            model=model,
            supersedes=None if superseded is None else superseded.id,
        )
        written.append(await repository.add(fact))
    await session.flush()
    return written


# One batch a call, in transactions of its own: a failure leaves the batches before it written, and a
# second run skips them. Asked from the box's own terminal, which names no org: facts of every org and env.
async def embed_stale(
    sessions: async_sessionmaker[AsyncSession], embedder: Embedder, *, batch: int = REEMBED_BATCH
) -> int:
    """Embed again one batch of the facts another model wrote; how many it was, zero when none is left."""
    async with sessions.begin() as session:
        stale = [(row.id, row.text) for row in await MemoryRepository(session).list_stale(embedder.model, batch)]
    if not stale:
        return 0
    vectors = await embedder.embed([text for _, text in stale])
    async with sessions.begin() as session:
        repository = MemoryRepository(session)
        for (fact_id, _), vector in zip(stale, vectors, strict=True):
            await repository.put_embedding(fact_id, vector, embedder.model)
    return len(stale)


def fold_text(text: str) -> str:
    """The text case-folded with its spaces squeezed: how two sentences are compared."""
    return " ".join(text.casefold().split())
