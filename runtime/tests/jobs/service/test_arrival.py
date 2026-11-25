"""The route a call takes by its agent, its number or the default; what a job asks again; the room it gives back."""

import asyncio
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from typing import cast

import httpx
import pytest
from livekit.agents import JobContext
from livekit.protocol import agent as livekit_agent
from livekit.protocol import models

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
    or_give_the_room_back,
    resolve_route,
    ring_the_tester,
)
from runtime.jobs.service.client import ARRIVES_WITHIN_S, GatewayClient
from runtime.kit.retry import Within
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


# A simulated caller's leg dials the call's own room: the gateway says the number it rang, the agent's
# own or the box's test line, and the call is the agent's at that number whatever routes it has.
def test_a_simulated_callers_ring_is_the_agents_at_the_number_the_gateway_says_it_rang() -> None:
    """An agent with no number of its own answers a simulated ring at the number its dispatch names."""
    dispatch = Dispatch(agent="front", org="org_a", env=Env.sandbox, dialled=NUMBER, persona="in-a-hurry")
    assert resolve_route(dispatch, A_PHONE, [], None) == IN_THE_SANDBOX


def test_a_simulated_ring_whose_leg_never_came_is_a_call_in_the_room() -> None:
    """With no phone leg the arrival is a page's, and the agent answers it as it answers the widget."""
    dispatch = Dispatch(agent="front", org="org_a", env=Env.sandbox, dialled=NUMBER)
    assert resolve_route(dispatch, A_PAGE, [], None) == Route(
        org="org_a", agent="front", channel=Channel.web, env=Env.sandbox
    )


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


def on_one_try() -> Within:
    """A job's wait that is over already: each question is asked once."""
    return Within(0.0)


async def at_once(_seconds: float) -> None:
    """The wait between two tries, not waited."""


def answering(handed: RingAtTestLine) -> GatewayClient:
    """The worker's own client, on a gateway that says whose sandbox agent a ring at the test line is for."""

    def answer(asked: httpx.Request) -> httpx.Response:
        assert asked.url.path == "/v1/test-line/rings-for"
        assert dict(asked.url.params) == {"number": NUMBER, "caller": CALLER}
        return httpx.Response(200, json=handed.dump())

    return GatewayClient(httpx.AsyncClient(base_url="http://gateway.test", transport=httpx.MockTransport(answer)))


async def test_the_route_a_known_caller_takes_is_their_orgs_agent_at_the_number_dialled() -> None:
    gateway = answering(RingAtTestLine(org="org_b", agent="front", holder="m_x"))
    taken, moved = await ring_the_tester(gateway, A_TESTERS_RING, A_PHONE, IN_THE_SANDBOX, on_one_try())
    await gateway.aclose()
    assert taken == Route(org="org_b", agent="front", channel=Channel.phone, number=NUMBER, env=Env.sandbox)
    assert (moved.org, moved.agent, moved.holder, moved.caller) == ("org_b", "front", "m_x", CALLER)


async def test_a_phone_nobody_said_was_theirs_stays_with_the_numbers_agent_told_why() -> None:
    gateway = answering(RingAtTestLine())
    taken, moved = await ring_the_tester(gateway, A_TESTERS_RING, A_PHONE, IN_THE_SANDBOX, on_one_try())
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
    taken, moved = await ring_the_tester(gateway, A_TESTERS_RING, A_PHONE, IN_THE_SANDBOX, on_one_try())
    await gateway.aclose()
    assert taken == IN_THE_SANDBOX
    assert (moved.org, moved.agent, moved.holder) == (A_TESTERS_RING.org, A_TESTERS_RING.agent, A_TESTERS_RING.holder)
    assert moved.metadata == {"test_line": why, "test_line_agent": agent}


async def test_a_ring_at_the_test_line_while_the_gateway_is_away_stays_with_the_numbers_own_agent() -> None:
    def away(_asked: httpx.Request) -> httpx.Response:
        return httpx.Response(503, text="away")

    gateway = GatewayClient(httpx.AsyncClient(base_url="http://gateway.test", transport=httpx.MockTransport(away)))
    taken, moved = await ring_the_tester(gateway, A_TESTERS_RING, A_PHONE, IN_THE_SANDBOX, on_one_try())
    await gateway.aclose()
    assert taken == IN_THE_SANDBOX
    assert moved.metadata["test_line"] == TEST_LINE_UNAVAILABLE


# 2026-11-25, thirty simulated calls on one gateway: its pool had no connection free for two seconds,
# it answered a job's read `503`, the job ended on that answer and its caller waited 110 s for nobody.
# A gateway busy or away is asked again, for as long as the job's one wait lasts.
async def test_a_question_a_busy_gateway_refused_is_asked_again_on_the_jobs_wait() -> None:
    asked: list[str] = []

    def busy_at_first(request: httpx.Request) -> httpx.Response:
        asked.append(request.url.path)
        if len(asked) == 1:
            return httpx.Response(503, json={"detail": "the database is busy: no connection came free within 2 s"})
        return httpx.Response(200, json=RingAtTestLine(org="org_b", agent="front", holder="m_x").dump())

    http = httpx.AsyncClient(base_url="http://gateway.test", transport=httpx.MockTransport(busy_at_first))
    gateway, asking = GatewayClient(http), Within(ARRIVES_WITHIN_S, sleep=at_once)
    taken, _ = await ring_the_tester(gateway, A_TESTERS_RING, A_PHONE, IN_THE_SANDBOX, asking)
    await gateway.aclose()
    assert taken.org == "org_b", "the second answer is the one the call goes on with"
    assert asked == ["/v1/test-line/rings-for"] * 2


THE_WORKER = "pinecall-sandbox/w1.1"
GIVEN_BACK = ("DELETE", "/v1/fleet/rooms/call_1/taken?worker=pinecall-sandbox%2Fw1.1")


@dataclass
class Hearing:
    """A gateway that keeps what a job said of its room, and answers as told."""

    status: int = 204
    heard: list[tuple[str, str]] = field(default_factory=list[tuple[str, str]])

    def answer(self, request: httpx.Request) -> httpx.Response:
        """The word is kept, or the gateway is away."""
        self.heard.append((request.method, str(request.url.raw_path, "ascii")))
        return httpx.Response(self.status)

    @property
    def client(self) -> GatewayClient:
        """The job's way to this gateway."""
        return GatewayClient(httpx.AsyncClient(transport=httpx.MockTransport(self.answer), base_url="http://gw"))


@dataclass
class AJob:
    """A job as livekit hands it: its room, and the worker's name its dispatch carried."""

    job: livekit_agent.Job


def a_job(worker: str = THE_WORKER) -> JobContext:
    """The job of room call_1, offered to this worker by name."""
    job = livekit_agent.Job(id="AJ_call_1", room=models.Room(name="call_1", sid="RM_call_1"), agent_name=worker)
    return cast("JobContext", AJob(job))


def breaking(failure: Exception) -> Callable[[], Awaitable[None]]:
    """What leads to a call's opening, broken on the way."""

    async def opening() -> None:
        raise failure

    return opening


# 2026-11-25: a room is its worker's from the moment the job is accepted, so a job that ended before
# it opened its call left a room held for nobody, which nothing rang again.
async def test_a_job_that_breaks_before_its_call_is_open_gives_its_room_back() -> None:
    gateway = Hearing()
    with pytest.raises(RuntimeError, match="the gateway stayed busy"):
        await or_give_the_room_back(a_job(), gateway.client, breaking(RuntimeError("the gateway stayed busy")))
    assert gateway.heard == [GIVEN_BACK]


async def test_a_job_told_to_stop_before_its_call_is_open_gives_its_room_back() -> None:
    gateway = Hearing()
    arriving = asyncio.create_task(or_give_the_room_back(a_job(), gateway.client, asyncio.Event().wait))
    await asyncio.sleep(0.05)
    arriving.cancel()
    with pytest.raises(asyncio.CancelledError):
        await arriving
    assert gateway.heard == [GIVEN_BACK]


async def test_a_job_that_opened_its_call_or_left_it_to_another_job_gives_nothing_back() -> None:
    gateway = Hearing()

    async def opened() -> str:
        return "call_1"

    async def another_jobs() -> None:
        return None

    assert await or_give_the_room_back(a_job(), gateway.client, opened) == "call_1"
    assert await or_give_the_room_back(a_job(), gateway.client, another_jobs) is None
    assert gateway.heard == []


async def test_a_job_no_worker_was_named_for_has_no_offer_to_give_back() -> None:
    gateway = Hearing()
    with pytest.raises(RuntimeError):
        await or_give_the_room_back(a_job(worker=""), gateway.client, breaking(RuntimeError("broke")))
    assert gateway.heard == []


async def test_a_gateway_that_does_not_hear_the_room_given_back_leaves_the_job_its_own_failure(
    caplog: pytest.LogCaptureFixture,
) -> None:
    gateway = Hearing(status=503)
    with pytest.raises(RuntimeError, match="broke"):
        await or_give_the_room_back(a_job(), gateway.client, breaking(RuntimeError("broke")))
    assert gateway.heard == [GIVEN_BACK]
    assert "room call_1: the gateway was not told this job left it unopened" in caplog.text
