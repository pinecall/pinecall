"""Contact memory: the facts recalled per turn, held and forgotten, and its goldens."""

import dataclasses
import math
import time
import unicodedata
import uuid
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from datetime import datetime
from typing import Literal

from sqlalchemy.ext.asyncio import AsyncSession

from pinecall_runtime.enums import Env
from pinecall_runtime.exceptions import ValidationError
from pinecall_runtime.kit.auth import Scope
from pinecall_runtime.knowledge.models import ContactMemory
from pinecall_runtime.knowledge.repository import Hit, MemoryRepository
from pinecall_runtime.knowledge.service import ranking
from pinecall_runtime.knowledge.service.embedder import Embedder, halfvec
from pinecall_runtime.knowledge.service.ranking import Evidence, Figures

DEFAULT_FACTS_PER_TURN = 6
# A fact learned a half-life ago weighs half of one learned now.
HALF_LIFE_DAYS = 90
A_DAY_S = 86_400

# There is no delete: a fact is only ever superseded or ended, and the history keeps it.
type OpName = Literal["add", "update", "invalidate"]
OP_NAMES: tuple[OpName, ...] = ("add", "update", "invalidate")
WRITES: frozenset[OpName] = frozenset({"add", "update"})
NAMES_A_FACT: frozenset[OpName] = frozenset({"update", "invalidate"})


@dataclass(frozen=True, slots=True)
class RecalledFact:
    """A fact recalled, and its score relative to the best of the recall."""

    fact: ContactMemory
    score: float


@dataclass(frozen=True, slots=True)
class Recalled:
    """What a recall found, best first, and how strongly the best vector says it answers."""

    facts: list[RecalledFact]
    top_cosine: float
    evidence: Evidence


@dataclass(frozen=True, slots=True)
class Recall:
    """A recall of one contact's facts: the query, the moment, how many, and what held when."""

    contact: str
    query: str
    at: datetime
    k: int = DEFAULT_FACTS_PER_TURN
    # Reads the facts that held at that moment rather than the current ones.
    as_of: datetime | None = None


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


@dataclass(frozen=True, slots=True)
class FactsPage:
    """A page of facts, newest first, the cursor of the next, and the agent that taught each."""

    facts: list[ContactMemory]
    next: str | None
    agents: Mapping[str, str] = field(default_factory=dict[str, str])


@dataclass(frozen=True, slots=True)
class GoldenQuestion:
    """One question of a memory golden: what memory holds, what is asked, what should come back."""

    holds: tuple[str, ...]
    asks: str
    expects: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class Answered:
    """A golden's question, and the texts of the facts recalled for it, best first."""

    question: GoldenQuestion
    found: tuple[str, ...]

    # Only the first fact that says it counts: memory repeating itself answered once.
    @property
    def ranks(self) -> tuple[int | None, ...]:
        """The rank of each expected fact, from 1, or None when it was not recalled."""
        return tuple(
            next((at for at, text in enumerate(self.found, 1) if says(text, expected)), None)
            for expected in self.question.expects
        )

    @property
    def missing(self) -> tuple[str, ...]:
        """The expected facts that were not recalled."""
        return tuple(expected for expected, rank in zip(self.question.expects, self.ranks, strict=True) if rank is None)


@dataclass(frozen=True, slots=True)
class Score:
    """A memory golden's figures over every question, the questions it missed, how long it took."""

    questions: int
    k: int
    figures: Figures
    misses: tuple[Answered, ...]
    took_ms: float = 0.0


# Memory has no fallback to the org's own facts: a scope recalls its own or nothing.
async def recall(session: AsyncSession, embedder: Embedder, scope: Scope, request: Recall) -> Recalled:
    """The contact's best facts for the query: both branches fused, then recency and confidence."""
    (vector,) = await embedder.embed([request.query])
    hits = await MemoryRepository(session).recall(
        scope,
        request.contact,
        model=embedder.model,
        as_of=request.as_of,
        vector=halfvec(vector),
        words=request.query,
        room=ranking.CANDIDATES_PER_BRANCH,
    )
    # A cosine against another model's vector measures nothing.
    best = ranking.top_cosine([hit for hit in hits if hit.row["model"] == embedder.model])
    return Recalled(
        facts=ranked(hits, now=request.as_of or request.at, k=request.k),
        top_cosine=best,
        evidence=ranking.evidence_of(best),
    )


def ranked(hits: Sequence[Hit], *, now: datetime, k: int) -> list[RecalledFact]:
    """The k best hits once each is weighed by recency and confidence, relative to the best."""
    weighed = [
        dataclasses.replace(hit, fused=hit.fused * recency(hit.row["valid_from"], now) * hit.row["confidence"])
        for hit in hits
    ]
    return [RecalledFact(fact=_fact_of(hit.row), score=hit.fused) for hit in ranking.relative_to_the_best(weighed)[:k]]


def recency(learned: datetime, now: datetime) -> float:
    """1.0 for a fact learned now, halving every half-life; a date after now counts as now."""
    days = max((now - learned).total_seconds(), 0.0) / A_DAY_S
    return math.pow(0.5, days / HALF_LIFE_DAYS)


async def current(session: AsyncSession, scope: Scope, contact: str) -> Sequence[ContactMemory]:
    """The contact's facts that hold now, oldest first."""
    return await MemoryRepository(session).current(scope, contact)


async def history(session: AsyncSession, scope: Scope, contact: str) -> Sequence[ContactMemory]:
    """Every fact ever kept of the contact in the scope, current first, newest first."""
    return await MemoryRepository(session).history(scope, contact)


async def facts_kept(session: AsyncSession, org: str, env: Env) -> int:
    """How many current facts the org keeps in the env, across every holder and contact."""
    return await MemoryRepository(session).kept_by_org(org, env)


async def hold(
    session: AsyncSession, embedder: Embedder, scope: Scope, contact: str, sentences: Sequence[str], *, at: datetime
) -> list[ContactMemory]:
    """The sentences written as the contact's facts, embedded, with no model asked."""
    vectors = await embedder.embed(list(sentences)) if sentences else []
    taught = Taught(contact=contact, call=None, at=at)
    ops = [Op(op="add", text=text) for text in sentences]
    return await _write_ops(session, embedder, scope, taught, ops, vectors)


# Every row, superseded ones included: an erasure that left the history would erase nothing.
async def forget(session: AsyncSession, scope: Scope, contact: str) -> int:
    """Delete every fact of the contact in the scope; how many went, zero included."""
    return await MemoryRepository(session).forget(scope, contact)


async def invalidate(session: AsyncSession, scope: Scope, fact_id: uuid.UUID, *, at: datetime) -> bool:
    """End one current fact of the scope at `at`; False when there is none by that id."""
    return await MemoryRepository(session).end(scope, fact_id, at=at)


# One batch per transaction: a failure leaves the batches before it written, and a second run
# skips them.
async def reembed(session: AsyncSession, embedder: Embedder, *, batch: int = 64) -> int:
    """Re-embed every fact another model wrote, in every org and env; how many there were."""
    repository = MemoryRepository(session)
    done = 0
    while True:
        rows = await repository.stale(embedder.model, batch)
        if not rows:
            return done
        vectors = await embedder.embed([row.text for row in rows])
        for row, vector in zip(rows, vectors, strict=True):
            row.embedding, row.model = vector, embedder.model
        await session.commit()
        done += len(rows)


async def ask_golden(
    session: AsyncSession,
    embedder: Embedder,
    scope: Scope,
    questions: Sequence[GoldenQuestion],
    k: int,
    *,
    at: datetime,
) -> Score:
    """Each question's facts written to a scratch contact, recalled, scored, and forgotten."""
    scratch = f"golden-{uuid.uuid4().hex}"
    started = time.perf_counter()
    answered: list[Answered] = []
    try:
        for question in questions:
            await hold(session, embedder, scope, scratch, question.holds, at=at)
            recalled = await recall(session, embedder, scope, Recall(scratch, question.asks, at=at, k=k))
            await forget(session, scope, scratch)
            answered.append(Answered(question=question, found=tuple(item.fact.text for item in recalled.facts)))
    finally:
        await forget(session, scope, scratch)
    score = score_memory(answered, k)
    return dataclasses.replace(score, took_ms=(time.perf_counter() - started) * 1000)


def score_memory(answered: Sequence[Answered], k: int) -> Score:
    """recall@k and nDCG@10 over every question; a question missing any expected fact is a miss."""
    return Score(
        questions=len(answered),
        k=k,
        figures=ranking.figures([item.ranks for item in answered]),
        misses=tuple(item for item in answered if None in item.ranks),
    )


# Facts are written by a model, so the golden is held to containment, one direction: a fact that
# says less than expected is a miss.
def says(found: str, expected: str) -> bool:
    """Whether a recalled fact contains the expected text, accents, case and spacing aside."""
    return _unaccented(expected) in _unaccented(found)


# Embedded before anything is written: an update never ends a fact without its replacement.
async def apply_ops(
    session: AsyncSession, embedder: Embedder, scope: Scope, taught: Taught, ops: Sequence[Op]
) -> list[ContactMemory]:
    """Write the ops as one: adds and updates embedded first; an update ends the row it replaces."""
    writing = [op for op in ops if op.op in WRITES]
    vectors = await embedder.embed([op.text for op in writing]) if writing else []
    return await _write_ops(session, embedder, scope, taught, ops, vectors)


def fold_text(text: str) -> str:
    """The text case-folded with its spaces squeezed: how two sentences are compared."""
    return " ".join(text.casefold().split())


async def _write_ops(
    session: AsyncSession,
    embedder: Embedder,
    scope: Scope,
    taught: Taught,
    ops: Sequence[Op],
    vectors: Sequence[list[float]],
) -> list[ContactMemory]:
    repository = MemoryRepository(session)
    vector_of = iter(vectors)
    written: list[ContactMemory] = []
    for op in ops:
        superseded = None
        if op.of is not None:
            superseded = await repository.get_current(scope, uuid.UUID(op.of))
            # Nothing is written when the old row had already ended.
            if superseded is None:
                continue
            superseded.invalidated_at = taught.at
        if op.op == "invalidate":
            continue
        fact = ContactMemory(
            org=scope.org,
            env=scope.env,
            holder=scope.holder,
            contact=taught.contact,
            text=op.text,
            category=op.category,
            embedding=next(vector_of),
            valid_from=taught.at,
            source_call=taught.call,
            model=embedder.model,
            supersedes=None if superseded is None else superseded.id,
        )
        written.append(await repository.add(fact))
    await session.flush()
    return written


def _fact_of(row: Mapping[str, object]) -> ContactMemory:
    return ContactMemory(
        id=row["id"],
        contact=row["contact"],
        category=row["category"],
        text=row["text"],
        valid_from=row["valid_from"],
        invalidated_at=row["invalidated_at"],
        supersedes=row["supersedes"],
        source_call=row["source_call"],
        model=row["model"],
        confidence=row["confidence"],
    )


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
    return "%" + _like_escaped(words) + "%"


def _like_escaped(words: str) -> str:
    return words.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")


def _unaccented(text: str) -> str:
    characters = unicodedata.normalize("NFD", text)
    return fold_text("".join(item for item in characters if not unicodedata.combining(item)))
