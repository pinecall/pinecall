"""The route a call takes: the agent the job names, else the number dialled, else the worker's default."""

import httpx
import pytest

from runtime.calls.context import Route
from runtime.enums import Channel, Direction, Env
from runtime.exceptions import NotFound
from runtime.jobs.service.arrival import (
    AGENT_NOT_RUNNING,
    NO_AGENT_NAMED,
    PHONE_NOT_SAID,
    TEST_LINE_UNAVAILABLE,
    may_be_a_developers,
    may_be_a_testers,
    resolve_route,
    ring_the_tester,
)
from runtime.jobs.service.client import GatewayClient
from runtime.telephony.service.legs import Arrival
from runtime.wire.dispatch import Dispatch
from runtime.wire.worker import RingAtTestLine

NUMBER = "+15550100"
CALLER = "+15550199"
A_PHONE = Arrival(caller=CALLER, channel=Channel.phone, direction=Direction.inbound, number=NUMBER)
A_PAGE = Arrival(caller="room_1", channel=Channel.web, direction=Direction.inbound)
AT_THE_NUMBER = Route(org="org_a", agent="front", channel=Channel.phone, number=NUMBER)
IN_THE_SANDBOX = Route(org="org_a", agent="front", channel=Channel.phone, number=NUMBER, env=Env.sandbox)


def test_a_number_dialled_finds_the_route_that_answers_it() -> None:
    """The job names no agent: the number dialled decides."""
    assert resolve_route(Dispatch(), A_PHONE, [AT_THE_NUMBER], "fallback") == AT_THE_NUMBER


def test_a_number_nobody_answers_is_refused_rather_than_sent_to_the_default() -> None:
    """A number with no route is refused, never answered by the worker's default agent."""
    with pytest.raises(NotFound, match="nobody answers"):
        resolve_route(Dispatch(), A_PHONE, [], "fallback")


def test_with_no_agent_and_no_number_only_the_workers_default_is_left() -> None:
    """A page names no number: with no default agent the call has nowhere to go."""
    with pytest.raises(NotFound, match="no default agent"):
        resolve_route(Dispatch(), A_PAGE, [], None)


def test_the_dispatchs_agent_wins_over_the_number() -> None:
    """An agent the job names is the one that answers, on its own route."""
    other = Route(org="org_a", agent="sales", channel=Channel.phone, number="+15550111")
    assert resolve_route(Dispatch(agent="sales"), A_PHONE, [AT_THE_NUMBER, other], None) == other


def test_every_agent_answers_on_the_widget_without_a_stored_route() -> None:
    """The widget is every agent's door: no row is stored for it."""
    found = resolve_route(Dispatch(agent="front", org="org_a", env=Env.sandbox), A_PAGE, [], None)
    assert found == Route(org="org_a", agent="front", channel=Channel.web, env=Env.sandbox)


def test_an_agent_with_no_door_on_the_channel_names_where_it_looked() -> None:
    """Refused, the call says which org and env it looked in."""
    with pytest.raises(NotFound, match="org_a/production"):
        resolve_route(Dispatch(agent="sales"), A_PHONE, [AT_THE_NUMBER], None)


def test_a_ring_handed_to_the_sandbox_keeps_the_production_number_it_dialled() -> None:
    """A production ring handed to a developer's sandbox still names the number the caller dialled."""
    dispatch = Dispatch(agent="front", org="org_a", env=Env.sandbox, diverted_from=Env.production)
    assert resolve_route(dispatch, A_PHONE, [], None) == IN_THE_SANDBOX


def test_a_ring_handed_over_whose_leg_named_nobody_is_refused_rather_than_run_here() -> None:
    """A handed-over ring that lost its agent on the way is refused, never answered by the number."""
    with pytest.raises(NotFound, match="names no agent"):
        resolve_route(Dispatch(env=Env.sandbox, diverted_from=Env.production), A_PHONE, [AT_THE_NUMBER], None)


def test_only_an_undispatched_ring_at_a_production_number_may_be_a_developers() -> None:
    assert may_be_a_developers(Dispatch(), A_PHONE, AT_THE_NUMBER)
    assert not may_be_a_developers(Dispatch(), A_PHONE, IN_THE_SANDBOX)
    assert not may_be_a_developers(Dispatch(agent="front"), A_PHONE, AT_THE_NUMBER)
    assert not may_be_a_developers(Dispatch(), A_PAGE, AT_THE_NUMBER)


def test_only_an_undispatched_ring_at_a_sandbox_number_may_be_a_testers() -> None:
    assert may_be_a_testers(Dispatch(org="org_box", env=Env.sandbox), A_PHONE, IN_THE_SANDBOX)
    assert not may_be_a_testers(Dispatch(), A_PHONE, AT_THE_NUMBER), "production's rings are the hand-over's"
    assert not may_be_a_testers(Dispatch(agent="front"), A_PHONE, IN_THE_SANDBOX), "a job told its agent"
    assert not may_be_a_testers(Dispatch(), A_PAGE, IN_THE_SANDBOX), "a page dialled no number"


A_TESTERS_RING = Dispatch(org="org_a", env=Env.sandbox)


def answering(handed: RingAtTestLine) -> GatewayClient:
    """The worker's own client, on a gateway that says whose sandbox agent a ring at the test line is for."""

    def answer(asked: httpx.Request) -> httpx.Response:
        assert asked.url.path == "/v1/test-line/rings-for"
        assert dict(asked.url.params) == {"number": NUMBER, "caller": CALLER}
        return httpx.Response(200, json=handed.dump())

    return GatewayClient(httpx.AsyncClient(base_url="http://gateway.test", transport=httpx.MockTransport(answer)))


async def test_the_route_a_known_caller_takes_is_their_orgs_agent_at_the_number_dialled() -> None:
    gateway = answering(RingAtTestLine(org="org_b", agent="front", holder="m_x"))
    taken, moved = await ring_the_tester(gateway, A_TESTERS_RING, A_PHONE, IN_THE_SANDBOX)
    await gateway.aclose()
    assert taken == Route(org="org_b", agent="front", channel=Channel.phone, number=NUMBER, env=Env.sandbox)
    assert (moved.org, moved.agent, moved.holder, moved.caller) == ("org_b", "front", "m_x", CALLER)


async def test_a_phone_nobody_said_was_theirs_stays_with_the_numbers_agent_told_why() -> None:
    gateway = answering(RingAtTestLine())
    taken, moved = await ring_the_tester(gateway, A_TESTERS_RING, A_PHONE, IN_THE_SANDBOX)
    await gateway.aclose()
    assert taken == IN_THE_SANDBOX
    assert moved.metadata["test_line"] == PHONE_NOT_SAID


# 2026-11-06: a person whose phone was not registered heard "or your agent is not running" and
# went looking for the wrong thing; the number's own agent is told which reason it is.
@pytest.mark.parametrize(
    ("handed", "why", "agent"),
    [
        (RingAtTestLine(org="org_b"), NO_AGENT_NAMED, ""),
        (RingAtTestLine(org="org_b", agent="front"), AGENT_NOT_RUNNING, "front"),
    ],
    ids=["no agent named among several", "nobody holds the agent"],
)
async def test_a_ring_the_gateway_hands_to_nobody_stays_with_the_numbers_own_agent_told_why(
    handed: RingAtTestLine, why: str, agent: str
) -> None:
    gateway = answering(handed)
    taken, moved = await ring_the_tester(gateway, A_TESTERS_RING, A_PHONE, IN_THE_SANDBOX)
    await gateway.aclose()
    assert taken == IN_THE_SANDBOX
    assert (moved.org, moved.agent, moved.holder) == (A_TESTERS_RING.org, A_TESTERS_RING.agent, A_TESTERS_RING.holder)
    assert moved.metadata == {"test_line": why, "test_line_agent": agent}


async def test_a_ring_at_the_test_line_while_the_gateway_is_away_stays_with_the_numbers_own_agent() -> None:
    def away(_asked: httpx.Request) -> httpx.Response:
        return httpx.Response(503, text="away")

    gateway = GatewayClient(httpx.AsyncClient(base_url="http://gateway.test", transport=httpx.MockTransport(away)))
    taken, moved = await ring_the_tester(gateway, A_TESTERS_RING, A_PHONE, IN_THE_SANDBOX)
    await gateway.aclose()
    assert taken == IN_THE_SANDBOX
    assert moved.metadata["test_line"] == TEST_LINE_UNAVAILABLE
