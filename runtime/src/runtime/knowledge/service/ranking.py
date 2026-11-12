"""What is done with the hits of a hybrid search, whatever table they came from: scores relative to the best."""

import dataclasses
from collections.abc import Sequence

from runtime.knowledge.repository import Hit

# How many rows each branch of a search hands to the fusion; a search of several bases, that many a base.
CANDIDATES_PER_BRANCH = 30


# A fused score means nothing across queries: relative to the best, the top is always 1.0.
def relative_to_the_best[Row](hits: Sequence[Hit[Row]]) -> list[Hit[Row]]:
    """Each hit's fused score divided by the best, the best first and ties by id."""
    best = max((hit.fused for hit in hits), default=0.0)
    ordered = sorted(hits, key=lambda hit: (-hit.fused, hit.id))
    return [dataclasses.replace(hit, fused=hit.fused / best if best else 0.0) for hit in ordered]
