"""The two figures a golden is scored with: recall at k, and nDCG at 10, over the ranks of what it wanted."""

import math
from collections.abc import Sequence
from dataclasses import dataclass
from statistics import fmean

# The cutoff of nDCG, past any k a turn is handed.
NDCG_AT = 10


@dataclass(frozen=True, slots=True)
class Figures:
    """Recall at k, and nDCG at 10."""

    recall_at_k: float
    ndcg_at_10: float


# nDCG is normalised by the ideal order for as many answers as the question wants.
def measure(ranks: Sequence[Sequence[int | None]]) -> Figures:
    """The two figures over the ranks of each question's wanted answers; None is not found."""
    if not ranks:
        return Figures(recall_at_k=0.0, ndcg_at_10=0.0)
    return Figures(
        recall_at_k=fmean(_share_found(question) for question in ranks),
        ndcg_at_10=fmean(_normalise(question) for question in ranks),
    )


def _share_found(ranks: Sequence[int | None]) -> float:
    if not ranks:
        return 0.0
    return sum(rank is not None for rank in ranks) / len(ranks)


def _normalise(ranks: Sequence[int | None]) -> float:
    if not ranks:
        return 0.0
    ideal = sum(_discount(place) for place in range(1, min(len(ranks), NDCG_AT) + 1))
    return sum(_discount(rank) for rank in ranks) / ideal


# Past the tenth the model never saw it.
def _discount(rank: int | None) -> float:
    if rank is None or rank > NDCG_AT:
        return 0.0
    return 1.0 / math.log2(rank + 1)
