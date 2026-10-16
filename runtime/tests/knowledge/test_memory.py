"""A contact's memory: facts written as ops, recalled by the hybrid search, superseded, forgotten."""

from datetime import UTC, datetime, timedelta

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from pinecall_runtime.kit.auth import Scope
from pinecall_runtime.knowledge.service import memory
from pinecall_runtime.knowledge.service.embedder import Embedder
from tests.conftest import needs_the_database

pytestmark = needs_the_database

CONTACT = "+59899000001"
LEARNED = datetime(2026, 9, 1, 10, 0, tzinfo=UTC)


def taught(at: datetime = LEARNED) -> memory.Taught:
    """A call of the contact's that taught memory at that moment."""
    return memory.Taught(contact=CONTACT, call="call_1", at=at)


async def test_facts_written_are_recalled_by_their_words(
    sessions: async_sessionmaker[AsyncSession], embedder: Embedder, scope: Scope
) -> None:
    """Two facts added; a recall of the words of one finds it first."""
    ops = [
        memory.Op(op="add", text="Es alérgica a la penicilina", category="alergias"),
        memory.Op(op="add", text="Prefiere las citas por la mañana", category="cuándo prefiere que le llamen"),
    ]
    async with sessions.begin() as session:
        written = await memory.apply_ops(session, embedder, scope, taught(), ops)
    assert len(written) == 2
    async with sessions() as session:
        recalled = await memory.recall(
            session, embedder, scope, memory.Recall(contact=CONTACT, query="penicilina", at=LEARNED, k=2)
        )
    assert recalled.facts[0].fact.text == "Es alérgica a la penicilina"


async def test_an_update_ends_the_fact_it_replaces_and_history_keeps_it(
    sessions: async_sessionmaker[AsyncSession], embedder: Embedder, scope: Scope
) -> None:
    """A fact the call contradicts stops holding at that moment; the history still reads it."""
    async with sessions.begin() as session:
        (afternoon,) = await memory.apply_ops(
            session, embedder, scope, taught(), [memory.Op(op="add", text="Prefiere la tarde", category="horario")]
        )
    later = LEARNED + timedelta(days=9)
    replacing = memory.Op(op="update", text="Prefiere la mañana", category="horario", of=str(afternoon.id))
    async with sessions.begin() as session:
        await memory.apply_ops(session, embedder, scope, taught(later), [replacing])
    async with sessions() as session:
        now = [fact.text for fact in await memory.current(session, scope, CONTACT)]
        ever = [fact.text for fact in await memory.history(session, scope, CONTACT)]
    assert now == ["Prefiere la mañana"]
    assert sorted(ever) == ["Prefiere la mañana", "Prefiere la tarde"]


async def test_a_recall_as_of_a_moment_reads_what_held_then(
    sessions: async_sessionmaker[AsyncSession], embedder: Embedder, scope: Scope
) -> None:
    """A recall at a past moment finds the fact that held then, not the one that replaced it."""
    async with sessions.begin() as session:
        (afternoon,) = await memory.apply_ops(
            session, embedder, scope, taught(), [memory.Op(op="add", text="Prefiere la tarde", category="horario")]
        )
    later = LEARNED + timedelta(days=9)
    async with sessions.begin() as session:
        await memory.apply_ops(
            session,
            embedder,
            scope,
            taught(later),
            [memory.Op(op="update", text="Prefiere la mañana", category="horario", of=str(afternoon.id))],
        )
    asked = memory.Recall(contact=CONTACT, query="prefiere", at=later, k=1, as_of=LEARNED + timedelta(days=1))
    async with sessions() as session:
        recalled = await memory.recall(session, embedder, scope, asked)
    assert [item.fact.text for item in recalled.facts] == ["Prefiere la tarde"]


async def test_forgetting_a_contact_erases_every_fact_and_says_how_many(
    sessions: async_sessionmaker[AsyncSession], embedder: Embedder, scope: Scope
) -> None:
    """The right to be forgotten: every fact of the contact, current and past, is gone."""
    ops = [memory.Op(op="add", text="Tiene seguro con Asisa"), memory.Op(op="add", text="Viene con su madre")]
    async with sessions.begin() as session:
        await memory.apply_ops(session, embedder, scope, taught(), ops)
    async with sessions.begin() as session:
        assert await memory.forget(session, scope, CONTACT) == 2
    async with sessions() as session:
        assert await memory.history(session, scope, CONTACT) == []
