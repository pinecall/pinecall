"""Whom a simulation briefs before it phones, and who says what an agent is: the first describer that holds it."""

from sqlalchemy.ext.asyncio import AsyncSession

from runtime.actor import Scope
from runtime.enums import Env
from runtime.evals.service.briefs import Describers, as_scenario, is_from_the_library
from runtime.evals.service.writers import Brief
from runtime.judging import service as judging

SCOPE = Scope(org="org_a", env=Env.sandbox)


def test_only_a_caller_of_the_library_is_briefed() -> None:
    assert is_from_the_library(judging.Persona(name="elderly-slow", goal="help", style="slow"))
    assert not is_from_the_library(judging.Persona(name="marta-cancels", goal="cancel", style="curt"))


def test_an_agent_nobody_has_called_with_no_tools_is_nothing_to_brief_on() -> None:
    assert not Brief().says_anything
    assert Brief(tools=("book: books a visit",)).says_anything
    assert Brief(prompt="You answer for a clinic.").says_anything


def test_a_scenario_given_is_what_the_caller_phones_about_with_its_facts_over_its_own() -> None:
    caller = judging.Persona(name="elderly-slow", goal="help", style="slow", facts={"name": "Rosa", "age": "81"})
    moved = "I want to move my visit of Tuesday to the afternoon."
    phoned = as_scenario(caller, moved, {"visit": "Tuesday 9:00", "age": "82"})
    assert phoned.goal == moved
    assert phoned.facts == {"name": "Rosa", "age": "82", "visit": "Tuesday 9:00"}
    assert phoned.style == "slow"
    assert caller.goal == "help"


class Holding:
    """A describer that holds one agent."""

    def __init__(self, slug: str, prompt: str) -> None:
        self.slug, self.prompt = slug, prompt

    async def brief_of(self, session: AsyncSession, scope: Scope, slug: str) -> Brief | None:
        """What it says of the agent it holds; nothing of any other."""
        return Brief(prompt=self.prompt) if slug == self.slug else None


async def test_the_first_describer_that_holds_the_agent_answers() -> None:
    describers = Describers()
    describers.add(Holding("clinic", "the clinic's"))
    describers.add(Holding("clinic", "a later one's"))
    describers.add(Holding("shop", "the shop's"))
    session = AsyncSession()
    assert await describers.brief_of(session, SCOPE, "clinic") == Brief(prompt="the clinic's")
    assert await describers.brief_of(session, SCOPE, "shop") == Brief(prompt="the shop's")


async def test_an_agent_no_describer_holds_is_none() -> None:
    describers = Describers()
    describers.add(Holding("clinic", "the clinic's"))
    assert await describers.brief_of(AsyncSession(), SCOPE, "bank") is None
    assert await Describers().brief_of(AsyncSession(), SCOPE, "clinic") is None
