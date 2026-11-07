"""What an agent built in Studio says of itself before anybody calls it: its instructions and tools, for a writer."""

from sqlalchemy.ext.asyncio import AsyncSession

from pinecall_runtime.hosting import service as hosting
from pinecall_runtime.judging import service as judging
from pinecall_runtime.kit.auth import Scope
from pinecall_runtime.studio.schemas import Definition
from pinecall_runtime.studio.service import definition as defined

OPENS_WITH = "Opens the call with: {say}"


def brief_of_definition(definition: Definition) -> judging.Brief:
    """The definition as a writer reads it: the instructions with no call's values in them, how it opens, its tools."""
    said = [defined.rendered(definition.instructions, {})]
    if definition.greeting is not None and definition.greeting.say:
        said.append(OPENS_WITH.format(say=definition.greeting.say))
    tools = tuple(f"{spec.name}: {spec.description}" for spec in defined.tool_specs(definition))
    return judging.Brief(prompt="\n\n".join(said), tools=tools)


# A class agent writes its prompt per call, so a briefing or Generate reads its newest call; a Studio
# agent is a definition the gateway holds, read here off its newest release in the scope's env —
# what the editor saved, what the next call runs on — so a caller is briefed on it, and callers are
# written for it, before anybody has called it.
class StudioAgents:
    """The describer the lifespan wires into the calls: a Studio agent's newest release, or nothing for any other."""

    async def brief_of(self, session: AsyncSession, scope: Scope, slug: str) -> judging.Brief | None:
        """The agent's definition as a writer reads it; None for an agent Studio does not hold in this env."""
        app = hosting.App(org=scope.org, env=scope.env, name=slug)
        if await hosting.kind_of(session, app) != hosting.STUDIO:
            return None
        releases = await hosting.releases_of(session, app)
        if not releases:
            return None
        source = await hosting.source_of(session, app, releases[0].release)
        return brief_of_definition(defined.parsed(source.data))
