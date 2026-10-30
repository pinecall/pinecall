"""The judges and the personas a class declares: refused at configure as a PUT refuses them, read as the class's."""

from collections.abc import Mapping, Sequence

from sqlalchemy.ext.asyncio import AsyncSession

from pinecall_runtime.agents.declaration import AgentConfig
from pinecall_runtime.exceptions import Conflict, ValidationError
from pinecall_runtime.judging.repository import JudgeRepository
from pinecall_runtime.judging.service import catalog
from pinecall_runtime.judging.service.judges import TAKEN, spec_of
from pinecall_runtime.judging.service.personas import check_persona_keys, check_persona_models, persona_of
from pinecall_runtime.judging.service.specs import JudgeSpec, Persona
from pinecall_runtime.kit.auth import THE_ORGS_OWN
from pinecall_runtime.providers import service as providers
from pinecall_runtime.wire.parts import JudgesDeclared, PersonasDeclared

NONE_OF_PINECALLS = "{name} is none of Pinecall's {kind}: `pinecall {kind} list` names them"
ONE_OF_PINECALLS = (
    "{name} is one of Pinecall's {kind}: switch it on in the class's `{kind}`, or write your own under another name"
)
TWICE = "the class declares two {kind} called {name}"


def declared_judges(declared: JudgesDeclared) -> tuple[dict[str, bool], tuple[JudgeSpec, ...]]:
    """The library's switches and the agent's own judges as the class declares them; refused by sentence."""
    library = catalog.library_judges()
    switches = _switches(declared.on, library, "judges")
    own = tuple(spec_of(judge.name, judge) for judge in declared.own)
    _own_names([spec.name for spec in own], library, "judges")
    return switches, own


def declared_personas(declared: PersonasDeclared) -> tuple[dict[str, bool], tuple[Persona, ...]]:
    """The library's switches and the agent's own callers as the class declares them; refused by sentence."""
    library = catalog.library_personas()
    switches = _switches(declared.on, library, "personas")
    own = tuple(persona_of(persona.name, persona) for persona in declared.own)
    _own_names([persona.name for persona in own], library, "personas")
    return switches, own


# What a PUT of a judge or a persona refuses is refused when the class declares one, and never on
# the call that would have met it: the org's own judge under the name, a persona's model, vendor or
# voice this box lacks, or one on a vendor nobody keyed for the org.
async def check_declared(
    session: AsyncSession,
    configured: providers.Catalog,
    keyring: providers.Keyring,
    org: str,
    agent: str,
    config: AgentConfig,
) -> None:
    """Refuse the judges and the personas the class declares that could not be written for the agent."""
    if config.judges is not None:
        await check_declared_judges(session, org, agent, config.judges)
    if config.personas is not None:
        check_declared_personas(configured, keyring, config.personas)


async def check_declared_judges(session: AsyncSession, org: str, agent: str, declared: JudgesDeclared) -> None:
    """Refuse a judge of the class's under a name the org's own judge holds: one name is one question per call."""
    _, judges = declared_judges(declared)
    repository = JudgeRepository(session)
    for spec in judges:
        if await repository.clashing(org, agent, spec.name) == THE_ORGS_OWN:
            raise Conflict(TAKEN.format(name=spec.name, whose="the org's"))


def check_declared_personas(
    configured: providers.Catalog, keyring: providers.Keyring, declared: PersonasDeclared
) -> None:
    """Refuse a caller of the class's on a model, a vendor or a voice this box lacks, or one nobody keyed."""
    _, personas = declared_personas(declared)
    for persona in personas:
        check_persona_models(configured, persona.llm, persona.tts, persona.voice)
        check_persona_keys(configured, keyring, persona.llm, persona.tts)


# A class says "none but Pinecall's" with an empty list: a switch it leaves out is off.
def _switches(on: Sequence[str], library: Mapping[str, object], kind: str) -> dict[str, bool]:
    for name in on:
        if name not in library:
            raise ValidationError(NONE_OF_PINECALLS.format(name=name, kind=kind))
    return {name: name in on for name in library}


def _own_names(names: Sequence[str], library: Mapping[str, object], kind: str) -> None:
    for name in names:
        if name in library:
            raise ValidationError(ONE_OF_PINECALLS.format(name=name, kind=kind))
        if names.count(name) > 1:
            raise ValidationError(TWICE.format(name=name, kind=kind))
