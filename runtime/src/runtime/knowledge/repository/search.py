"""The one hybrid search both knowledge and memory are read with: cosine and BM25, fused by rank."""

import struct
import uuid
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from datetime import datetime
from typing import Any

from sqlalchemy import RowMapping, text
from sqlalchemy.ext.asyncio import AsyncSession

# Cormack's constant: a rank weighs 1 / (60 + rank), so cosine and BM25 are never compared.
RRF_K = 60

# `hnsw.iterative_scan` makes the index scan past its first 40 candidates when the scope filters
# them out: one tenant's rows among every tenant's would otherwise come back short, or empty.
ITERATIVE_SCAN = text("SET LOCAL hnsw.iterative_scan = relaxed_order")
# A prepared statement is planned for its values every time: planned once for any org and any copy,
# it estimated a few dozen rows for every copy and scored them all by hand, a second a search, where
# the index scans take ten milliseconds. Planning costs a millisecond.
PLANNED_FOR_ITS_VALUES = text("SET LOCAL plan_cache_mode = force_custom_plan")

# Every branch is one ranked list: the vectors, and the words of each lexical index asked, since
# two indexes' BM25 scores are over two corpora and compare only within one. A row's fused score
# is the sum of 1 / (k + rank) over the lists it is in.
HYBRID = """
WITH ranked AS (
    SELECT id, RANK() OVER (ORDER BY distance) AS r FROM (
        SELECT id, embedding <=> CAST(:q AS halfvec) AS distance FROM {table}
        WHERE ({scope}) AND ({same_space})
        ORDER BY embedding <=> CAST(:q AS halfvec)
        LIMIT :room
    ) AS nearest
    {worded}
),
fusion AS (
    SELECT id, SUM(1.0 / ({k} + r))::float8 AS fused FROM ranked GROUP BY id
)
SELECT CAST(fusion.id AS text) AS hit_id, fusion.fused AS hit_fused,
    1 - (found.embedding <=> CAST(:q AS halfvec)) AS hit_cosine, {columns}
FROM fusion JOIN {table} AS found ON found.id = fusion.id
ORDER BY fusion.fused DESC, fusion.id
"""
# `<@>` is BM25 negated, lower is better, and 0 when no term matched: those rows are no match.
# The ORDER BY on the operator with the LIMIT under it is what pg_textsearch reads as a top-k
# scan of the index; scored in a plain SELECT, every row of the scope was scored one by one.
WORDED = """
    UNION ALL
    SELECT id, RANK() OVER (ORDER BY score) AS r FROM (
        SELECT id, text <@> to_bm25query(:words, '{index}') AS score FROM {table}
        WHERE ({scope}) AND ({rows})
        ORDER BY text <@> to_bm25query(:words, '{index}')
        LIMIT :room
    ) AS worded_{at}
    WHERE score < 0
"""


@dataclass(frozen=True, slots=True)
class Lexical:
    """One BM25 index to read, and the predicate that picks its rows (`true` for a whole index)."""

    index: str
    rows: str = "true"


@dataclass(frozen=True, slots=True)
class Hit[Row]:
    """One row found: its id, its fused score, its cosine to the query, and the row as its table reads it."""

    id: str
    fused: float
    cosine: float
    row: Row


@dataclass(frozen=True, slots=True)
class ChunkFound:
    """A chunk of a base as a search reads it: where it is, its place in its file, its indexed text."""

    base: str
    holder: str
    path: str
    heading: str | None
    ordinal: int
    text: str


@dataclass(frozen=True, slots=True)
class FactFound:
    """A fact of a contact as a recall reads it: what it says, when it held, where it came from."""

    id: uuid.UUID
    contact: str
    category: str | None
    text: str
    valid_from: datetime
    invalidated_at: datetime | None
    supersedes: uuid.UUID | None
    source_call: str | None
    model: str
    confidence: float


# One statement for two tables: what differs is said here, and each repository says how its row is read.
@dataclass(frozen=True, slots=True)
class HybridQuery:
    """What a hybrid search asks of one table: its rows in scope, its lexical indexes, the query both ways."""

    table: str
    # The columns the search hands back, by name.
    columns: Sequence[str]
    # The predicate that picks the scope's rows, and the values it binds.
    scope: str
    params: Mapping[str, Any]
    lexical: Sequence[Lexical]
    vector: Sequence[float]
    words: str
    # How many rows each branch may hand to the fusion.
    room: int
    # The predicate that keeps the vector branch to rows of the query's own space.
    same_space: str = "true"


async def hybrid[Row](session: AsyncSession, query: HybridQuery, read: Callable[[RowMapping], Row]) -> list[Hit[Row]]:
    """Up to `room` rows from the vectors and from each lexical index, fused by reciprocal rank, the best first."""
    statement = HYBRID.format(
        table=query.table,
        worded="".join(
            WORDED.format(index=one.index, table=query.table, scope=query.scope, rows=one.rows, at=at)
            for at, one in enumerate(query.lexical)
        ),
        scope=query.scope,
        same_space=query.same_space,
        k=RRF_K,
        columns=", ".join(f"found.{column}" for column in query.columns),
    )
    await session.execute(ITERATIVE_SCAN)
    await session.execute(PLANNED_FOR_ITS_VALUES)
    params = {**query.params, "q": halfvec(query.vector), "words": query.words, "room": query.room}
    rows = (await session.execute(text(statement), params)).mappings().all()
    return [
        Hit(id=str(row["hit_id"]), fused=float(row["hit_fused"]), cosine=float(row["hit_cosine"]), row=read(row))
        for row in rows
    ]


# pgvector parses the text and the SQL casts it (`::halfvec`), so the driver needs no vector type.
def halfvec(vector: Sequence[float]) -> str:
    """The vector as pgvector's text, each value rounded to IEEE half precision as the column is."""
    return "[" + ",".join(str(_half(value)) for value in vector) + "]"


def _half(value: float) -> float:
    rounded: float = struct.unpack("<e", struct.pack("<e", value))[0]
    return rounded
