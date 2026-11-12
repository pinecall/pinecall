"""A base pushed, searched with the hybrid search, re-pushed and dropped, on the test database."""

import pytest
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from runtime.actor import Scope
from runtime.billing import service as billing
from runtime.billing.service import quotas
from runtime.exceptions import QuotaExceeded
from runtime.knowledge.service import bases, search
from runtime.knowledge.service.cutter import cut
from runtime.knowledge.service.embedder import Embedder
from tests.conftest import needs_the_database

pytestmark = needs_the_database

PRICES = "# Precios\n\nUna limpieza cuesta 40 euros y dura media hora.\n"
HOURS = "# Horario\n\nAbrimos de lunes a viernes, de nueve a siete.\n"
SUPERVISING = "# Supervising a live call\n\nA supervisor listens, whispers to the agent and takes the call over.\n"
ASKED = "# Precios\n\n<!-- asks\n¿Cuánto sale una limpieza?\n-->\n\nUna limpieza cuesta 40 euros y dura media hora.\n"
NAMES = "# Vidal\n\nAna\n"


async def pushed(
    sessions: async_sessionmaker[AsyncSession],
    embedder: Embedder,
    scope: Scope,
    base: str,
    *files: tuple[str, str],
    language: str | None = None,
    replace: bool = True,
) -> bases.Pushed:
    """The folder pushed into the base, as `docs push` pushes it."""
    return await bases.push_folder(sessions, embedder, scope, base, list(files), language=language, replace=replace)


async def language_kept(sessions: async_sessionmaker[AsyncSession], scope: Scope, base: str) -> str:
    """The language the base's row says."""
    async with sessions() as session:
        return (await bases.get_base(session, scope, base)).language


async def paths_of(sessions: async_sessionmaker[AsyncSession], scope: Scope, base: str) -> list[str]:
    """The paths the base holds, in order."""
    async with sessions() as session:
        return [item.path for item in await bases.list_files(session, scope, base)]


async def asked(
    sessions: async_sessionmaker[AsyncSession], embedder: Embedder, scope: Scope, query: str, base: str, k: int = 2
) -> list[search.Found]:
    """What a turn asking these words of the base finds."""
    return await search.search(sessions, embedder, scope, search.SearchQuery(query=query, k=k, bases={base: 0.0}))


async def test_a_pushed_base_answers_the_words_of_the_file_that_holds_them(
    sessions: async_sessionmaker[AsyncSession], embedder: Embedder, scope: Scope
) -> None:
    """The search finds the chunk whose words were asked, from the right file, best first."""
    await pushed(sessions, embedder, scope, "clinica", ("precios.md", PRICES), ("horario.md", HOURS))
    found = await asked(sessions, embedder, scope, "cuánto cuesta una limpieza", "clinica")
    assert found, "the search found nothing"
    assert found[0].path == "precios.md"
    assert "40 euros" in found[0].text


async def test_a_base_replaced_keeps_only_its_new_files(
    sessions: async_sessionmaker[AsyncSession], embedder: Embedder, scope: Scope
) -> None:
    """A replace makes the base the folder: a file it no longer carries is gone, and so are its chunks."""
    await pushed(sessions, embedder, scope, "clinica", ("precios.md", PRICES), ("horario.md", HOURS))
    await pushed(sessions, embedder, scope, "clinica", ("horario.md", HOURS))
    assert await paths_of(sessions, scope, "clinica") == ["horario.md"]
    found = await asked(sessions, embedder, scope, "cuánto cuesta una limpieza", "clinica")
    assert all(one.path != "precios.md" for one in found)


async def test_a_push_keeps_the_files_it_does_not_name_and_a_replace_drops_them(
    sessions: async_sessionmaker[AsyncSession], embedder: Embedder, scope: Scope
) -> None:
    """A file the console put beside the folder's survives a push, counted in `kept`; a replace drops it."""
    folder = (("precios.md", PRICES), ("horario.md", HOURS))
    await pushed(sessions, embedder, scope, "clinica", *folder)
    await bases.put_file(sessions, embedder, scope, "clinica", "supervising.md", SUPERVISING)
    written = await pushed(sessions, embedder, scope, "clinica", *folder, replace=False)
    assert written.kept == 1
    assert await paths_of(sessions, scope, "clinica") == ["horario.md", "precios.md", "supervising.md"]
    await pushed(sessions, embedder, scope, "clinica", *folder)
    assert await paths_of(sessions, scope, "clinica") == ["horario.md", "precios.md"]


async def test_a_push_is_sized_against_the_files_it_names_and_a_replace_against_the_base(
    sessions: async_sessionmaker[AsyncSession], embedder: Embedder, scope: Scope
) -> None:
    """At the quota, a file grown by a question is refused by path and admitted as a replace: only what goes counts."""
    folder = (("precios.md", PRICES), ("horario.md", HOURS))
    await pushed(sessions, embedder, scope, "clinica", *folder)
    at_the_limit = sum(cut(path, text).rows for path, text in folder)
    async with sessions.begin() as session:
        await quotas.put_quotas(session, scope.org, scope.env, billing.Quotas(knowledge_chunks=at_the_limit))
    with pytest.raises(QuotaExceeded, match="knowledge chunks"):
        await pushed(sessions, embedder, scope, "clinica", ("precios.md", ASKED), replace=False)
    await pushed(sessions, embedder, scope, "clinica", ("precios.md", ASKED))


async def test_another_orgs_base_is_never_searched(
    sessions: async_sessionmaker[AsyncSession], embedder: Embedder, scope: Scope
) -> None:
    """A base of the same name in another org answers nothing here."""
    await pushed(sessions, embedder, scope, "clinica", ("horario.md", HOURS))
    assert await asked(sessions, embedder, Scope("org_nobody_here", scope.env), "horario", "clinica") == []


async def test_a_dropped_base_is_refused_the_second_time_and_answers_nothing_after(
    sessions: async_sessionmaker[AsyncSession], embedder: Embedder, scope: Scope
) -> None:
    """Dropping a base there is none of is refused, and the search finds nothing in it after."""
    await pushed(sessions, embedder, scope, "clinica", ("horario.md", HOURS))
    async with sessions.begin() as session:
        await bases.delete_base(session, scope, "clinica")
    async with sessions.begin() as session:
        with pytest.raises(bases.NoSuchBase):
            await bases.delete_base(session, scope, "clinica")
    assert await asked(sessions, embedder, scope, "horario", "clinica") == []


@pytest.mark.parametrize("k", [1, 2])
async def test_a_search_hands_back_at_most_k_chunks(
    sessions: async_sessionmaker[AsyncSession], embedder: Embedder, scope: Scope, k: int
) -> None:
    """However many chunks match, a turn is handed k at most."""
    await pushed(sessions, embedder, scope, "clinica", ("precios.md", PRICES), ("horario.md", HOURS))
    assert 1 <= len(await asked(sessions, embedder, scope, "limpieza horario lunes euros", "clinica", k)) <= k


async def test_a_push_that_says_no_language_is_counted_from_its_words(
    sessions: async_sessionmaker[AsyncSession], embedder: Embedder, scope: Scope
) -> None:
    """A Spanish folder is a Spanish base and an English one English, with nobody saying so."""
    await pushed(sessions, embedder, scope, "clinica", ("precios.md", PRICES), ("horario.md", HOURS))
    await pushed(sessions, embedder, scope, "console", ("supervising.md", SUPERVISING))
    assert await language_kept(sessions, scope, "clinica") == "spanish"
    assert await language_kept(sessions, scope, "console") == "english"


async def test_a_base_pushed_again_in_another_language_moves_its_chunks_and_loses_none(
    sessions: async_sessionmaker[AsyncSession], embedder: Embedder, scope: Scope
) -> None:
    """The same files said English after Spanish: the base is English now and still answers whole."""
    await pushed(sessions, embedder, scope, "console", ("supervising.md", SUPERVISING), language="spanish")
    assert await language_kept(sessions, scope, "console") == "spanish"
    await pushed(sessions, embedder, scope, "console", ("supervising.md", SUPERVISING), language="english")
    assert await language_kept(sessions, scope, "console") == "english"
    found = await asked(sessions, embedder, scope, "supervisor whispers", "console")
    assert [one.path for one in found] == ["supervising.md"]


async def test_a_file_put_beside_the_others_speaks_the_bases_language(
    sessions: async_sessionmaker[AsyncSession], embedder: Embedder, scope: Scope
) -> None:
    """One English file put into a Spanish base is read as Spanish: the base is one language."""
    await pushed(sessions, embedder, scope, "clinica", ("precios.md", PRICES), ("horario.md", HOURS))
    await bases.put_file(sessions, embedder, scope, "clinica", "supervising.md", SUPERVISING)
    assert await language_kept(sessions, scope, "clinica") == "spanish"


async def test_a_push_answers_the_language_the_base_speaks(
    sessions: async_sessionmaker[AsyncSession], embedder: Embedder, scope: Scope
) -> None:
    """What the push counted, or was told, comes back with the push, so the tenant sees `simple` at once."""
    counted = await pushed(sessions, embedder, scope, "clinica", ("precios.md", PRICES))
    said = await pushed(sessions, embedder, scope, "console", ("s.md", SUPERVISING), language="dutch")
    undecided = await pushed(sessions, embedder, scope, "names", ("names.md", NAMES))
    assert (counted.language, said.language, undecided.language) == ("spanish", "dutch", "simple")


async def test_a_base_begun_with_a_file_that_said_no_language_is_counted_again_with_the_next(
    sessions: async_sessionmaker[AsyncSession], embedder: Embedder, scope: Scope
) -> None:
    """A table of names starts the base `simple`; the prose put beside it makes the base speak, and moves the table."""
    first = await bases.put_file(sessions, embedder, scope, "clinica", "names.md", NAMES)
    second = await bases.put_file(sessions, embedder, scope, "clinica", "precios.md", PRICES)
    assert (first.language, second.language) == ("simple", "spanish")
    assert await language_kept(sessions, scope, "clinica") == "spanish"


async def test_a_question_the_section_answers_finds_it_and_the_model_reads_the_section(
    sessions: async_sessionmaker[AsyncSession], embedder: Embedder, scope: Scope
) -> None:
    """Asked in the question's own words, the search hands back the section's text, never the question."""
    await pushed(sessions, embedder, scope, "clinica", ("precios.md", ASKED), ("horario.md", HOURS))
    found = await asked(sessions, embedder, scope, "¿Cuánto sale una limpieza?", "clinica")
    assert found[0].path == "precios.md"
    assert "40 euros" in found[0].text
    assert "¿Cuánto sale" not in found[0].text
    async with sessions() as session:
        files = await bases.list_files(session, scope, "clinica")
    assert {item.path: item.chunks for item in files} == {"precios.md": 2, "horario.md": 1}
