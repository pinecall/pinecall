"""The hybrid search: two branches in one statement, fused by rank, over the rows a scope sees."""

import math

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from pinecall_runtime.enums import Env
from pinecall_runtime.knowledge.models import KnowledgeBase, KnowledgeChunk
from pinecall_runtime.knowledge.repository.search import RRF_K, Hit, hybrid
from pinecall_runtime.knowledge.service.embedder import halfvec
from pinecall_runtime.knowledge.service.ranking import (
    CANDIDATES_PER_BRANCH,
    evidence_of,
    relative_to_the_best,
    top_cosine,
)
from tests.conftest import Tenant, make_tenant, needs_the_database

BASE = "clinica-norte"
TEXT_INDEX = "knowledge_chunks_text_bm25"
SCOPE = "org = :org AND env = 'production' AND holder = '' AND base = :base"


def toward(*weights: float) -> list[float]:
    """A unit vector of 1024 whose first values are the weights given."""
    length = math.sqrt(sum(weight * weight for weight in weights))
    return [weight / length for weight in weights] + [0.0] * (1024 - len(weights))


async def kept(sessions: async_sessionmaker[AsyncSession], org: str, path: str, said: str, vector: list[float]) -> None:
    """A chunk of the base, as a push would have written it."""
    async with sessions.begin() as session:
        session.add(
            KnowledgeChunk(
                org=org, env=Env.production, holder="", base=BASE, path=path, ordinal=0, text=said, embedding=vector
            )
        )


async def found(
    sessions: async_sessionmaker[AsyncSession],
    org: str,
    *,
    vector: list[float],
    words: str,
    room: int = CANDIDATES_PER_BRANCH,
    base: str = BASE,
    same_space: str = "true",
) -> list[Hit]:
    """What the search finds in the base, in one transaction."""
    async with sessions.begin() as session:
        return await hybrid(
            session,
            "knowledge_chunks",
            TEXT_INDEX,
            SCOPE,
            same_space,
            ("path", "text"),
            {"org": org, "base": base},
            vector=halfvec(vector),
            words=words,
            room=room,
        )


def paths(hits: list[Hit]) -> list[str]:
    """The paths of the hits, in their order."""
    return [hit.row["path"] for hit in hits]


@pytest.fixture
async def org(sessions: async_sessionmaker[AsyncSession], tenant: Tenant) -> str:
    """The tenant's org, with one empty base its chunks are written into."""
    async with sessions.begin() as session:
        session.add(
            KnowledgeBase(
                org=tenant.org,
                env=Env.production,
                holder="",
                base=BASE,
                model="embed-flat-1",
                dimensions=1024,
                chunks=0,
            )
        )
    return tenant.org


@needs_the_database
async def test_a_row_is_found_by_its_words_where_its_vector_says_nothing(
    sessions: async_sessionmaker[AsyncSession], org: str
) -> None:
    """BM25 finds the row the vector misses, with its cosine as it is."""
    await kept(sessions, org, "horario.md", "Abrimos de lunes a viernes", toward(1, 0))
    await kept(sessions, org, "tarifas.md", "La revisión anual cuesta cuarenta euros", toward(0, 1))
    hits = await found(sessions, org, vector=toward(1, 0), words="revisión", room=1)
    assert sorted(paths(hits)) == ["horario.md", "tarifas.md"]
    by_words = next(hit for hit in hits if hit.row["path"] == "tarifas.md")
    assert by_words.cosine == pytest.approx(0.0, abs=1e-3)


@needs_the_database
async def test_a_row_is_found_by_its_vector_where_its_words_say_nothing(
    sessions: async_sessionmaker[AsyncSession], org: str
) -> None:
    """The vector finds the row no word of the question is in."""
    await kept(sessions, org, "horario.md", "Abrimos de lunes a viernes", toward(1, 0))
    await kept(sessions, org, "tarifas.md", "La revisión anual cuesta cuarenta euros", toward(0, 1))
    hits = await found(sessions, org, vector=toward(0, 1), words="aparcamiento", room=1)
    assert paths(hits) == ["tarifas.md"]
    assert hits[0].cosine == pytest.approx(1.0, abs=1e-3)


@needs_the_database
async def test_the_row_both_branches_find_comes_before_the_first_of_either_alone(
    sessions: async_sessionmaker[AsyncSession], org: str
) -> None:
    """Found by both, a row outranks the best of each branch alone."""
    await kept(sessions, org, "cerca.md", "Abrimos de lunes a viernes", toward(1, 0))
    await kept(sessions, org, "ambos.md", "La revisión se hace en el taller", toward(1, 0.2))
    await kept(sessions, org, "palabras.md", "Revisión, revisión y más revisión", toward(0, 1))
    hits = await found(sessions, org, vector=toward(1, 0), words="revisión", room=2)
    assert paths(hits)[0] == "ambos.md"


@needs_the_database
async def test_a_rank_weighs_one_over_sixty_plus_it_and_both_branches_add_up(
    sessions: async_sessionmaker[AsyncSession], org: str
) -> None:
    """Reciprocal rank fusion: 1 / (60 + rank) a branch, summed."""
    await kept(sessions, org, "ambos.md", "La revisión anual", toward(1, 0))
    await kept(sessions, org, "cerca.md", "Abrimos de lunes a viernes", toward(1, 0.5))
    both, near = await found(sessions, org, vector=toward(1, 0), words="revisión")
    assert both.fused == pytest.approx(2 / (RRF_K + 1))
    assert near.fused == pytest.approx(1 / (RRF_K + 2))


@needs_the_database
async def test_room_caps_each_branch_and_not_the_two_together(
    sessions: async_sessionmaker[AsyncSession], org: str
) -> None:
    """Room 2 is two from the vectors and two from the words."""
    for at in range(3):
        await kept(sessions, org, f"cerca-{at}.md", "Abrimos de lunes a viernes", toward(1, at / 10))
    for at in range(3):
        await kept(sessions, org, f"lejos-{at}.md", "revisión " * (at + 1), toward(0, 1, at / 10))
    hits = await found(sessions, org, vector=toward(1, 0), words="revisión", room=2)
    assert sorted(paths(hits)) == ["cerca-0.md", "cerca-1.md", "lejos-1.md", "lejos-2.md"]


@needs_the_database
async def test_a_row_no_term_matched_never_enters_the_word_branch(
    sessions: async_sessionmaker[AsyncSession], org: str
) -> None:
    """A BM25 score of 0 is no match, not the last match."""
    await kept(sessions, org, "horario.md", "Abrimos de lunes a viernes", toward(1, 0))
    await kept(sessions, org, "tarifas.md", "La revisión anual cuesta cuarenta euros", toward(0, 1))
    hits = await found(sessions, org, vector=toward(1, 0), words="lunes", room=1)
    assert paths(hits) == ["horario.md"]


@needs_the_database
async def test_the_scope_sees_one_orgs_base_and_never_another_base_or_org(
    sessions: async_sessionmaker[AsyncSession], org: str
) -> None:
    """Another base of the org, and the same base of another org, find nothing."""
    await kept(sessions, org, "horario.md", "Abrimos de lunes a viernes", toward(1, 0))
    other = await make_tenant(sessions)
    assert await found(sessions, org, vector=toward(1, 0), words="lunes", base="otra") == []
    assert await found(sessions, other.org, vector=toward(1, 0), words="lunes") == []


@needs_the_database
async def test_the_vector_branch_alone_can_be_narrowed_and_the_word_branch_still_finds(
    sessions: async_sessionmaker[AsyncSession], org: str
) -> None:
    """Rows of another embedding space are out of the vector branch, never out of BM25."""
    await kept(sessions, org, "tarifas.md", "La revisión anual", toward(1, 0))
    by_words = await found(sessions, org, vector=toward(1, 0), words="revisión", room=5, same_space="false")
    by_vector = await found(sessions, org, vector=toward(1, 0), words="nada", room=5, same_space="false")
    assert [hit.fused for hit in by_words] == [pytest.approx(1 / (RRF_K + 1))]
    assert by_vector == []


@needs_the_database
async def test_the_scan_goes_on_past_the_index_first_candidates_in_the_same_transaction(
    sessions: async_sessionmaker[AsyncSession], org: str
) -> None:
    """The search turns on the iterative scan for its own transaction."""
    async with sessions.begin() as session:
        await hybrid(
            session, "knowledge_chunks", TEXT_INDEX, SCOPE, "true", ("path",), {"org": org, "base": BASE},
            vector=halfvec(toward(1, 0)), words="lunes", room=5,
        )  # fmt: skip
        scan = (await session.execute(text("SELECT current_setting('hnsw.iterative_scan')"))).scalar_one()
    assert scan == "relaxed_order"


# ── what the hits are made into ──


def a_hit(named: str, fused: float, cosine: float = 0.5) -> Hit:
    """A hit with no columns."""
    return Hit(id=named, fused=fused, cosine=cosine, row={})


def test_the_best_is_one_and_the_rest_are_their_share_of_it_best_first() -> None:
    """Scores are relative to the best hit."""
    scored = relative_to_the_best([a_hit("b", 0.5), a_hit("a", 1.0), a_hit("c", 0.25)])
    assert [(hit.id, hit.fused) for hit in scored] == [("a", 1.0), ("b", 0.5), ("c", 0.25)]


def test_a_tie_is_ordered_by_id_so_two_processes_answer_alike() -> None:
    """Equal scores come back in one order everywhere."""
    tied = relative_to_the_best([a_hit("z", 1.0), a_hit("m", 1.0)])
    assert [hit.id for hit in tied] == ["m", "z"]


def test_nothing_found_is_nothing_and_a_zero_best_divides_nothing() -> None:
    """No hits, or a best of zero, never divides by zero."""
    assert relative_to_the_best([]) == []
    assert [hit.fused for hit in relative_to_the_best([a_hit("a", 0.0)])] == [0.0]


def test_the_top_cosine_is_the_best_hits_and_nothing_found_is_zero() -> None:
    """The evidence is read off the highest cosine."""
    assert top_cosine([a_hit("a", 1.0, cosine=0.2), a_hit("b", 0.5, cosine=0.61)]) == 0.61
    assert top_cosine([]) == 0.0


@pytest.mark.parametrize(
    ("cosine", "evidence"),
    [(0.45, "strong"), (0.8, "strong"), (0.44, "weak"), (0.30, "weak"), (0.29, "none"), (0.0, "none")],
)
def test_the_best_cosine_says_how_strong_the_evidence_is(cosine: float, evidence: str) -> None:
    """Strong from 0.45, none below 0.30."""
    assert evidence_of(cosine) == evidence
