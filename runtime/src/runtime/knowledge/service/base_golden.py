"""A base held to its golden: each question asked of the base alone, scored by code with no model."""

import time
from collections.abc import Sequence
from dataclasses import dataclass

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from runtime.actor import Scope
from runtime.knowledge.service import figures, search
from runtime.knowledge.service.bases import NoSuchBase
from runtime.knowledge.service.cutter import answers
from runtime.knowledge.service.embedder import Embedder
from runtime.knowledge.service.search import Found, SearchQuery


@dataclass(frozen=True, slots=True)
class Question:
    """A golden question and the heading paths any one of which answers it."""

    asks: str
    expects: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class Answered:
    """A question and the chunks the search handed back, best first."""

    question: Question
    found: list[Found]


@dataclass(frozen=True, slots=True)
class Miss:
    """One question none of whose chunks was among the k returned, and what came back instead."""

    asks: str
    expects: tuple[str, ...]
    found: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class Score:
    """A golden run: how many questions, at which k, its two figures, and the questions missed."""

    questions: int
    k: int
    recall_at_k: float
    ndcg_at_10: float
    misses: list[Miss]


@dataclass(frozen=True, slots=True)
class Run:
    """A base's golden as it is answered: the base, the model that wrote it, the score, how long it took."""

    base: str
    model: str
    questions: int
    k: int
    recall_at_k: float
    ndcg_at_10: float
    misses: list[Miss]
    took_ms: float


# Every question embedded in one go, before the first statement of the searches: what a turn would
# have found, without a round trip to the embedder per question and with no connection waiting on it.
# Sequential: searches at once would measure the pool, not the index. No floor: the golden measures
# the ranking, not an attachment's threshold.
async def run(
    sessions: async_sessionmaker[AsyncSession],
    embedder: Embedder,
    scope: Scope,
    base: str,
    questions: Sequence[Question],
    k: int,
) -> Run:
    """Each question asked of the base, and recall@k and nDCG@10 over every answer."""
    async with sessions.begin() as session:
        copies = await search.list_copies(session, scope, [base], embedder.model)
    if not copies:
        raise NoSuchBase(base)
    started = time.perf_counter()
    vectors = await embedder.embed([question.asks for question in questions])
    answered: list[Answered] = []
    async with sessions.begin() as session:
        for question, vector in zip(questions, vectors, strict=True):
            asked = SearchQuery(query=question.asks, k=k, bases={base: 0.0})
            found = await search.search_by_vector(session, scope, copies, asked, vector)
            answered.append(Answered(question, found))
    score = score_answers(answered, k)
    return Run(
        base=base,
        model=copies[0].model,
        questions=score.questions,
        k=score.k,
        recall_at_k=score.recall_at_k,
        ndcg_at_10=score.ndcg_at_10,
        misses=score.misses,
        took_ms=(time.perf_counter() - started) * 1000,
    )


def score_answers(answered: Sequence[Answered], k: int) -> Score:
    """Recall at k and nDCG at 10 over every question, and the ones whose chunk never came back."""
    ranks = [_rank_of(item) for item in answered]
    measured = figures.measure([[rank] for rank in ranks])
    return Score(
        questions=len(answered),
        k=k,
        recall_at_k=measured.recall_at_k,
        ndcg_at_10=measured.ndcg_at_10,
        misses=[
            Miss(item.question.asks, item.question.expects, tuple(chunk.where for chunk in item.found))
            for item, rank in zip(answered, ranks, strict=True)
            if rank is None
        ],
    )


# Only the first match counts: a base that repeats itself answered once, and any of the paths answers.
def _rank_of(item: Answered) -> int | None:
    return next(
        (
            at
            for at, chunk in enumerate(item.found, start=1)
            if any(answers(chunk.where, expected) for expected in item.question.expects)
        ),
        None,
    )
