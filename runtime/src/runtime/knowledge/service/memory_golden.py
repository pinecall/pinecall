"""Memory held to its golden: each question's facts written to a scratch contact, recalled, scored, forgotten."""

import time
import unicodedata
import uuid
from collections.abc import Sequence
from dataclasses import dataclass

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from runtime.actor import Scope
from runtime.kit.time import now
from runtime.knowledge.service import figures, memory
from runtime.knowledge.service.embedder import Embedder
from runtime.knowledge.service.memory import EmbeddedOp, Op, Recall, Taught, fold_text


# A question brings its own facts: written to a scratch contact, asked, and forgotten.
@dataclass(frozen=True, slots=True)
class Question:
    """One question of a memory golden: what memory holds, what is asked, what should come back."""

    holds: tuple[str, ...]
    asks: str
    expects: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class Answered:
    """A golden's question, and the texts of the facts recalled for it, best first."""

    question: Question
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
class Miss:
    """One question memory did not answer whole: what it missed, and what came back instead."""

    asks: str
    missing: tuple[str, ...]
    found: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class Score:
    """A memory golden's figures over every question, and the questions it missed."""

    questions: int
    k: int
    recall_at_k: float
    ndcg_at_10: float
    misses: list[Miss]


@dataclass(frozen=True, slots=True)
class Run:
    """A memory golden as it is answered: the model that embedded it, the score, how long it took."""

    model: str
    questions: int
    k: int
    recall_at_k: float
    ndcg_at_10: float
    misses: list[Miss]
    took_ms: float


# Every sentence and every question embedded before the first statement, so no connection waits on
# the vendor. Then one transaction: a question's facts are written to a contact nobody has, recalled
# by the ranking a call reads, and deleted before the next. They are never committed: a run that
# fails half-way rolls its facts back, and none is ever seen in the tenant's memory.
async def run(
    sessions: async_sessionmaker[AsyncSession], embedder: Embedder, scope: Scope, questions: Sequence[Question], k: int
) -> Run:
    """Each question's facts written to a scratch contact, recalled, scored, and forgotten."""
    scratch = f"golden-{uuid.uuid4().hex}"
    started = time.perf_counter()
    at = now()
    held = iter(await embedder.embed([sentence for question in questions for sentence in question.holds]))
    asked = await embedder.embed([question.asks for question in questions])
    taught = Taught(contact=scratch, call=None, at=at)
    answered: list[Answered] = []
    async with sessions.begin() as session:
        for question, vector in zip(questions, asked, strict=True):
            ops = [EmbeddedOp(Op(op="add", text=text), next(held)) for text in question.holds]
            await memory.apply_ops(session, scope, taught, ops, model=embedder.model)
            asking = Recall(scratch, question.asks, at=at, k=k)
            recalled = await memory.recall_by_vector(session, scope, asking, vector, model=embedder.model)
            await memory.forget(session, scope, scratch)
            answered.append(Answered(question=question, found=tuple(item.fact.text for item in recalled)))
    score = score_answers(answered, k)
    return Run(
        model=embedder.model,
        questions=score.questions,
        k=score.k,
        recall_at_k=score.recall_at_k,
        ndcg_at_10=score.ndcg_at_10,
        misses=score.misses,
        took_ms=(time.perf_counter() - started) * 1000,
    )


def score_answers(answered: Sequence[Answered], k: int) -> Score:
    """recall@k and nDCG@10 over every question; a question missing any expected fact is a miss."""
    measured = figures.measure([item.ranks for item in answered])
    return Score(
        questions=len(answered),
        k=k,
        recall_at_k=measured.recall_at_k,
        ndcg_at_10=measured.ndcg_at_10,
        misses=[Miss(item.question.asks, item.missing, item.found) for item in answered if None in item.ranks],
    )


# Facts are written by a model, so the golden is held to containment, one direction: a fact that
# says less than expected is a miss.
def says(found: str, expected: str) -> bool:
    """Whether a recalled fact contains the expected text, accents, case and spacing aside."""
    return _strip_accents(expected) in _strip_accents(found)


def _strip_accents(text: str) -> str:
    characters = unicodedata.normalize("NFD", text)
    return fold_text("".join(item for item in characters if not unicodedata.combining(item)))
