"""A base pushed, searched with the hybrid search, re-pushed and dropped, on the test database."""

from datetime import UTC, datetime

import pytest
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from pinecall_runtime.kit.auth import Scope
from pinecall_runtime.knowledge.service import bases
from pinecall_runtime.knowledge.service.cutter import cut
from pinecall_runtime.knowledge.service.embedder import Embedder
from tests.conftest import needs_the_database

pytestmark = needs_the_database

PUSHED = datetime(2026, 10, 16, 12, 0, tzinfo=UTC)
PRICES = "# Precios\n\nUna limpieza cuesta 40 euros y dura media hora.\n"
HOURS = "# Horario\n\nAbrimos de lunes a viernes, de nueve a siete.\n"


def a_push(base: str, *files: tuple[str, str]) -> bases.Push:
    """The files cut as a push cuts them."""
    return bases.Push(base=base, files=tuple(cut(path, text) for path, text in files), at=PUSHED)


async def asked(
    sessions: async_sessionmaker[AsyncSession], embedder: Embedder, scope: Scope, query: str, base: str
) -> bases.Searched:
    """What a turn asking these words of the base finds."""
    async with sessions() as session:
        return await bases.search(session, embedder, scope, bases.SearchQuery(query=query, k=2, bases={base: 0.0}))


async def test_a_pushed_base_answers_the_words_of_the_file_that_holds_them(
    sessions: async_sessionmaker[AsyncSession], embedder: Embedder, scope: Scope
) -> None:
    """The search finds the chunk whose words were asked, from the right file, best first."""
    async with sessions.begin() as session:
        await bases.put_base(session, embedder, scope, a_push("clinica", ("precios.md", PRICES), ("horario.md", HOURS)))
    searched = await asked(sessions, embedder, scope, "cuánto cuesta una limpieza", "clinica")
    assert searched.found, "the search found nothing"
    assert searched.found[0].path == "precios.md"
    assert "40 euros" in searched.found[0].text


async def test_a_base_pushed_again_keeps_only_its_new_files(
    sessions: async_sessionmaker[AsyncSession], embedder: Embedder, scope: Scope
) -> None:
    """A push replaces the base whole: a file it no longer carries is gone, and so are its chunks."""
    async with sessions.begin() as session:
        await bases.put_base(session, embedder, scope, a_push("clinica", ("precios.md", PRICES), ("horario.md", HOURS)))
    async with sessions.begin() as session:
        await bases.put_base(session, embedder, scope, a_push("clinica", ("horario.md", HOURS)))
    async with sessions() as session:
        files = await bases.list_files(session, scope, "clinica")
    assert files is not None
    assert [item.path for item in files] == ["horario.md"]
    searched = await asked(sessions, embedder, scope, "cuánto cuesta una limpieza", "clinica")
    assert all(found.path != "precios.md" for found in searched.found)


async def test_another_orgs_base_is_never_searched(
    sessions: async_sessionmaker[AsyncSession], embedder: Embedder, scope: Scope
) -> None:
    """A base of the same name in another org answers nothing here."""
    elsewhere = Scope("org_nobody_here", scope.env)
    async with sessions.begin() as session:
        await bases.put_base(session, embedder, scope, a_push("clinica", ("horario.md", HOURS)))
    searched = await asked(sessions, embedder, elsewhere, "horario", "clinica")
    assert searched.found == []


async def test_a_dropped_base_says_so_once_and_answers_nothing_after(
    sessions: async_sessionmaker[AsyncSession], embedder: Embedder, scope: Scope
) -> None:
    """Dropping says whether there was a base, and the search finds nothing in it after."""
    async with sessions.begin() as session:
        await bases.put_base(session, embedder, scope, a_push("clinica", ("horario.md", HOURS)))
    async with sessions.begin() as session:
        assert await bases.drop_base(session, scope, "clinica")
        assert not await bases.drop_base(session, scope, "clinica")
    assert (await asked(sessions, embedder, scope, "horario", "clinica")).found == []


@pytest.mark.parametrize("k", [1, 2])
async def test_a_search_hands_back_at_most_k_chunks(
    sessions: async_sessionmaker[AsyncSession], embedder: Embedder, scope: Scope, k: int
) -> None:
    """However many chunks match, a turn is handed k at most."""
    async with sessions.begin() as session:
        await bases.put_base(session, embedder, scope, a_push("clinica", ("precios.md", PRICES), ("horario.md", HOURS)))
    async with sessions() as session:
        query = bases.SearchQuery(query="limpieza horario lunes euros", k=k, bases={"clinica": 0.0})
        searched = await bases.search(session, embedder, scope, query)
    assert 1 <= len(searched.found) <= k
