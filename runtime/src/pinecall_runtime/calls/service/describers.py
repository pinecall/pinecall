"""Who can say what an agent does with no call to read it from: Studio, for the agents the gateway holds."""

from typing import Protocol

from sqlalchemy.ext.asyncio import AsyncSession

from pinecall_runtime.judging import service as judging
from pinecall_runtime.kit.auth import Scope


class Describer(Protocol):
    """A domain above the calls that holds agents' definitions, asked what one says of itself."""

    async def brief_of(self, session: AsyncSession, scope: Scope, slug: str) -> judging.Brief | None:
        """What the agent says of itself, as a writer reads it; None for an agent this describer does not hold."""
        ...


# A class agent writes its prompt per call, so what it is about is read off its newest call. An
# agent built in Studio is a definition the gateway holds: its instructions and tools say what it does
# before anybody has called it, and the domain that holds them is above this one, so it is asked
# through here, as the lifespan wires it.
class Describers:
    """The describers wired at start, asked in turn; the first that knows the agent answers."""

    def __init__(self) -> None:
        self._each: list[Describer] = []

    def add(self, one: Describer) -> None:
        """One more domain that can describe an agent."""
        self._each.append(one)

    async def brief_of(self, session: AsyncSession, scope: Scope, slug: str) -> judging.Brief | None:
        """The agent as the first describer that holds it says it; None when none does."""
        for one in self._each:
            told = await one.brief_of(session, scope, slug)
            if told is not None:
                return told
        return None
