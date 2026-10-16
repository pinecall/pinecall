"""What is done with the hits of a hybrid search: scores relative to the best, evidence, figures, sections."""

import dataclasses
import math
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from statistics import fmean
from typing import Any, Literal

from pinecall_runtime.knowledge.repository import Hit

type Evidence = Literal["strong", "weak", "none"]

# The cutoff of nDCG, past any k a turn is handed.
NDCG_AT = 10
CANDIDATES_PER_BRANCH = 30
# Measured on a golden of real questions; data for the reader and the judge, never a gate.
STRONG = 0.45
NONE_BELOW = 0.30
# The best pages give every section that was found in them; every page after them gives one.
PAGES_GIVING_ALL = 2


@dataclass(frozen=True, slots=True)
class Figures:
    """Recall at k, and nDCG at 10."""

    recall_at_k: float
    ndcg_at_10: float


# A fused score means nothing across queries: relative to the best, the top is always 1.0.
def relative_to_the_best(hits: Sequence[Hit]) -> list[Hit]:
    """Each hit's fused score divided by the best, the best first and ties by id."""
    best = max((hit.fused for hit in hits), default=0.0)
    ordered = sorted(hits, key=lambda hit: (-hit.fused, hit.id))
    return [dataclasses.replace(hit, fused=hit.fused / best if best else 0.0) for hit in ordered]


def top_cosine(hits: Sequence[Hit]) -> float:
    """The best cosine among the hits; 0.0 when there are none."""
    return max((hit.cosine for hit in hits), default=0.0)


def evidence_of(cosine: float) -> Evidence:
    """How strongly the best cosine says the question is answered here."""
    if cosine >= STRONG:
        return "strong"
    if cosine < NONE_BELOW:
        return "none"
    return "weak"


# nDCG is normalised by the ideal order for as many answers as the question wants.
def figures(ranks: Sequence[Sequence[int | None]]) -> Figures:
    """The two figures over the ranks of each question's wanted answers; None is not found."""
    if not ranks:
        return Figures(recall_at_k=0.0, ndcg_at_10=0.0)
    return Figures(
        recall_at_k=fmean(_share_found(question) for question in ranks),
        ndcg_at_10=fmean(_normalised(question) for question in ranks),
    )


def sections_chosen(rows: Sequence[Mapping[str, Any]], k: int) -> list[int]:
    """Which hits come back, best first: one per section, the best pages all theirs, k at most."""
    chosen: list[int] = []
    sections: set[tuple[object, object, object]] = set()
    pages: list[tuple[object, object]] = []
    for at, row in enumerate(rows):
        page = (row["base"], row["path"])
        section = (row["base"], row["path"], row["heading"])
        if section in sections or (page in pages and pages.index(page) >= PAGES_GIVING_ALL):
            continue
        if page not in pages:
            pages.append(page)
        sections.add(section)
        chosen.append(at)
        if len(chosen) == k:
            break
    return chosen


def _share_found(ranks: Sequence[int | None]) -> float:
    if not ranks:
        return 0.0
    return sum(rank is not None for rank in ranks) / len(ranks)


def _normalised(ranks: Sequence[int | None]) -> float:
    if not ranks:
        return 0.0
    ideal = sum(_discounted(place) for place in range(1, min(len(ranks), NDCG_AT) + 1))
    return sum(_discounted(rank) for rank in ranks) / ideal


# Past the tenth the model never saw it.
def _discounted(rank: int | None) -> float:
    if rank is None or rank > NDCG_AT:
        return 0.0
    return 1.0 / math.log2(rank + 1)
