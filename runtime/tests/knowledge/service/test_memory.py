"""A contact's memory: facts written as ops, recalled by the hybrid search, superseded, forgotten."""

from collections.abc import Sequence
from datetime import UTC, datetime, timedelta

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from runtime.actor import Scope
from runtime.knowledge.models import ContactMemory
from runtime.knowledge.service import memory
from runtime.knowledge.service.embedder import Embedder
from tests.conftest import needs_the_database

pytestmark = needs_the_database

CONTACT = "+59899000001"
LEARNED = datetime(2026, 9, 1, 10, 0, tzinfo=UTC)


def taught(at: datetime = LEARNED) -> memory.Taught:
    """A call of the contact's that taught memory at that moment."""
    return memory.Taught(contact=CONTACT, call="call_1", at=at)


async def written(
    sessions: async_sessionmaker[AsyncSession],
    embedder: Embedder,
    scope: Scope,
    ops: Sequence[memory.Op],
    at: datetime = LEARNED,
) -> list[ContactMemory]:
    """The ops embedded, then written as one, as a call's extraction writes them."""
    embedded = await memory.embed_ops(embedder, ops)
    async with sessions.begin() as session:
        return await memory.apply_ops(session, scope, taught(at), embedded, model=embedder.model)


async def test_facts_written_are_recalled_by_their_words(
    sessions: async_sessionmaker[AsyncSession], embedder: Embedder, scope: Scope
) -> None:
    """Two facts added; a recall of the words of one finds it first."""
    ops = [
        memory.Op(op="add", text="Es alérgica a la penicilina", category="alergias"),
        memory.Op(op="add", text="Prefiere las citas por la mañana", category="cuándo prefiere que le llamen"),
    ]
    assert len(await written(sessions, embedder, scope, ops)) == 2
    asked = memory.Recall(contact=CONTACT, query="penicilina", at=LEARNED, k=2)
    recalled = await memory.recall(sessions, embedder, scope, asked)
    assert recalled[0].fact.text == "Es alérgica a la penicilina"


async def test_an_update_ends_the_fact_it_replaces_and_history_keeps_it(
    sessions: async_sessionmaker[AsyncSession], embedder: Embedder, scope: Scope
) -> None:
    """A fact the call contradicts stops holding at that moment; the history still reads it."""
    (afternoon,) = await written(
        sessions, embedder, scope, [memory.Op(op="add", text="Prefiere la tarde", category="horario")]
    )
    replacing = memory.Op(op="update", text="Prefiere la mañana", category="horario", of=str(afternoon.id))
    await written(sessions, embedder, scope, [replacing], at=LEARNED + timedelta(days=9))
    async with sessions.begin() as session:
        now = [fact.text for fact in await memory.list_current(session, scope, CONTACT)]
        ever = [fact.text for fact in await memory.read_history(session, scope, CONTACT, by="the suite")]
    assert now == ["Prefiere la mañana"]
    assert sorted(ever) == ["Prefiere la mañana", "Prefiere la tarde"]


async def test_forgetting_a_contact_erases_every_fact_and_says_how_many(
    sessions: async_sessionmaker[AsyncSession], embedder: Embedder, scope: Scope
) -> None:
    """The right to be forgotten: every fact of the contact, current and past, is gone."""
    ops = [memory.Op(op="add", text="Tiene seguro con Asisa"), memory.Op(op="add", text="Viene con su madre")]
    await written(sessions, embedder, scope, ops)
    async with sessions.begin() as session:
        assert await memory.forget(session, scope, CONTACT) == 2
    async with sessions.begin() as session:
        assert list(await memory.read_history(session, scope, CONTACT, by="the suite")) == []
