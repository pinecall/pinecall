"""What an agent built in Studio says of itself before anybody calls it: its instructions and tools, for a writer."""

from sqlalchemy.ext.asyncio import AsyncSession

from runtime.actor import Scope
from runtime.evals import service as evals
from runtime.studio.repository import StudioAgentRepository
from runtime.studio.service import declaring, prompt
from runtime.studio.service import definition as definitions
from runtime.wire.studio import Definition

OPENS_WITH = "Opens the call with: {say}"


def brief_definition(definition: Definition) -> evals.Brief:
    """The definition as a writer reads it: the instructions with no call's values in them, how it opens, its tools."""
    said = [prompt.fill(definition.instructions, {})]
    if definition.greeting is not None and definition.greeting.say:
        said.append(OPENS_WITH.format(say=definition.greeting.say))
    tools = tuple(f"{spec.name}: {spec.description}" for spec in declaring.list_tool_specs(definition))
    return evals.Brief(prompt="\n\n".join(said), tools=tools)


# A class agent writes its prompt per call, so a briefing or Generate reads its newest call; a Studio
# agent is a definition the gateway holds, read here off its newest release in the scope's env (what
# the editor saved, what the next call runs on), so a caller is briefed on it, and callers are
# written for it, before anybody has called it.
class StudioAgents:
    """The describer the lifespan hands the harness: a Studio agent's newest release, or nothing for any other."""

    async def brief_of(self, session: AsyncSession, scope: Scope, slug: str) -> evals.Brief | None:
        """The agent's definition as a writer reads it; None for an agent Studio does not hold in this env."""
        kept = await StudioAgentRepository(session).list_newest(scope.env, org=scope.org, name=slug)
        return brief_definition(definitions.parse(kept[0].definition)) if kept else None
