"""The judges and the personas a class declares, refused at configure as a PUT of either refuses them."""

from sqlalchemy.ext.asyncio import AsyncSession

from runtime.actor import THE_ORGS_OWN
from runtime.agents.declaration import Declaration
from runtime.exceptions import Conflict
from runtime.judging.repository.judges import JudgeRepository
from runtime.judging.service.judges import judges_of_class
from runtime.judging.service.personas import check_persona_keys, check_persona_models, personas_of_class
from runtime.providers import service as providers
from runtime.providers.catalog import Catalog
from runtime.wire.declaration import JudgesDeclared, PersonasDeclared


# What a PUT of a judge or a persona refuses is refused when the class declares one, and never on
# the call that would have met it: the org's own judge under the name, a persona's model, vendor or
# voice this box lacks, or one on a vendor nobody keyed for the org.
async def check_declaration(
    session: AsyncSession, catalog: Catalog, keyring: providers.Keyring, org: str, agent: str, declaration: Declaration
) -> None:
    """Refuse the judges and the personas the class declares that could not be written for the agent."""
    if declaration.judges is not None:
        await check_judges_of_class(session, org, agent, declaration.judges)
    if declaration.personas is not None:
        check_personas_of_class(catalog, keyring, declaration.personas)


async def check_judges_of_class(session: AsyncSession, org: str, agent: str, class_judges: JudgesDeclared) -> None:
    """Refuse a judge of the class's under a name the org's own judge holds: one name is one question per call."""
    _, judges = judges_of_class(class_judges)
    repository = JudgeRepository(session)
    for spec in judges:
        if await repository.find_clash(org, agent, spec.name) == THE_ORGS_OWN:
            raise Conflict(f"{spec.name} is the org's judge already: one name asks one question of a call")


def check_personas_of_class(catalog: Catalog, keyring: providers.Keyring, class_personas: PersonasDeclared) -> None:
    """Refuse a caller of the class's on a model, a vendor or a voice this box lacks, or one nobody keyed."""
    _, personas = personas_of_class(class_personas)
    for persona in personas:
        check_persona_models(catalog, persona.llm, persona.tts, persona.voice)
        check_persona_keys(catalog, keyring, persona.llm, persona.tts)
