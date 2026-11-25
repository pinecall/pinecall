"""Whose call a job is: its dispatch, arrival and route, a ring handed on; what it asks again; its room given back."""

import asyncio
import logging
from collections.abc import Awaitable, Callable, Mapping, Sequence
from dataclasses import dataclass
from typing import Any

from livekit.agents import JobContext
from livekit.agents.utils import aio

from runtime.actor import Scope
from runtime.agents.declaration import Declaration
from runtime.calls.context import CallContext, Contact, Route, dump_context
from runtime.enums import Channel, Direction, Env
from runtime.exceptions import NotFound, UpstreamError
from runtime.jobs.service.client import GatewayClient, Stages
from runtime.jobs.service.handed import tell_it_is_handed
from runtime.kit.retry import Within
from runtime.kit.time import today_in
from runtime.telephony import service as telephony
from runtime.wire.dispatch import Dispatch
from runtime.wire.worker import HoldAudio, OpenCallRequest

logger = logging.getLogger(__name__)

# Why a ring at the box's test line stayed with the number's own agent, said in the call's metadata.
PHONE_NOT_SAID = "phone_not_said"
NO_AGENT_NAMED = "no_agent_named"
AGENT_NOT_RUNNING = "agent_not_running"
TEST_LINE_UNAVAILABLE = "unavailable"

TEST_VALUES_ON_THE_WIRE = "tuning"


@dataclass(frozen=True, slots=True)
class Arrived:
    """A job's call once it is known whose it is: its dispatch, how it arrived, its route, and the call it opens."""

    dispatch: Dispatch
    arrival: telephony.Arrival
    route: Route
    context: CallContext

    @property
    def scope(self) -> Scope:
        """The org, the env and the holder the call runs for."""
        return Scope(self.route.org, self.route.env, self.dispatch.holder or "")

    # The values a test room asked for ride the wire under the word the release before 2026-11 wrote.
    # `seat` is the identity the job's agent joined the room under: the gateway tells this job's open
    # from the open of another job of the same room by it.
    def open_with(self, app: str | None, seat: str) -> OpenCallRequest:
        """What the call's log is opened with at the gateway, and said again to one that forgot it."""
        return OpenCallRequest.model_validate(
            {
                "agent": self.route.agent,
                "context": dump_context(self.context),
                "app": self.dispatch.app or app,
                "carrier_account": self.arrival.carrier_account,
                TEST_VALUES_ON_THE_WIRE: self.dispatch.test_values or None,
                "seat": seat,
            }
        )


# The one reading of whose call a job is, for the job that runs it and for the overflow that only
# tells its caller: until 2026-11 each had its own copy of these steps. The room is the call: its
# name is the id the gateway minted, or the SIP rule's. What it asks the gateway is asked on the
# job's one wait (`asking`, `client.arriving`): a gateway away or busy is asked again, not left.
async def arrive_as_rung(
    ctx: JobContext, gateway: GatewayClient, *, default_agent: str | None, zone: str, asking: Within
) -> Arrived:
    """Join the room and find whose call the job is, by its dispatch and the number it rang."""
    dispatch = Dispatch.parse(ctx.job.metadata)
    arrival, found = await _join(ctx, gateway, dispatch, asking)
    route = resolve_route(dispatch, arrival, found, default_agent)
    return Arrived(dispatch, arrival, route, context_of(ctx.room.name or ctx.job.id, dispatch, arrival, route, zone))


# A call that will be run may be somebody's own ring: a developer's at a production number, sent on
# to their sandbox, or a tester's at the box's test line, answered here as their org's agent.
async def arrive(
    ctx: JobContext, gateway: GatewayClient, *, default_agent: str | None, zone: str, asking: Within
) -> Arrived | None:
    """Join the room and find whose call the job is; None once the ring was handed to a developer's sandbox."""
    rung = await arrive_as_rung(ctx, gateway, default_agent=default_agent, zone=zone, asking=asking)
    dispatch, arrival, route = rung.dispatch, rung.arrival, rung.route
    if may_be_a_developers(dispatch, arrival, route) and await _hand_over(ctx, gateway, rung, asking):
        return None
    if not may_be_a_testers(dispatch, arrival, route):
        return rung
    route, dispatch = await ring_the_tester(gateway, dispatch, arrival, route, asking)
    return Arrived(dispatch, arrival, route, context_of(rung.context.call, dispatch, arrival, route, zone))


# A room is its worker's from the moment its job was accepted (`heartbeat.Accepted`), so that a process
# slow to start is not read as a job given to nobody. A job that then leaves before its call is open
# leaves a room nobody has and the gateway holds for it: nothing rang it again, and its caller waited
# for nobody (2026-11-25: three simulated callers of twenty, each its 110 s, their jobs gone on a busy
# gateway's `503`). Whatever takes the job out before the open (a gateway away past the wait, a
# refusal, a fault of ours, its process told to stop) the room is given back as it goes, and the
# sweep offers it again in its turn. A job that returns, its ring handed on or its call another job's,
# gives nothing back: that room has somebody. A process killed outright says nothing: its room stays
# held until the fleet forgets it.
async def or_give_the_room_back[T](ctx: JobContext, gateway: GatewayClient, opening: Callable[[], Awaitable[T]]) -> T:
    """What leads to the call's opening, done; a job that breaks on the way gives its room back to the gateway."""
    try:
        return await opening()
    except BaseException:
        room, worker = ctx.job.room.name, ctx.job.agent_name
        # A job no dispatch named a worker for was offered by nobody: there is no offer to give back.
        if worker:
            try:
                await gateway.drop_room(room, worker)
            except UpstreamError as refused:
                logger.warning("room %s: the gateway was not told this job left it unopened: %s", room, refused)
        raise


# The three answers a call is set up from, asked together on the job's one wait: a call's first job
# and the job that takes it up from a worker that went away ask the same.
async def read_agent(
    gateway: GatewayClient, arrived: Arrived, asking: Within, *, test: Mapping[str, Any] | None = None
) -> tuple[Declaration, Stages, HoldAudio]:
    """The agent as the call runs it, the stages it runs on with their keys, and what it plays a held caller."""
    agent, scope, call = arrived.route.agent, arrived.scope, arrived.context.call
    return await asyncio.gather(
        asking.ask(lambda: gateway.get_agent(agent, scope, call=call, test=test), f"the agent of {call}"),
        asking.ask(lambda: gateway.get_stages(agent, scope, call=call, test=test), f"the stages of {call}"),
        asking.ask(lambda: gateway.get_hold(agent, scope), f"what {call} plays on hold"),
    )


def context_of(call: str, dispatch: Dispatch, arrival: telephony.Arrival, route: Route, zone: str) -> CallContext:
    """The call as the gateway opens it, from the job's dispatch, its arrival and its route."""
    return CallContext(
        call=call,
        channel=route.channel,
        direction=arrival.direction,
        caller=arrival.caller,
        route=route,
        today=today_in(zone),
        contact=None if dispatch.contact is None else Contact(id=dispatch.contact),
        metadata=dispatch.metadata,
        run=dispatch.run,
        persona=dispatch.persona,
        expects=tuple(dispatch.expects),
        holder=dispatch.holder,
        state=dispatch.state,
        continues=dispatch.continues,
    )


# The dispatch's agent first, then the number dialled, then the worker's own default.
def resolve_route(
    dispatch: Dispatch, arrival: telephony.Arrival, routes: Sequence[Route], default: str | None
) -> Route:
    """The route the call takes."""
    if dispatch.diverted_from is not None and dispatch.agent is None:
        raise NotFound("a ring handed over from production names no agent: its leg carried no X-Pinecall-*")
    agent = dispatch.agent or (None if arrival.number else default)
    if agent is not None:
        return _route_of_agent(agent, dispatch, arrival, routes)
    if arrival.number is None:
        raise NotFound("the job names no agent, no number was dialled, and this worker has no default agent")
    found = next(
        (route for route in routes if route.channel == arrival.channel and route.number == arrival.number), None
    )
    if found is None:
        raise NotFound(f"nobody answers {arrival.number} on {arrival.channel}")
    return found


# Only an undispatched ring at a production number can be a developer's own phone.
def may_be_a_developers(dispatch: Dispatch, arrival: telephony.Arrival, route: Route) -> bool:
    """Whether to ask if this ring belongs in a developer's sandbox."""
    return _is_an_undispatched_ring(dispatch, arrival, route) and route.env is Env.production


# A ring at a sandbox number the job was not told the agent of: the test line is one, and whose
# agent it reaches is the caller's phone's to say.
def may_be_a_testers(dispatch: Dispatch, arrival: telephony.Arrival, route: Route) -> bool:
    """Whether to ask whose sandbox agent this ring is for."""
    return _is_an_undispatched_ring(dispatch, arrival, route) and route.env is Env.sandbox


# A ring at the box's test line is the caller's own: the gateway says whose sandbox agent, and the
# call goes on here as that org's, in the copy that takes a ring from that phone. A phone nobody
# said was theirs, one whose person named no agent among several, or one whose agent nobody holds,
# is answered by the agent the number is routed to, told which of them it is in the call's metadata
# (`{{metadata.test_line}}` in a Studio agent): a caller hears what to fix, not every reason at once.
async def ring_the_tester(
    gateway: GatewayClient, dispatch: Dispatch, arrival: telephony.Arrival, route: Route, asking: Within
) -> tuple[Route, Dispatch]:
    """The route and the dispatch a ring at the test line goes on with: its caller's own agent, or the number's."""
    try:
        whose = f"whose phone rings {route.number}"
        handed = await asking.ask(lambda: gateway.ring_at_test_line(str(route.number), arrival.caller), whose)
    except UpstreamError:
        logger.warning("could not ask whose phone rings %s: the call stays with %s", route.number, route.agent)
        return route, _tell(dispatch, TEST_LINE_UNAVAILABLE, None)
    if handed.org is None:
        return route, _tell(dispatch, PHONE_NOT_SAID, None)
    if handed.agent is None:
        return route, _tell(dispatch, NO_AGENT_NAMED, None)
    if handed.holder is None:
        return route, _tell(dispatch, AGENT_NOT_RUNNING, handed.agent)
    moved = dispatch.model_copy(
        update={
            "agent": handed.agent,
            "org": handed.org,
            "env": Env.sandbox,
            "holder": handed.holder,
            "caller": arrival.caller,
        }
    )
    # The route a test-line ring takes once its caller is known: their org's agent, at the number dialled.
    taken = Route(org=handed.org, agent=handed.agent, channel=route.channel, number=arrival.number, env=Env.sandbox)
    return taken, moved


# ── private ──


# A dispatch that names its scope has its routes asked for while the room connects. One that names
# none is the box's own trunk, where the number dialled decides: it is read off the caller's leg
# first, and the routes asked once. Until 2026-11 they were asked twice, the first answer unread.
async def _join(
    ctx: JobContext, gateway: GatewayClient, dispatch: Dispatch, asking: Within
) -> tuple[telephony.Arrival, list[Route]]:
    named = dispatch.named_scope
    what = f"the routes of room {ctx.job.room.name}"
    if named is None:
        await ctx.connect()
        arrival = await telephony.arrival_of(dispatch, ctx.room)
        rung = arrival.number, arrival.channel
        return arrival, await asking.ask(lambda: gateway.list_routes(None, number=rung[0], channel=rung[1]), what)
    listing = asking.ask(lambda: gateway.list_routes(named, number=None, channel=Channel.phone), what)
    _, found = await asyncio.gather(ctx.connect(), listing)
    return await telephony.arrival_of(dispatch, ctx.room), found


def _is_an_undispatched_ring(dispatch: Dispatch, arrival: telephony.Arrival, route: Route) -> bool:
    return (
        arrival.number is not None
        and dispatch.agent is None
        and arrival.direction is Direction.inbound
        and route.channel is Channel.phone
    )


# A widget's route is not stored: every agent answers on the widget, and the token endpoint
# already checked the agent is the key's. A handed-over ring dialled production's number, and a
# simulated caller's the number the gateway says it rang: the agent's own, or the box's test line.
def _route_of_agent(agent: str, dispatch: Dispatch, arrival: telephony.Arrival, routes: Sequence[Route]) -> Route:
    rings = dispatch.diverted_from is not None or dispatch.dialled is not None
    if rings and arrival.channel is Channel.phone and arrival.number and dispatch.org and dispatch.env:
        return Route(org=dispatch.org, agent=agent, channel=arrival.channel, number=arrival.number, env=dispatch.env)
    found = next((route for route in routes if route.agent == agent and route.channel == arrival.channel), None)
    if found is not None:
        return found
    if arrival.channel is Channel.web and dispatch.org and dispatch.env:
        return Route(org=dispatch.org, agent=agent, channel=Channel.web, number=None, env=dispatch.env)
    looked = sorted({f"{route.org}/{route.env}" for route in routes}) or ["no org at all"]
    raise NotFound(f"agent {agent} answers on no {arrival.channel} route: it looked in {', '.join(looked)}")


# The caller and their carrier stay where they are: production's LiveKit holds their leg.
async def _hand_over(ctx: JobContext, gateway: GatewayClient, rung: Arrived, asking: Within) -> bool:
    dispatch, arrival, route = rung.dispatch, rung.arrival, rung.route
    try:
        whose = f"whose phone rings {route.agent}"
        handed = await asking.ask(lambda: gateway.ring_for(route.agent, route.org, arrival.caller), whose)
    except UpstreamError:
        logger.warning("could not ask whose phone rings %s: the call stays here", route.agent)
        return False
    if handed.holder is None or handed.fleet is None:
        return False
    moved = dispatch.model_copy(
        update={
            "agent": route.agent,
            "org": route.org,
            "env": Env.sandbox,
            "holder": handed.holder,
            "caller": arrival.caller,
            "diverted_from": Env.production,
        }
    )
    # Said while the leg is dialled, which is when the caller is answered and would hear nothing.
    telling = asyncio.create_task(tell_it_is_handed(ctx, gateway, route.agent, Scope(route.org, route.env)))
    if not await telephony.hand_on(ctx.api, ctx.room.name, handed=handed, moved=moved, number=str(route.number)):
        await aio.cancel_and_wait(telling)
        return False
    # The sentence is said whole before this worker leaves the room: its track goes with it.
    await telling
    ctx.shutdown(reason=f"handed to {handed.fleet}")
    return True


def _tell(dispatch: Dispatch, why: str, agent: str | None) -> Dispatch:
    said = {"test_line": why, "test_line_agent": agent or ""}
    return dispatch.model_copy(update={"metadata": {**dispatch.metadata, **said}})
