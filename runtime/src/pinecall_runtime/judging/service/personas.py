"""The personas an agent is called by in its simulations, and which of the library's it plays."""

from collections.abc import Sequence
from dataclasses import asdict, dataclass, replace
from datetime import datetime

from sqlalchemy.ext.asyncio import AsyncSession

from pinecall_runtime.agents.declaration import Voice
from pinecall_runtime.agents.service import tuning
from pinecall_runtime.exceptions import Conflict, NotFound, ValidationError
from pinecall_runtime.judging.models import AgentPersona
from pinecall_runtime.judging.repository import PersonaRepository, PersonaSwitchRepository
from pinecall_runtime.judging.schemas import CallerBehavior, PersonaRequest, PersonaRow, ProposedPersona
from pinecall_runtime.judging.service import catalog
from pinecall_runtime.judging.service.specs import Behavior, Persona, check_persona_name
from pinecall_runtime.providers import service as providers

PINECALL = "pinecall"
NOBODY = "no persona called {name} for {agent}"
TAKEN = "{agent} has a persona called {name} already"
ONLY_ON = (
    "{name} is one of Pinecall's personas: only whether the agent's runs play it and how it is "
    "played are written (on or off, the model, the voice's vendor and the voice); a caller of your "
    "own takes a name of your own"
)
NOT_A_SWITCH = "{name} is a persona of the agent's own: it is played while it is written"
NOT_YOURS = "{name} is one of Pinecall's personas and is never deleted: `pinecall personas off {name}` turns it off"
NO_SUCH_VOICE = "{vendor} lists no voice {voice}: `pinecall voices list --tts {vendor}` names the ones it has"

# What a PUT may write of one of Pinecall's: its switch, and how it is played.
PLAYED_FIELDS = frozenset({"llm", "tts", "voice"})
LIBRARY_FIELDS = frozenset({"on", "llm", "tts", "voice"})


@dataclass(frozen=True, slots=True)
class Played:
    """How one of the library's personas is played for an agent; None is the runtime's choice."""

    llm: str | None = None
    tts: str | None = None
    voice: str | None = None


@dataclass(frozen=True, slots=True)
class StoredPersona:
    """A persona as the agent keeps it: whose it is, who wrote it last, and when."""

    agent: str
    persona: Persona
    author: str
    set_at: datetime


async def personas_of(session: AsyncSession, org: str, agent: str) -> list[StoredPersona]:
    """The agent's own callers, by name."""
    return [_stored(row) for row in await PersonaRepository(session).of_agent(org, agent)]


async def every_persona(session: AsyncSession, org: str) -> list[StoredPersona]:
    """Every agent's own callers, by agent and then by name."""
    return [_stored(row) for row in await PersonaRepository(session).of_org(org)]


async def get_persona(session: AsyncSession, org: str, agent: str, name: str) -> StoredPersona | None:
    """One of the agent's own callers, by name."""
    row = await PersonaRepository(session).get(org, agent, name)
    return None if row is None else _stored(row)


async def persona_named(session: AsyncSession, org: str, agent: str, name: str) -> Persona | None:
    """The agent's own persona by that name, else Pinecall's as the org plays it; None for neither."""
    own = await get_persona(session, org, agent, name)
    if own is not None:
        return own.persona
    written = catalog.library_personas().get(name)
    if written is None:
        return None
    chosen = (await played_for(session, org, agent)).get(name, Played())
    return catalog.played_on(written, chosen.llm, chosen.tts, chosen.voice).persona


# A `was` that is the same name, or none, renames nothing.
async def put_persona(
    session: AsyncSession, org: str, agent: str, persona: Persona, *, by: str, was: str | None
) -> None:
    """Write one of the agent's callers whole: a new one, the same name again, or a rename."""
    repository = PersonaRepository(session)
    if was is not None and was != persona.name:
        if await repository.get(org, agent, was) is None:
            raise NotFound(NOBODY.format(name=was, agent=agent))
        if await repository.get(org, agent, persona.name) is not None:
            raise Conflict(TAKEN.format(name=persona.name, agent=agent))
        await repository.drop(org, agent, was)
    await repository.put(
        org,
        agent,
        name=persona.name,
        author=by,
        about=persona.about,
        goal=persona.goal,
        style=persona.style,
        facts=dict(persona.facts),
        state=dict(persona.state),
        llm=persona.llm,
        tts=persona.tts,
        voice=persona.voice,
        expects=list(persona.expects),
        tags=list(persona.tags),
        behavior=asdict(persona.behavior),
    )


async def delete_persona(session: AsyncSession, org: str, agent: str, name: str) -> None:
    """Forget one of the agent's callers; 404 for a name nobody wrote, 409 for Pinecall's."""
    if name in catalog.library_personas():
        raise Conflict(NOT_YOURS.format(name=name))
    if not await PersonaRepository(session).drop(org, agent, name):
        raise NotFound(NOBODY.format(name=name, agent=agent))


async def persona_switches_for(session: AsyncSession, org: str, agent: str) -> dict[str, bool]:
    """Which of the library's personas the agent's runs play, as the org and the agent set them."""
    return {row.name: row.is_on for row in await PersonaSwitchRepository(session).for_agent(org, agent)}


async def switch_personas(
    session: AsyncSession, org: str, agent: str, names: Sequence[str], *, on: bool, by: str
) -> None:
    """Turn library personas on or off, for the org (agent '') or for one agent."""
    await PersonaSwitchRepository(session).switch(org, agent, names, on=on, author=by)


# How each library persona is played for the agent: the agent's row after the org's, as a whole.
async def played_for(session: AsyncSession, org: str, agent: str) -> dict[str, Played]:
    """How each of the library's personas is played for the agent, where anything is set."""
    rows = await PersonaSwitchRepository(session).for_agent(org, agent)
    return {
        row.name: Played(row.llm, row.tts, row.voice)
        for row in rows
        if row.llm is not None or row.tts is not None or row.voice is not None
    }


# One of Pinecall's is switched, told how it is played, or both; anything else of it is refused.
# What a PUT names of how it is played is written; what it leaves out stays as it was.
async def write_library_persona(
    session: AsyncSession, org: str, agent: str, name: str, body: PersonaRequest, *, by: str
) -> None:
    """Switch one of Pinecall's personas for the agent, and set how it is played."""
    written_fields = body.model_fields_set
    if not written_fields & LIBRARY_FIELDS or written_fields - LIBRARY_FIELDS:
        raise Conflict(ONLY_ON.format(name=name))
    repository = PersonaSwitchRepository(session)
    if body.on is not None:
        await repository.switch(org, agent, (name,), on=body.on, author=by)
    plays = written_fields & PLAYED_FIELDS
    if not plays:
        return
    was = (await played_for(session, org, agent)).get(name, Played())
    chosen = replace(was, **{field: getattr(body, field) or None for field in plays})
    is_on = (await persona_switches_for(session, org, agent)).get(name, catalog.library_personas()[name].on_by_default)
    await repository.play(org, agent, name, is_on=is_on, llm=chosen.llm, tts=chosen.tts, voice=chosen.voice, author=by)


def check_persona_models(configured: providers.Catalog, llm: str | None, tts: str | None, voice: str | None) -> None:
    """Refuse a model, a vendor or a voice this box lacks when a persona is written, not on the call that plays it."""
    tuning.model_named(llm or None, "llm", in_use=configured.default_vendors["llm"])
    # The caller's `tts` names a vendor, never a model: a word that is no vendor is refused as one.
    vendor = configured.default_vendors["tts"] if not tts else providers.vendor_doing(tts, "tts")
    # A vendor whose voices the catalog lists has the voice there or not at all; one it lists none
    # for (every voice is the vendor's own) takes the id as given.
    listed = providers.listed_in_catalog(configured, vendor, None)
    if voice and listed and all(one.id != voice for one in listed):
        raise ValidationError(NO_SUCH_VOICE.format(vendor=vendor, voice=voice))


# The run says it the same way when no key stands behind the vendor, so the writer hears it first.
def check_persona_keys(
    configured: providers.Catalog, keys: providers.Keyring, llm: str | None, tts: str | None
) -> None:
    """Refuse a model or a voice's vendor that nobody keyed for the org, or the box lends it no key for."""
    in_use = configured.default_vendors
    model = tuning.model_named(llm or None, "llm", in_use=in_use["llm"])
    if model is not None:
        providers.stage_on_its_key("llm", model, configured, keys)
    if tts:
        providers.stage_on_its_key("tts", Voice(provider=providers.vendor_doing(tts, "tts")), configured, keys)


def persona_of(name: str, body: PersonaRequest) -> Persona:
    """A persona as a request writes it; a name that is not one is refused."""
    check_persona_name(name)
    return Persona(
        name=name,
        goal=body.goal,
        style=body.style,
        about=body.about,
        facts=dict(body.facts),
        state=dict(body.state),
        llm=body.llm or None,
        tts=body.tts or None,
        voice=body.voice or None,
        expects=tuple(body.expects),
        tags=tuple(body.tags),
        behavior=Behavior(**body.behavior.model_dump()),
    )


# An agent's list carries Pinecall's first, each as the org and the agent switch and play it.
async def list_personas(session: AsyncSession, org: str, agent: str) -> list[PersonaRow]:
    """Pinecall's personas as switched for the agent, then the agent's own, by name."""
    switches = await persona_switches_for(session, org, agent)
    played = await played_for(session, org, agent)
    rows: list[PersonaRow] = []
    for written in catalog.library_personas().values():
        chosen = played.get(written.persona.name, Played())
        rows.append(_library_row(agent, catalog.played_on(written, chosen.llm, chosen.tts, chosen.voice), switches))
    rows += [persona_row(stored) for stored in await personas_of(session, org, agent)]
    return rows


def persona_row(stored: StoredPersona) -> PersonaRow:
    """One of an agent's own callers as the list shows it."""
    return _row(
        stored.persona,
        agent=stored.agent,
        owner=stored.agent,
        on=True,
        author=stored.author,
        set_at=stored.set_at.timestamp(),
    )


def proposed_row(persona: Persona) -> ProposedPersona:
    """A persona as a proposal is sent: saved nowhere yet."""
    return ProposedPersona(
        name=persona.name,
        about=persona.about,
        goal=persona.goal,
        style=persona.style,
        facts=dict(persona.facts),
        expects=list(persona.expects),
        tags=list(persona.tags),
        behavior=CallerBehavior.model_validate(asdict(persona.behavior)),
    )


def _library_row(agent: str, written: catalog.WrittenPersona, switches: dict[str, bool]) -> PersonaRow:
    return _row(
        written.persona,
        agent=agent,
        owner=PINECALL,
        on=switches.get(written.persona.name, written.on_by_default),
        summary=written.summary,
        version=written.version,
    )


def _row(
    persona: Persona,
    *,
    agent: str,
    owner: str,
    on: bool,
    summary: str | None = None,
    version: int | None = None,
    author: str | None = None,
    set_at: float | None = None,
) -> PersonaRow:
    return PersonaRow(
        agent=agent,
        name=persona.name,
        owner=owner,
        on=on,
        about=persona.about,
        goal=persona.goal,
        style=persona.style,
        facts=dict(persona.facts),
        state=dict(persona.state),
        llm=persona.llm,
        tts=persona.tts,
        voice=persona.voice,
        expects=list(persona.expects),
        tags=list(persona.tags),
        behavior=CallerBehavior.model_validate(asdict(persona.behavior)),
        summary=summary,
        version=version,
        author=author,
        set_at=set_at,
    )


def _stored(row: AgentPersona) -> StoredPersona:
    persona = Persona(
        name=row.name,
        goal=row.goal,
        style=row.style,
        about=row.about,
        facts={str(key): str(value) for key, value in row.facts.items()},
        state=dict(row.state),
        llm=row.llm,
        tts=row.tts,
        voice=row.voice,
        expects=tuple(str(line) for line in row.expects),
        tags=tuple(str(tag) for tag in row.tags),
        behavior=Behavior(**row.behavior),
    )
    return StoredPersona(agent=row.agent, persona=persona, author=row.author, set_at=row.set_at)
