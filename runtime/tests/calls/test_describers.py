"""The describers wired into the calls: asked in turn, the first that holds the agent answers, none answers None."""

import asyncio

from sqlalchemy.ext.asyncio import AsyncSession

from pinecall_runtime.calls import service as calls
from pinecall_runtime.enums import Env
from pinecall_runtime.judging import service as judging
from pinecall_runtime.kit.auth import Scope

SCOPE = Scope(org="org_a", env=Env.sandbox)


class Holding:
    """A describer that holds one agent."""

    def __init__(self, slug: str, prompt: str) -> None:
        self.slug, self.prompt = slug, prompt

    async def brief_of(self, session: AsyncSession, scope: Scope, slug: str) -> judging.Brief | None:
        return judging.Brief(prompt=self.prompt) if slug == self.slug else None


def test_the_first_describer_that_holds_the_agent_answers() -> None:
    describers = calls.Describers()
    describers.add(Holding("clinic", "the clinic's"))
    describers.add(Holding("clinic", "a later one's"))
    describers.add(Holding("shop", "the shop's"))
    session = AsyncSession()
    assert asyncio.run(describers.brief_of(session, SCOPE, "clinic")) == judging.Brief(prompt="the clinic's")
    assert asyncio.run(describers.brief_of(session, SCOPE, "shop")) == judging.Brief(prompt="the shop's")


def test_an_agent_no_describer_holds_is_none() -> None:
    describers = calls.Describers()
    describers.add(Holding("clinic", "the clinic's"))
    assert asyncio.run(describers.brief_of(AsyncSession(), SCOPE, "bank")) is None
    assert asyncio.run(calls.Describers().brief_of(AsyncSession(), SCOPE, "clinic")) is None
