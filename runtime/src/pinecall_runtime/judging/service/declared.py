"""The judges and the personas a class declares, refused at configure as a PUT of either refuses them."""

from sqlalchemy.ext.asyncio import AsyncSession

from pinecall_runtime.agents.declaration import AgentConfig
from pinecall_runtime.exceptions import Conflict
from pinecall_runtime.judging.repository import JudgeRepository
from pinecall_runtime.judging.service.judges import TAKEN, declared_judges
from pinecall_runtime.judging.service.personas import check_persona_keys, check_persona_models, declared_personas
from pinecall_runtime.kit.auth import THE_ORGS_OWN
from pinecall_runtime.providers import service as providers
from pinecall_runtime.wire.parts import JudgesDeclared, PersonasDeclared


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
