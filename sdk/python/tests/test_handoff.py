"""A team: the tools that offer the call to a teammate, and who answers a line that chooses."""

import asyncio

import pytest

from pinecall import Agent, CallLine, DeclarationRefused, tool
from pinecall._handoff import (
    ANSWERED_WITHIN_S,
    answered_by,
    mate_named,
    taken_by,
    team_tools,
    transfer_name,
    transfers_of,
)

LINE = CallLine(id="CA_1", contact="+14155550142")


class FrontDesk(Agent):
    """You answer the clinic's phone."""

    @tool
    def book(self, day: str) -> str:
        """Books a visit."""
        return day


class BillingDesk(Agent):
    """You answer questions about bills."""

    takes = "questions about a bill"

    @tool
    def find_bill(self, number: str) -> str:
        """Finds a bill."""
        return number


TEAM = {FrontDesk: "front-desk", BillingDesk: "billing"}


def test_a_class_takes_what_it_says_in_words_and_its_tool_is_named_by_the_class() -> None:
    assert (taken_by(BillingDesk), taken_by(FrontDesk)) == ("questions about a bill", None)
    assert transfer_name(BillingDesk) == "transfer_to_billing_desk"


def test_a_call_is_offered_to_each_teammate_that_takes_something_never_to_itself() -> None:
    offered = transfers_of(FrontDesk, TEAM)
    assert [spec.name for spec in offered] == ["transfer_to_billing_desk"]
    assert "questions about a bill" in offered[0].description
    assert transfers_of(BillingDesk, TEAM) == []
    assert mate_named("transfer_to_billing_desk", TEAM) is BillingDesk


def test_a_team_declares_every_tool_once_and_refuses_one_name_on_two_agents() -> None:
    assert [spec.name for spec in team_tools(TEAM)] == [
        "book",
        "transfer_to_billing_desk",
        "find_bill",
    ]

    class Other(Agent):
        """Other."""

        takes = "anything"

        @tool
        def book(self, day: str) -> str:
            """Books too."""
            return day

    with pytest.raises(DeclarationRefused, match="both declare a tool named book"):
        team_tools({FrontDesk: "front-desk", Other: "other"})


async def test_a_line_that_chooses_is_answered_by_its_choice_from_the_team() -> None:
    assert (await answered_by(lambda _: BillingDesk, LINE, FrontDesk, TEAM)).agent is BillingDesk
    assert (await answered_by(lambda _: None, LINE, FrontDesk, TEAM)).why is None


async def test_a_line_that_chooses_may_name_its_choice_by_its_slug() -> None:
    assert (
        await answered_by(lambda _: TEAM[BillingDesk], LINE, FrontDesk, TEAM)
    ).agent is BillingDesk
    bound = await answered_by(lambda _: TEAM[FrontDesk], LINE, FrontDesk, TEAM)
    assert (bound.agent, bound.why) == (FrontDesk, None)
    stranger = await answered_by(lambda _: "after-hours", LINE, FrontDesk, TEAM)
    assert (stranger.agent, stranger.why) == (
        FrontDesk,
        "answers chose after-hours, which is not of the line's team",
    )


async def test_a_choice_that_fails_is_late_or_outside_the_team_is_the_bound_agent_and_why() -> None:
    def fails(_: CallLine) -> type:
        raise RuntimeError("no CRM")

    async def late(_: CallLine) -> type:
        await asyncio.sleep(ANSWERED_WITHIN_S + 1)
        return BillingDesk

    assert (await answered_by(fails, LINE, FrontDesk, TEAM)).why == "answers raised: no CRM"
    assert "took more than" in str((await answered_by(late, LINE, FrontDesk, TEAM)).why)
    stranger = await answered_by(lambda _: Agent, LINE, FrontDesk, TEAM)
    assert (stranger.agent, "not of the line's team" in str(stranger.why)) == (FrontDesk, True)
