"""The hybrid search: two branches in one statement, fused by rank, over the rows a scope sees."""

import math

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from runtime.enums import Env
from runtime.knowledge.models import KnowledgeBase, KnowledgeChunk, Language
from runtime.knowledge.repository.bases import lexical_of
from runtime.knowledge.repository.search import RRF_K, Hit, HybridQuery, Lexical, halfvec, hybrid
from runtime.knowledge.service.ranking import CANDIDATES_PER_BRANCH
from tests.conftest import Tenant, make_tenant, needs_the_database

BASE = "clinica-norte"
SPANISH = lexical_of(Language.spanish)
type Row = dict[str, object]
SCOPE = "org = :org AND env = 'production' AND holder = '' AND base = :base"


def toward(*weights: float) -> list[float]:
    """A unit vector of 1024 whose first values are the weights given."""
    length = math.sqrt(sum(weight * weight for weight in weights))
    return [weight / length for weight in weights] + [0.0] * (1024 - len(weights))


async def kept(
    sessions: async_sessionmaker[AsyncSession],
    org: str,
    path: str,
    said: str,
    vector: list[float],
    language: str = "spanish",
) -> None:
    """A chunk of the base, as a push would have written it."""
    async with sessions.begin() as session:
        session.add(
            KnowledgeChunk(
                org=org,
                env=Env.production,
                holder="",
                base=BASE,
                path=path,
                ordinal=0,
                text=said,
                embedding=vector,
                language=language,
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
    lexical: list[Lexical] | None = None,
) -> list[Hit[Row]]:
    """What the search finds in the base, in one transaction."""
    asked = HybridQuery(
        table="knowledge_chunks",
        columns=("path", "text"),
        scope=SCOPE,
        params={"org": org, "base": base},
        lexical=lexical or [SPANISH],
        vector=vector,
        words=words,
        room=room,
        same_space=same_space,
    )
    async with sessions.begin() as session:
        return await hybrid(session, asked, dict)


def paths(hits: list[Hit[Row]]) -> list[str]:
    """The paths of the hits, in their order."""
    return [str(hit.row["path"]) for hit in hits]


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
                language="spanish",
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
        asked = HybridQuery(
            table="knowledge_chunks", columns=("path",), scope=SCOPE, params={"org": org, "base": BASE},
            lexical=[SPANISH], vector=toward(1, 0), words="lunes", room=5,
        )  # fmt: skip
        await hybrid(session, asked, dict)
        scan = (await session.execute(text("SELECT current_setting('hnsw.iterative_scan')"))).scalar_one()
    assert scan == "relaxed_order"


@needs_the_database
async def test_a_word_is_stemmed_by_the_rows_language_and_not_by_anothers(
    sessions: async_sessionmaker[AsyncSession], org: str
) -> None:
    """An English chunk answers `supervise` for `supervising`; the same words as a Spanish row do not."""
    await kept(sessions, org, "english.md", "Supervising a live call from the console", toward(1, 0), "english")
    await kept(sessions, org, "spanish.md", "Supervising a live call from the console", toward(0, 1), "spanish")
    hits = await found(
        sessions,
        org,
        vector=toward(0, 0, 1),
        words="supervise",
        lexical=[lexical_of(Language.english), SPANISH],
        same_space="false",
    )
    assert paths(hits) == ["english.md"]


@needs_the_database
async def test_two_languages_asked_together_are_one_word_branch(
    sessions: async_sessionmaker[AsyncSession], org: str
) -> None:
    """A Spanish base and an English one searched at once each answer by their own stemmer."""
    await kept(sessions, org, "horario.md", "Abrimos de lunes a viernes, cerramos los sábados", toward(1, 0), "spanish")
    await kept(sessions, org, "hours.md", "We open on weekdays and close on Saturdays", toward(0, 1), "english")
    hits = await found(
        sessions,
        org,
        vector=toward(0, 0, 1),
        words="sábado saturday",
        lexical=[SPANISH, lexical_of(Language.english)],
        same_space="false",
    )
    assert sorted(paths(hits)) == ["horario.md", "hours.md"]


@needs_the_database
async def test_each_lexical_index_is_a_ranked_list_of_its_own_so_two_corpora_are_never_compared(
    sessions: async_sessionmaker[AsyncSession], org: str
) -> None:
    """The best row of each language's index ranks first in its list: both weigh 1 / (60 + 1), whatever BM25 said."""
    await kept(sessions, org, "horario.md", "Abrimos de lunes a viernes, cerramos los sábados", toward(1, 0), "spanish")
    await kept(sessions, org, "hours.md", "We open on weekdays and close on Saturdays", toward(0, 1), "english")
    hits = await found(
        sessions,
        org,
        vector=toward(0, 0, 1),
        words="sábado saturday",
        lexical=[SPANISH, lexical_of(Language.english)],
        same_space="false",
    )
    assert {hit.row["path"]: round(hit.fused, 6) for hit in hits} == {
        "horario.md": round(1 / 61, 6),
        "hours.md": round(1 / 61, 6),
    }


# ── halfvec ──


def test_a_vector_that_half_precision_holds_exactly_reads_back_the_same() -> None:
    assert halfvec([1.0, 0.5, -0.25, 0.0]) == "[1.0,0.5,-0.25,0.0]"


def test_a_value_half_precision_cannot_hold_is_written_as_the_half_it_becomes() -> None:
    assert halfvec([3.14159265]) == "[3.140625]"
    assert halfvec([0.1]) == "[0.0999755859375]"


def test_the_edges_of_half_precision_are_what_the_column_would_hold() -> None:
    assert halfvec([65504.0, -0.0, 1e-8]) == "[65504.0,-0.0,0.0]"
