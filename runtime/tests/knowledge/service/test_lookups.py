"""A call's lookups: what recall and search answer the model, and what the call's log keeps."""

from collections.abc import AsyncIterator
from dataclasses import dataclass, field
from datetime import UTC, datetime

import httpx
import pytest
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from runtime.actor import Scope
from runtime.agents.declaration import Declaration, Docs, MemoryPolicy
from runtime.billing import service as billing
from runtime.billing.service import quotas
from runtime.enums import Channel
from runtime.kit.text import JsonObject
from runtime.knowledge.service import bases, lookups, memory
from runtime.knowledge.service.cutter import HEADING_SEPARATOR
from runtime.knowledge.service.embedder import Embedder
from runtime.knowledge.service.lookups import Answer, LookupCall, LookupRequest
from runtime.wire.base import Entry
from runtime.wire.parts import PlatformTool, RecalledFacts, SearchFound
from tests.conftest import needs_the_database
from tests.fakes.embeddings import Embeddings, Meanings
from tests.knowledge.conftest import FLAT

pytestmark = needs_the_database

AGENT = "agenda"
CALL = "call_lookups"
CONTACT = "+59899000001"
LEARNED = datetime(2026, 9, 1, 10, 0, tzinfo=UTC)
NOW = datetime(2026, 9, 28, 12, 0, tzinfo=UTC)
TARIFAS = ("tarifas.md", "# Tarifas\n\n## Revisión\n\nLa revisión cuesta cuarenta euros.\n")
HORARIOS = ("horarios.md", "# Horarios\n\nAbrimos de nueve a veinte.\n")
KEEPS = MemoryPolicy(remember=("preference",))
READS = (Docs(base="clinica", k=2),)


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


def on_a_call(scope: Scope, declaration: Declaration, log: Kept, *, contact: str | None = CONTACT) -> LookupCall:
    """A phone call of the agent in the scope, its caller remembered as the contact."""
    return LookupCall(
        scope=scope, call=CALL, channel=Channel.phone, contact=contact, declaration=declaration, log=log, now=NOW
    )


def asked(tool: PlatformTool, query: str, **more: object) -> LookupRequest:
    """What the worker or the app asks."""
    return LookupRequest(tool=tool, input={"query": query, **more})


async def remembered(sessions: async_sessionmaker[AsyncSession], embedder: Embedder, scope: Scope, *said: str) -> None:
    """Facts the contact's earlier call taught."""
    embedded = await memory.embed_ops(
        embedder, [memory.Op(op="add", text=text, category="preference") for text in said]
    )
    async with sessions.begin() as session:
        taught = memory.Taught(contact=CONTACT, call="call_first", at=LEARNED)
        await memory.apply_ops(session, scope, taught, embedded, model=embedder.model)


async def pushed(
    sessions: async_sessionmaker[AsyncSession], embedder: Embedder, scope: Scope, base: str, *files: tuple[str, str]
) -> None:
    """The files pushed into the base."""
    await bases.push_folder(sessions, embedder, scope, base, list(files), language=None, replace=True)


async def limited(sessions: async_sessionmaker[AsyncSession], scope: Scope, given: billing.Quotas) -> None:
    """The scope's org held to these limits in its env."""
    async with sessions.begin() as session:
        await quotas.put_quotas(session, scope.org, scope.env, given)


# The box's embedder is the providers row's, which every test of the run shares: each lookup here is
# handed the embedder the test says, as the call's host hands the box's.
async def answered_to(
    sessions: async_sessionmaker[AsyncSession], embedder: Embedder | None, call: LookupCall, request: LookupRequest
) -> Answer:
    """The lookup as the endpoint runs it, on this embedder, or on none."""

    async def found(_session: AsyncSession) -> Embedder | None:
        return embedder

    return await lookups.look_up(sessions, found, call, request)


async def looked_up(
    sessions: async_sessionmaker[AsyncSession], embedder: Embedder | None, call: LookupCall, request: LookupRequest
) -> JsonObject:
    """The lookup's answer as the model reads it."""
    return (await answered_to(sessions, embedder, call, request)).dump()


async def searched(
    sessions: async_sessionmaker[AsyncSession], embedder: Embedder, call: LookupCall, query: str, **more: object
) -> SearchFound:
    """What a search answers the call."""
    answer = await answered_to(sessions, embedder, call, asked("search", query, **more))
    assert isinstance(answer, SearchFound)
    return answer


async def recalled(
    sessions: async_sessionmaker[AsyncSession], embedder: Embedder, call: LookupCall, query: str
) -> RecalledFacts:
    """What a recall answers the call."""
    answer = await answered_to(sessions, embedder, call, asked("recall", query))
    assert isinstance(answer, RecalledFacts)
    return answer


# ── recall ──


async def test_recall_answers_the_contacts_facts_with_their_source_and_since_and_logs_the_op(
    sessions: async_sessionmaker[AsyncSession], meant: Embedder, scope: Scope
) -> None:
    """The model reads the fact, the call that taught it and since when; the log keeps one memory.ops."""
    await remembered(sessions, meant, scope, "Es alérgica a la penicilina")
    log = Kept()
    call = on_a_call(scope, Declaration(slug=AGENT, memory=KEEPS), log)
    answered = await looked_up(sessions, meant, call, asked("recall", "alergia penicilina"))
    assert answered == {
        "facts": [{"text": "Es alérgica a la penicilina", "source": "call_first", "since": "2026-09-01"}]
    }
    (entry,) = log.entries
    assert entry.type == "memory.ops"
    (op,) = entry.data["ops"]
    assert (op["op"], op["contact"], op["query"]) == ("recall", CONTACT, "alergia penicilina")


async def test_the_contact_the_model_names_is_never_the_contact_that_is_read(
    sessions: async_sessionmaker[AsyncSession], meant: Embedder, scope: Scope
) -> None:
    """A contact in the tool's input is ignored: the platform's caller is the one recalled."""
    await remembered(sessions, meant, scope, "Prefiere las mañanas")
    stranger = on_a_call(scope, Declaration(slug=AGENT, memory=KEEPS), Kept(), contact="+59899000999")
    assert await looked_up(sessions, meant, stranger, asked("recall", "mañanas", contact=CONTACT)) == {"facts": []}


@pytest.mark.parametrize(
    ("declaration", "contact", "given"),
    [
        (Declaration(slug=AGENT, memory=KEEPS), None, billing.Quotas()),
        (Declaration(slug=AGENT), CONTACT, billing.Quotas()),
        (Declaration(slug=AGENT, memory=KEEPS), CONTACT, billing.Quotas(memory_facts=0)),
    ],
    ids=["a caller nobody knows", "an agent that keeps no memory", "a plan with no memory"],
)
async def test_a_recall_that_may_not_run_answers_nothing_and_writes_no_entry(
    sessions: async_sessionmaker[AsyncSession],
    meant: Embedder,
    scope: Scope,
    declaration: Declaration,
    contact: str | None,
    given: billing.Quotas,
) -> None:
    """No contact, no policy, or memory switched off: the empty shape, and no memory.ops saying it ran."""
    await remembered(sessions, meant, scope, "Es alérgica a la penicilina")
    await limited(sessions, scope, given)
    log = Kept()
    answered = await looked_up(
        sessions, meant, on_a_call(scope, declaration, log, contact=contact), asked("recall", "alergia")
    )
    assert (answered, log.entries) == ({"facts": []}, [])


async def test_a_memory_that_is_full_is_still_read_because_a_cap_is_about_keeping(
    sessions: async_sessionmaker[AsyncSession], meant: Embedder, scope: Scope
) -> None:
    """At its cap the memory keeps nothing new, and is still recalled."""
    await remembered(sessions, meant, scope, "Es alérgica a la penicilina")
    await limited(sessions, scope, billing.Quotas(memory_facts=1))
    call = on_a_call(scope, Declaration(slug=AGENT, memory=KEEPS), Kept())
    assert len((await recalled(sessions, meant, call, "alergia penicilina")).facts) == 1


# ── search ──


async def test_search_answers_chunks_under_the_declarations_own_k_and_logs_the_sources(
    sessions: async_sessionmaker[AsyncSession], meant: Embedder, scope: Scope
) -> None:
    """The declaration's k chunks reach the model with their heading; docs.sources keeps the excerpt."""
    await pushed(sessions, meant, scope, "clinica", TARIFAS, HORARIOS)
    log = Kept()
    call = on_a_call(scope, Declaration(slug=AGENT, bases=(Docs(base="clinica", k=1),)), log)
    answered = await looked_up(sessions, meant, call, asked("search", "la revisión"))
    heading = HEADING_SEPARATOR.join(("Tarifas", "Revisión"))
    assert answered == {
        "chunks": [{"path": "tarifas.md", "heading": heading, "text": "La revisión cuesta cuarenta euros."}]
    }
    (entry,) = log.entries
    assert (entry.type, entry.data["query"]) == ("docs.sources", "la revisión")
    (source,) = entry.data["sources"]
    assert (source["base"], source["excerpt"]) == ("clinica", "La revisión cuesta cuarenta euros.")


async def test_a_class_searching_for_itself_may_say_how_many(
    sessions: async_sessionmaker[AsyncSession], meant: Embedder, scope: Scope
) -> None:
    """A k in the tool's input wins over the declaration's."""
    await pushed(sessions, meant, scope, "clinica", TARIFAS, HORARIOS)
    call = on_a_call(scope, Declaration(slug=AGENT, bases=(Docs(base="clinica", k=1),)), Kept())
    assert len((await searched(sessions, meant, call, "revisión horarios", k=2)).chunks) == 2


async def test_every_attached_base_is_searched_in_one_pass_so_the_scores_are_comparable(
    sessions: async_sessionmaker[AsyncSession], meant: Embedder, scope: Scope
) -> None:
    """Two bases, one search, one docs.sources."""
    await pushed(sessions, meant, scope, "tarifas", TARIFAS)
    await pushed(sessions, meant, scope, "horarios", HORARIOS)
    log = Kept()
    both = (Docs(base="tarifas", k=1), Docs(base="horarios", k=3))
    found = await searched(
        sessions, meant, on_a_call(scope, Declaration(slug=AGENT, bases=both), log), "revisión horarios"
    )
    assert sorted(chunk.path for chunk in found.chunks) == ["horarios.md", "tarifas.md"]
    assert [entry.type for entry in log.entries] == ["docs.sources"]


async def test_the_declarations_min_score_is_what_the_base_is_searched_under(
    sessions: async_sessionmaker[AsyncSession], meant: Embedder, scope: Scope
) -> None:
    """The best chunk scores 1.0 relative to itself; a floor of 1.0 keeps it alone."""
    await pushed(sessions, meant, scope, "clinica", TARIFAS, HORARIOS)
    call = on_a_call(scope, Declaration(slug=AGENT, bases=(Docs(base="clinica", min_score=1.0),)), Kept())
    assert len((await searched(sessions, meant, call, "la revisión")).chunks) == 1


async def test_a_search_that_may_not_run_embeds_nothing_and_writes_no_entry(
    sessions: async_sessionmaker[AsyncSession],
    meant: Embedder,
    meanings: Meanings,
    scope: Scope,
) -> None:
    """No docs declared, or knowledge switched off: the empty shape, the embedder never asked."""
    for declaration, given in (
        (Declaration(slug=AGENT), billing.Quotas()),
        (Declaration(slug=AGENT, bases=READS), billing.Quotas(knowledge_chunks=0)),
    ):
        await limited(sessions, scope, given)
        log = Kept()
        answered = await looked_up(sessions, meant, on_a_call(scope, declaration, log), asked("search", "la revisión"))
        assert (answered, log.entries) == ({"chunks": []}, [])
    assert meanings.inputs() == []


# ── when nothing can run ──


async def test_a_box_with_no_embedder_answers_every_lookup_with_nothing_found(
    sessions: async_sessionmaker[AsyncSession], scope: Scope
) -> None:
    """With no embedder in the providers row both tools answer empty and nothing is logged."""
    log = Kept()
    call = on_a_call(scope, Declaration(slug=AGENT, memory=KEEPS, bases=READS), log)
    recalled = await looked_up(sessions, None, call, asked("recall", "alergia"))
    searched = await looked_up(sessions, None, call, asked("search", "revisión"))
    assert (recalled, searched, log.entries) == ({"facts": []}, {"chunks": []}, [])


async def test_a_down_embedder_finds_nothing_and_the_error_entry_names_the_tool(
    sessions: async_sessionmaker[AsyncSession], scope: Scope
) -> None:
    """The turn never waits on a lookup: an embedder that is down is an error entry and the empty shape."""
    down = Embeddings(script=[httpx.ConnectError("nothing listens")] * 4)
    log = Kept()
    async with httpx.AsyncClient(transport=down.transport()) as http:
        unreachable = Embedder(FLAT, "a-key", http)
        call = on_a_call(scope, Declaration(slug=AGENT, memory=KEEPS), log)
        answered = await looked_up(sessions, unreachable, call, asked("recall", "alergia"))
    assert answered == {"facts": []}
    (entry,) = log.entries
    assert (entry.type, entry.data["code"], entry.data["recoverable"]) == ("error", "recall_skipped", True)
    assert "recall did not run" in str(entry.data["message"])
