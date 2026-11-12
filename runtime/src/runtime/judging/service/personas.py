"""The personas an agent is called by in its simulations, resolved once: Pinecall's as played, its own, its class's."""

from collections.abc import Mapping, Sequence
from dataclasses import asdict, dataclass, field, replace
from datetime import datetime
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from runtime.actor import Scope
from runtime.agents import service as agents
from runtime.agents.declaration import Agent
from runtime.enums import Stage
from runtime.exceptions import Conflict, NotFound, ValidationError
from runtime.judging.models import AgentPersona, PersonaSwitch
from runtime.judging.repository.personas import PersonaRepository
from runtime.judging.repository.switches import PersonaSwitchRepository
from runtime.judging.service import library
from runtime.judging.service.specs import Behavior, Persona, check_persona_name
from runtime.kit.crypto import Vault
from runtime.kit.text import Json, JsonObject
from runtime.providers import service as providers
from runtime.providers.catalog import Catalog
from runtime.providers.stage import Voice
from runtime.wire.declaration import CallerBehavior, PersonaDeclaration, PersonasDeclared

PINECALL = "pinecall"
THE_CLASS = "class"
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

# What a write may say of one of Pinecall's: its switch, and how it is played.
PLAYED_FIELDS = frozenset({"llm", "tts", "voice"})
LIBRARY_FIELDS = frozenset({"on", "llm", "tts", "voice"})


@dataclass(frozen=True, slots=True)
class Played:
    """How one of the library's personas is played for an agent; None is the runtime's choice."""

    llm: str | None = None
    tts: str | None = None
    voice: str | None = None


@dataclass(frozen=True, slots=True)
class RosterPersona:
    """One caller an agent's runs may play: who it is, whose it is, and whether it is played."""

    persona: Persona
    agent: str
    # "pinecall" for the library's, "class" for one the agent's class declares, else the agent's slug.
    owner: str
    on: bool
    # True on one the class declares, its switch of a library persona or its own: no endpoint writes it.
    fixed: bool = False
    # The library's: one line on what it is for, and the version of its page.
    summary: str | None = None
    version: int | None = None
    # The agent's own: who wrote it last, and when.
    author: str | None = None
    set_at: datetime | None = None


@dataclass(frozen=True, slots=True)
class Wanted:
    """What a write says of a persona: the caller whole, or for one of Pinecall's its switch and how it is played."""

    about: str = ""
    goal: str = ""
    style: str = ""
    facts: Mapping[str, str] = field(default_factory=dict[str, str])
    state: JsonObject = field(default_factory=dict[str, Json])
    llm: str | None = None
    tts: str | None = None
    voice: str | None = None
    expects: Sequence[str] = ()
    tags: Sequence[str] = ()
    behavior: CallerBehavior = field(default_factory=CallerBehavior)
    # The name this caller had, when the write renames it.
    was: str | None = None
    # One of Pinecall's personas: whether the agent's runs play it.
    on: bool | None = None
    # The fields the write named, so one of Pinecall's is told apart from a caller written whole.
    named: frozenset[str] = frozenset()


# The class, when it declares its personas, is the agent's roster: its own are read and the agent's
# rows are not; Pinecall's are played by name either way, as the org plays them. Pinecall's come
# first, each as the org and the agent switch and play it.
async def roster_of(
    session: AsyncSession, org: str, agent: str, class_personas: PersonasDeclared | None = None
) -> tuple[RosterPersona, ...]:
    """Pinecall's personas as switched and played for the agent, then its own (its class's when it declares them)."""
    rows = await PersonaSwitchRepository(session).list_for_agent(org, agent)
    played = _plays_of(rows)
    if class_personas is None:
        switches = {row.name: row.is_on for row in rows}
        kept = await PersonaRepository(session).list_of_agent(org, agent)
        own = tuple(_persona_of_row(row) for row in kept)
    else:
        switches, of_the_class = personas_of_class(class_personas)
        own = tuple(RosterPersona(persona, agent, owner=THE_CLASS, on=True, fixed=True) for persona in of_the_class)
    fixed = class_personas is not None
    pinecalls = tuple(
        RosterPersona(
            as_played(written.persona, played.get(name, Played())),
            agent,
            owner=PINECALL,
            on=switches.get(name, written.on_by_default),
            fixed=fixed,
            summary=written.summary,
            version=written.version,
        )
        for name, written in library.library_personas().items()
    )
    return (*pinecalls, *own)


async def list_personas(session: AsyncSession, org: str, agent: Agent) -> tuple[RosterPersona, ...]:
    """The agent's roster, with what its class declares."""
    class_personas = None if agent.declaration is None else agent.declaration.personas
    return await roster_of(session, org, agent.slug, class_personas)


# Every agent's callers, the org's roster at once: one list for both envs, as an agent's is.
async def list_of_org(session: AsyncSession, org: str) -> tuple[RosterPersona, ...]:
    """Every agent's own callers, by agent and then by name."""
    return tuple(_persona_of_row(row) for row in await PersonaRepository(session).list_of_org(org))


# One of the agent's own wins over one of Pinecall's of the same name: it is listed after it.
async def persona_named(
    session: AsyncSession, org: str, agent: str, name: str, class_personas: PersonasDeclared | None = None
) -> Persona | None:
    """The agent's own persona by that name (its class's when it declares them), else Pinecall's as played; or None."""
    roster = await roster_of(session, org, agent, class_personas)
    return {listed.persona.name: listed.persona for listed in roster}.get(name)


async def get_persona(
    session: AsyncSession, org: str, agent: str, name: str, class_personas: PersonasDeclared | None = None
) -> Persona:
    """The persona of that name an agent's calls may be played by; refused when there is none."""
    found = await persona_named(session, org, agent, name, class_personas)
    if found is None:
        raise NotFound(NOBODY.format(name=name, agent=agent))
    return found


# A model or a vendor this box lacks, or that nobody keyed, is refused when written, not on the call
# that plays it; while the agent's class declares its personas, nothing is written here (409 naming
# the class). One of Pinecall's is switched and told how it is played; one of the agent's own is
# written whole; never the other way.
async def write_persona(
    session: AsyncSession, vault: Vault, scope: Scope, agent: Agent, name: str, wanted: Wanted, *, by: str
) -> tuple[RosterPersona, ...]:
    """Write one of the agent's callers whole, or rename one from `was`; or switch Pinecall's; the roster after."""
    agents.refuse_what_the_class_sets(agent, ("personas",))
    catalog = await providers.get_catalog(session)
    check_persona_models(catalog, wanted.llm, wanted.tts, wanted.voice)
    check_persona_keys(catalog, await providers.keys_of(session, vault, scope), wanted.llm, wanted.tts)
    if name in library.library_personas():
        await _write_pinecalls(session, scope.org, agent.slug, name, wanted, by=by)
    elif wanted.on is not None:
        raise Conflict(NOT_A_SWITCH.format(name=name))
    else:
        await put_persona(session, scope.org, agent.slug, persona_of(name, wanted), by=by, was=wanted.was)
    return await roster_of(session, scope.org, agent.slug)


# A `was` that is the same name, or none, renames nothing.
async def put_persona(
    session: AsyncSession, org: str, agent: str, persona: Persona, *, by: str, was: str | None
) -> None:
    """Write one of the agent's callers whole: a new one, the same name again, or a rename."""
    repository = PersonaRepository(session)
    if was is not None and was != persona.name:
        if await repository.find(org, agent, was) is None:
            raise NotFound(NOBODY.format(name=was, agent=agent))
        if await repository.find(org, agent, persona.name) is not None:
            raise Conflict(TAKEN.format(name=persona.name, agent=agent))
        await repository.delete_named(org, agent, was)
    await repository.put(org, agent, name=persona.name, author=by, **_columns_of(persona))


async def delete_persona(session: AsyncSession, org: str, agent: Agent, name: str) -> tuple[RosterPersona, ...]:
    """Forget one of the agent's callers; 404 for a name nobody wrote, 409 for Pinecall's or the class's."""
    agents.refuse_what_the_class_sets(agent, ("personas",))
    if name in library.library_personas():
        raise Conflict(NOT_YOURS.format(name=name))
    if not await PersonaRepository(session).delete_named(org, agent.slug, name):
        raise NotFound(NOBODY.format(name=name, agent=agent.slug))
    return await roster_of(session, org, agent.slug)


def check_persona_models(catalog: Catalog, llm: str | None, tts: str | None, voice: str | None) -> None:
    """Refuse a model, a vendor or a voice this box lacks when a persona is written, not on the call that plays it."""
    agents.name_model(llm or None, Stage.llm, in_use=catalog.default_vendors[Stage.llm])
    # The caller's `tts` names a vendor, never a model: a word that is no vendor is refused as one.
    vendor = catalog.default_vendors[Stage.tts] if not tts else providers.vendor_doing(tts, Stage.tts)
    # A vendor whose voices the catalog lists has the voice there or not at all; one it lists none
    # for (every voice is the vendor's own) takes the id as given.
    listed = providers.list_in_catalog(catalog, vendor, None)
    if voice and listed and all(one.id != voice for one in listed):
        raise ValidationError(NO_SUCH_VOICE.format(vendor=vendor, voice=voice))


# The run says it the same way when no key stands behind the vendor, so the writer hears it first.
def check_persona_keys(catalog: Catalog, keys: providers.Keyring, llm: str | None, tts: str | None) -> None:
    """Refuse a model or a voice's vendor that nobody keyed for the org, or the box lends it no key for."""
    model = agents.name_model(llm or None, Stage.llm, in_use=catalog.default_vendors[Stage.llm])
    if model is not None:
        providers.stage_on_its_key(Stage.llm, model, catalog, keys)
    if tts:
        providers.stage_on_its_key(Stage.tts, Voice(vendor=providers.vendor_doing(tts, Stage.tts)), catalog, keys)


def personas_of_class(class_personas: PersonasDeclared) -> tuple[dict[str, bool], tuple[Persona, ...]]:
    """The library's switches and the agent's own callers as the class declares them; refused by sentence."""
    written = library.library_personas()
    switches = library.switches_of_class(class_personas.on, written, "personas")
    own = tuple(persona_of(persona.name, persona) for persona in class_personas.own)
    library.check_own_names([persona.name for persona in own], written, "personas")
    return switches, own


def persona_of(name: str, said: Wanted | PersonaDeclaration) -> Persona:
    """A persona as a write says it, or as a class declares it; a name that is not one is refused."""
    check_persona_name(name)
    return Persona(
        name=name,
        goal=said.goal,
        style=said.style,
        about=said.about,
        facts=dict(said.facts),
        state=dict(said.state),
        llm=said.llm or None,
        tts=said.tts or None,
        voice=said.voice or None,
        expects=tuple(said.expects),
        tags=tuple(said.tags),
        behavior=behavior_of(said.behavior),
    )


# The one reading of how a caller acts off the wire, where the value's own sentences refuse it.
def behavior_of(said: CallerBehavior) -> Behavior:
    """How a caller acts as the wire says it, as the value."""
    return Behavior(**said.model_dump())


def as_played(persona: Persona, chosen: Played) -> Persona:
    """A library persona as the org plays it: its own model and voice, where it chose them."""
    return replace(persona, llm=chosen.llm, tts=chosen.tts, voice=chosen.voice)


# What a write names of how it is played is written; what it leaves out stays as it was.
async def _write_pinecalls(session: AsyncSession, org: str, agent: str, name: str, wanted: Wanted, *, by: str) -> None:
    if not wanted.named & LIBRARY_FIELDS or wanted.named - LIBRARY_FIELDS:
        raise Conflict(ONLY_ON.format(name=name))
    repository = PersonaSwitchRepository(session)
    if wanted.on is not None:
        await repository.switch(org, agent, (name,), on=wanted.on, author=by)
    plays = wanted.named & PLAYED_FIELDS
    if not plays:
        return
    rows = await repository.list_for_agent(org, agent)
    was = _plays_of(rows).get(name, Played())
    chosen = replace(was, **{one: getattr(wanted, one) or None for one in plays})
    switches = {row.name: row.is_on for row in rows}
    is_on = switches.get(name, library.library_personas()[name].on_by_default)
    await repository.play(org, agent, name, is_on=is_on, llm=chosen.llm, tts=chosen.tts, voice=chosen.voice, author=by)


# How each library persona is played for the agent: the agent's row after the org's, as a whole.
def _plays_of(rows: Sequence[PersonaSwitch]) -> dict[str, Played]:
    return {
        row.name: Played(row.llm, row.tts, row.voice)
        for row in rows
        if row.llm is not None or row.tts is not None or row.voice is not None
    }


def _persona_of_row(row: AgentPersona) -> RosterPersona:
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
    return RosterPersona(persona, row.agent, owner=row.agent, on=True, author=row.author, set_at=row.set_at)


# A persona's fields are its row's columns, by the same names.
def _columns_of(persona: Persona) -> dict[str, Any]:
    kept = asdict(persona)
    del kept["name"]
    return {**kept, "expects": list(persona.expects), "tags": list(persona.tags)}
