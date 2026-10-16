"""The one hybrid search both knowledge and memory are read with: cosine and BM25, fused by rank."""

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

# Cormack's constant: a rank weighs 1 / (60 + rank), so cosine and BM25 are never compared.
RRF_K = 60

# `hnsw.iterative_scan` makes the index scan past its first 40 candidates when the scope filters
# them out: one tenant's rows among every tenant's would otherwise come back short, or empty.
ITERATIVE_SCAN = text("SET LOCAL hnsw.iterative_scan = relaxed_order")

# `<@>` is BM25 negated, lower is better, and 0 when no term matched: those rows are no match.
HYBRID = """
WITH dense AS (
    SELECT id, RANK() OVER (ORDER BY distance) AS r FROM (
        SELECT id, embedding <=> CAST(:q AS halfvec) AS distance FROM {table}
        WHERE ({scope}) AND ({same_space})
        ORDER BY embedding <=> CAST(:q AS halfvec)
        LIMIT :room
    ) AS nearest
),
sparse AS (
    SELECT id, RANK() OVER (ORDER BY score) AS r FROM (
        SELECT id, score FROM (
            SELECT id, text <@> to_bm25query(:words, '{text_index}') AS score FROM {table}
            WHERE ({scope})
        ) AS scored
        WHERE score < 0
        ORDER BY score
        LIMIT :room
    ) AS worded
),
fusion AS (
    SELECT coalesce(dense.id, sparse.id) AS id,
        (coalesce(1.0 / ({k} + dense.r), 0) + coalesce(1.0 / ({k} + sparse.r), 0))::float8 AS fused
    FROM dense FULL OUTER JOIN sparse ON dense.id = sparse.id
)
SELECT CAST(fusion.id AS text) AS hit_id, fusion.fused AS hit_fused,
    1 - (found.embedding <=> CAST(:q AS halfvec)) AS hit_cosine, {columns}
FROM fusion JOIN {table} AS found ON found.id = fusion.id
ORDER BY fusion.fused DESC, fusion.id
"""


@dataclass(frozen=True, slots=True)
class Hit:
    """One row found: its id, its fused score, its cosine to the query, and the columns asked."""

    id: str
    fused: float
    cosine: float
    row: Mapping[str, Any]


async def hybrid(
    session: AsyncSession,
    table: str,
    text_index: str,
    scope: str,
    same_space: str,
    columns: Sequence[str],
    params: Mapping[str, Any],
    *,
    vector: str,
    words: str,
    room: int,
) -> list[Hit]:
    """Up to `room` rows from each branch, fused by reciprocal rank, the best first."""
    query = HYBRID.format(
        table=table,
        text_index=text_index,
        scope=scope,
        same_space=same_space,
        k=RRF_K,
        columns=", ".join(f"found.{column}" for column in columns),
    )
    await session.execute(ITERATIVE_SCAN)
    rows = (await session.execute(text(query), {**params, "q": vector, "words": words, "room": room})).mappings().all()
    return [
        Hit(
            id=str(row["hit_id"]),
            fused=float(row["hit_fused"]),
            cosine=float(row["hit_cosine"]),
            row={c: row[c] for c in columns},
        )
        for row in rows
    ]
