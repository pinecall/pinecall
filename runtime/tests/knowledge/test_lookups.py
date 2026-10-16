"""A call's lookups: what recall and search answer the model, and what the call's log keeps."""

from collections.abc import AsyncIterator
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any

import httpx
import pytest
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from pinecall_runtime.agents.declaration import AgentConfig, Docs, MemoryPolicy, ToolSpec
from pinecall_runtime.billing.service import Quotas
from pinecall_runtime.enums import Channel
from pinecall_runtime.kit.auth import Scope
from pinecall_runtime.kit.text import JsonObject
from pinecall_runtime.knowledge.service import bases, memory
from pinecall_runtime.knowledge.service.cutter import HEADING_SEPARATOR, cut
from pinecall_runtime.knowledge.service.embedder import Embedder
from pinecall_runtime.knowledge.service.lookups import LookupCall, LookupRequest, heard_in, lookup
from pinecall_runtime.wire.base import Entry
from pinecall_runtime.wire.parts import PlatformTool
from tests.conftest import needs_the_database
from tests.fakes.embeddings import Embeddings, Meanings
from tests.knowledge.conftest import FLAT

AGENT = "agenda"
CALL = "call_lookups"
CONTACT = "+59899000001"
LEARNED = datetime(2026, 9, 1, 10, 0, tzinfo=UTC)
NOW = datetime(2026, 9, 28, 12, 0, tzinfo=UTC)
TARIFAS = ("tarifas.md", "# Tarifas\n\n## Revisión\n\nLa revisión cuesta cuarenta euros.\n")
HORARIOS = ("horarios.md", "# Horarios\n\nAbrimos de nueve a veinte.\n")
KEEPS = MemoryPolicy(remember=("preference",))
READS = (Docs(base="clinica", k=2),)
EVERYTHING = Quotas()


@dataclass
class Kept:
    """A call's log that keeps what a lookup appends, in order."""

    entries: list[Entry] = field(default_factory=list[Entry])

    async def append(self, kind: str, data: JsonObject | None = None, *, ephemeral: bool | None = None) -> Entry:
        """One entry, numbered after the last."""
        seq = len(self.entries) + 1
        entry = Entry(
            seq=seq, ts=float(seq), call=CALL, agent=AGENT, type=kind, ephemeral=bool(ephemeral), data=dict(data or {})
        )
        self.entries.append(entry)
        return entry


@pytest.fixture
def meanings() -> Meanings:
    """An embeddings vendor whose vectors tell a revisión from a horario."""
    return Meanings(words=("revisión", "horarios", "alergia", "penicilina", "mañanas"))


@pytest.fixture
async def meant(meanings: Meanings) -> AsyncIterator[Embedder]:
    """The box's embedder on the vendor of meanings."""
    async with httpx.AsyncClient(transport=meanings.transport()) as http:
        yield Embedder(FLAT, "a-key", http)


def on_a_call(scope: Scope, config: AgentConfig, log: Kept, *, contact: str | None = CONTACT) -> LookupCall:
    """A phone call of the agent in the scope, its caller remembered as the contact."""
    return LookupCall(scope=scope, call=CALL, channel=Channel.phone, contact=contact, config=config, log=log, now=NOW)


def asked(tool: PlatformTool, query: str, **more: object) -> LookupRequest:
    """What the worker or the app asks."""
    return LookupRequest(tool=tool, input={"query": query, **more})


async def remembered(sessions: async_sessionmaker[AsyncSession], embedder: Embedder, scope: Scope, *said: str) -> None:
    """Facts the contact's earlier call taught."""
    ops = [memory.Op(op="add", text=text, category="preference") for text in said]
    async with sessions.begin() as session:
        await memory.apply_ops(
            session, embedder, scope, memory.Taught(contact=CONTACT, call="call_first", at=LEARNED), ops
        )


async def pushed(
    sessions: async_sessionmaker[AsyncSession], embedder: Embedder, scope: Scope, base: str, *files: tuple[str, str]
) -> None:
    """The files pushed into the base."""
    push = bases.Push(base=base, files=tuple(cut(path, text) for path, text in files), at=LEARNED)
    async with sessions.begin() as session:
        await bases.put_base(session, embedder, scope, push)


async def looked_up(
    sessions: async_sessionmaker[AsyncSession],
    embedder: Embedder | None,
    call: LookupCall,
    request: LookupRequest,
    quotas: Quotas = EVERYTHING,
) -> dict[str, Any]:
    """The lookup, in one transaction as the endpoint runs it."""
    async with sessions.begin() as session:
        return await lookup(session, embedder, call, request, quotas=quotas)


# ── recall ──


@needs_the_database
async def test_recall_answers_the_contacts_facts_with_their_source_and_since_and_logs_the_op(
    sessions: async_sessionmaker[AsyncSession], meant: Embedder, scope: Scope
) -> None:
    """The model reads the fact, the call that taught it and since when; the log keeps one memory.ops."""
    await remembered(sessions, meant, scope, "Es alérgica a la penicilina")
    log = Kept()
    answered = await looked_up(
        sessions,
        meant,
        on_a_call(scope, AgentConfig(slug=AGENT, memory=KEEPS), log),
        asked("recall", "alergia penicilina"),
    )
    assert answered == {
        "facts": [{"text": "Es alérgica a la penicilina", "source": "call_first", "since": "2026-09-01"}]
    }
    (entry,) = log.entries
    assert entry.type == "memory.ops"
    (op,) = entry.data["ops"]
    assert (op["op"], op["contact"], op["query"]) == ("recall", CONTACT, "alergia penicilina")


@needs_the_database
async def test_the_contact_the_model_names_is_never_the_contact_that_is_read(
    sessions: async_sessionmaker[AsyncSession], meant: Embedder, scope: Scope
) -> None:
    """A contact in the tool's input is ignored: the platform's caller is the one recalled."""
    await remembered(sessions, meant, scope, "Prefiere las mañanas")
    stranger = on_a_call(scope, AgentConfig(slug=AGENT, memory=KEEPS), Kept(), contact="+59899000999")
    answered = await looked_up(sessions, meant, stranger, asked("recall", "mañanas", contact=CONTACT))
    assert answered == {"facts": []}


@needs_the_database
@pytest.mark.parametrize(
    ("config", "contact", "quotas"),
    [
        (AgentConfig(slug=AGENT, memory=KEEPS), None, EVERYTHING),
        (AgentConfig(slug=AGENT), CONTACT, EVERYTHING),
        (AgentConfig(slug=AGENT, memory=KEEPS), CONTACT, Quotas(memory_facts=0)),
    ],
    ids=["a caller nobody knows", "an agent that keeps no memory", "a plan with no memory"],
)
async def test_a_recall_that_may_not_run_answers_nothing_and_writes_no_entry(
    sessions: async_sessionmaker[AsyncSession],
    meant: Embedder,
    scope: Scope,
    config: AgentConfig,
    contact: str | None,
    quotas: Quotas,
) -> None:
    """No contact, no policy, or memory switched off: the empty shape, and no memory.ops saying it ran."""
    await remembered(sessions, meant, scope, "Es alérgica a la penicilina")
    log = Kept()
    answered = await looked_up(
        sessions, meant, on_a_call(scope, config, log, contact=contact), asked("recall", "alergia"), quotas
    )
    assert (answered, log.entries) == ({"facts": []}, [])


@needs_the_database
async def test_a_memory_that_is_full_is_still_read_because_a_cap_is_about_keeping(
    sessions: async_sessionmaker[AsyncSession], meant: Embedder, scope: Scope
) -> None:
    """At its cap the memory keeps nothing new, and is still recalled."""
    await remembered(sessions, meant, scope, "Es alérgica a la penicilina")
    call = on_a_call(scope, AgentConfig(slug=AGENT, memory=KEEPS), Kept())
    answered = await looked_up(sessions, meant, call, asked("recall", "alergia penicilina"), Quotas(memory_facts=1))
    assert len(answered["facts"]) == 1


# ── search ──


@needs_the_database
async def test_search_answers_chunks_under_the_declarations_own_k_and_logs_the_sources(
    sessions: async_sessionmaker[AsyncSession], meant: Embedder, scope: Scope
) -> None:
    """The declaration's k chunks reach the model with their heading; docs.sources keeps the excerpt."""
    await pushed(sessions, meant, scope, "clinica", TARIFAS, HORARIOS)
    log = Kept()
    call = on_a_call(scope, AgentConfig(slug=AGENT, bases=(Docs(base="clinica", k=1),)), log)
    answered = await looked_up(sessions, meant, call, asked("search", "la revisión"))
    (chunk,) = answered["chunks"]
    heading = HEADING_SEPARATOR.join(("Tarifas", "Revisión"))
    assert (chunk["path"], chunk["heading"], chunk["text"]) == (
        "tarifas.md",
        heading,
        "La revisión cuesta cuarenta euros.",
    )
    (entry,) = log.entries
    assert (entry.type, entry.data["query"]) == ("docs.sources", "la revisión")
    (source,) = entry.data["sources"]
    assert (source["base"], source["excerpt"]) == ("clinica", "La revisión cuesta cuarenta euros.")


@needs_the_database
async def test_a_class_searching_for_itself_may_say_how_many(
    sessions: async_sessionmaker[AsyncSession], meant: Embedder, scope: Scope
) -> None:
    """A k in the tool's input wins over the declaration's."""
    await pushed(sessions, meant, scope, "clinica", TARIFAS, HORARIOS)
    call = on_a_call(scope, AgentConfig(slug=AGENT, bases=(Docs(base="clinica", k=1),)), Kept())
    answered = await looked_up(sessions, meant, call, asked("search", "revisión horarios", k=2))
    assert len(answered["chunks"]) == 2


@needs_the_database
async def test_every_attached_base_is_searched_in_one_pass_so_the_scores_are_comparable(
    sessions: async_sessionmaker[AsyncSession], meant: Embedder, scope: Scope
) -> None:
    """Two bases, one search, one docs.sources."""
    await pushed(sessions, meant, scope, "tarifas", TARIFAS)
    await pushed(sessions, meant, scope, "horarios", HORARIOS)
    log = Kept()
    both = (Docs(base="tarifas", k=1), Docs(base="horarios", k=3))
    answered = await looked_up(
        sessions,
        meant,
        on_a_call(scope, AgentConfig(slug=AGENT, bases=both), log),
        asked("search", "revisión horarios"),
    )
    assert sorted(chunk["path"] for chunk in answered["chunks"]) == ["horarios.md", "tarifas.md"]
    assert [entry.type for entry in log.entries] == ["docs.sources"]


@needs_the_database
async def test_the_declarations_min_score_is_what_the_base_is_searched_under(
    sessions: async_sessionmaker[AsyncSession], meant: Embedder, scope: Scope
) -> None:
    """The best chunk scores 1.0 relative to itself; a floor of 1.0 keeps it alone."""
    await pushed(sessions, meant, scope, "clinica", TARIFAS, HORARIOS)
    call = on_a_call(scope, AgentConfig(slug=AGENT, bases=(Docs(base="clinica", min_score=1.0),)), Kept())
    answered = await looked_up(sessions, meant, call, asked("search", "la revisión"))
    assert len(answered["chunks"]) == 1


@needs_the_database
async def test_a_search_that_may_not_run_embeds_nothing_and_writes_no_entry(
    sessions: async_sessionmaker[AsyncSession], meant: Embedder, meanings: Meanings, scope: Scope
) -> None:
    """No docs declared, or knowledge switched off: the empty shape, the embedder never asked."""
    for config, quotas in (
        (AgentConfig(slug=AGENT), EVERYTHING),
        (AgentConfig(slug=AGENT, bases=READS), Quotas(knowledge_chunks=0)),
    ):
        log = Kept()
        answered = await looked_up(
            sessions, meant, on_a_call(scope, config, log), asked("search", "la revisión"), quotas
        )
        assert (answered, log.entries) == ({"chunks": []}, [])
    assert meanings.inputs() == []


# ── when nothing can run ──


@needs_the_database
async def test_a_box_with_no_embedder_answers_every_lookup_with_nothing_found(
    sessions: async_sessionmaker[AsyncSession], scope: Scope
) -> None:
    """With no embedder configured both tools answer empty and nothing is logged."""
    log = Kept()
    call = on_a_call(scope, AgentConfig(slug=AGENT, memory=KEEPS, bases=READS), log)
    recalled = await looked_up(sessions, None, call, asked("recall", "alergia"))
    searched = await looked_up(sessions, None, call, asked("search", "revisión"))
    assert (recalled, searched, log.entries) == ({"facts": []}, {"chunks": []}, [])


@needs_the_database
async def test_a_down_embedder_finds_nothing_and_the_error_entry_names_the_tool(
    sessions: async_sessionmaker[AsyncSession], scope: Scope
) -> None:
    """The turn never waits on a lookup: an embedder that is down is an error entry and the empty shape."""
    down = Embeddings(script=[httpx.ConnectError("nothing listens")] * 4)
    log = Kept()
    async with httpx.AsyncClient(transport=down.transport()) as http:
        call = on_a_call(scope, AgentConfig(slug=AGENT, memory=KEEPS), log)
        answered = await looked_up(sessions, Embedder(FLAT, "a-key", http), call, asked("recall", "alergia"))
    assert answered == {"facts": []}
    (entry,) = log.entries
    assert (entry.type, entry.data["code"], entry.data["recoverable"]) == ("error", "recall_skipped", True)
    assert "recall did not run" in entry.data["message"]


# ── what a hang-up reads ──


def an_entry(seq: int, kind: str, data: JsonObject) -> Entry:
    """A line of the finished call's log."""
    return Entry(seq=seq, ts=float(seq), call=CALL, agent=AGENT, type=kind, ephemeral=False, data=dict(data))


def test_the_turns_of_a_call_are_what_memory_reads_and_its_tools_are_named() -> None:
    """Memory reads who said what, in order, and the names of the agent's tools; nothing else."""
    config = AgentConfig(slug=AGENT, memory=KEEPS, tools=(ToolSpec("book_slot", "Books a slot.", {"type": "object"}),))
    entries = [
        an_entry(1, "call.started", {}),
        an_entry(2, "turn.user", {"speech_id": "sp_1", "text": "Hola, soy Marta", "metrics": {}}),
        an_entry(3, "tool.call", {"call_id": "t1", "name": "book_slot", "arguments": {}}),
        an_entry(4, "turn.agent", {"speech_id": "sp_1", "text": "Hola Marta", "interrupted": False, "metrics": {}}),
    ]
    heard = heard_in(CALL, Channel.phone, CONTACT, config, entries, at=NOW)
    assert heard is not None
    assert (heard.contact, heard.call, heard.channel, heard.at, heard.tools) == (
        CONTACT,
        CALL,
        Channel.phone,
        NOW,
        ("book_slot",),
    )
    assert [(turn.role, turn.text) for turn in heard.spoken] == [("user", "Hola, soy Marta"), ("agent", "Hola Marta")]


def test_nothing_is_read_for_an_agent_with_no_policy_or_a_caller_nobody_knows() -> None:
    """No policy, or no contact: nothing for the extraction model."""
    assert heard_in(CALL, Channel.phone, CONTACT, AgentConfig(slug=AGENT), [], at=NOW) is None
    assert heard_in(CALL, Channel.web, None, AgentConfig(slug=AGENT, memory=KEEPS), [], at=NOW) is None
