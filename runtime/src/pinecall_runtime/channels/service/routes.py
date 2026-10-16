"""Which agent answers a number or a channel, per org and env: the routes table, resolved."""

from collections.abc import Sequence
from dataclasses import dataclass

from sqlalchemy.ext.asyncio import AsyncSession

from pinecall_runtime.calls import context
from pinecall_runtime.channels.models import Route
from pinecall_runtime.channels.repository import RouteRepository
from pinecall_runtime.enums import Channel, Direction, Env, RouteOrigin
from pinecall_runtime.exceptions import NotFound
from pinecall_runtime.wire.dispatch import Dispatch


@dataclass(frozen=True, slots=True)
class RouteWrite:
    """What a row keeps beside its route: who wrote it, the account, the networks, the carrier."""

    origin: RouteOrigin
    account: str | None = None
    # A number hooked from networks of the org's own, which the operator approves.
    networks: tuple[str, ...] = ()
    # The catalog carrier a number with no account comes through.
    via: str | None = None
    # Written unapproved: no call to it opens until the operator approves it.
    waits: bool = False


@dataclass(frozen=True, slots=True)
class Arrival:
    """What a job says of its call before it runs: who calls, through what, dialling what."""

    caller: str
    channel: Channel
    direction: Direction
    # The number dialled, read off the caller's SIP leg: phone jobs are room jobs, and livekit
    # leaves job.participant empty for them.
    number: str | None = None
    # The Twilio account the leg came from, when Twilio sent it.
    carrier_account: str | None = None


async def routes_of_org(session: AsyncSession, org: str, env: Env) -> Sequence[Route]:
    """The org's numbers in one env, oldest first."""
    return await RouteRepository(session).of_org(org, env)


async def route_at(session: AsyncSession, channel: Channel, number: str) -> Route | None:
    """The route a call dialled to this number takes, whatever org holds it."""
    return await RouteRepository(session).at(channel, number)


async def get_route(session: AsyncSession, org: str, number: str) -> Route | None:
    """The org's route at this number, whatever env it is in."""
    return await RouteRepository(session).get(org, number)


async def phones_of_org(session: AsyncSession, org: str) -> Sequence[Route]:
    """The org's phone numbers in both envs, oldest first."""
    return await RouteRepository(session).phones_of(org)


async def orgs_with_phones(session: AsyncSession) -> list[str]:
    """Every org that answers at a phone number."""
    return await RouteRepository(session).orgs_with_phones()


async def put_route(session: AsyncSession, route: Route, written: RouteWrite) -> Route:
    """Keep the route, moving the number if the org had it, with how it was written."""
    return await RouteRepository(session).put(
        route.org,
        route.number,
        agent=route.agent,
        channel=route.channel,
        env=route.env,
        managed=route.managed,
        account=written.account,
        networks=written.networks,
        origin=written.origin,
        via=written.via,
        waits=written.waits,
    )


async def note_called(session: AsyncSession, org: str, number: str) -> None:
    """Note that a call to the org's number reached the box now."""
    await RouteRepository(session).called(org, number)


async def approve_route(session: AsyncSession, org: str, number: str, by: str) -> bool:
    """The operator's word that the org's hooked number is the org's; whether one waited."""
    return await RouteRepository(session).approve(org, number, by)


async def held_elsewhere(session: AsyncSession, org: str, number: str) -> bool:
    """Whether another org holds the number on this box."""
    return await RouteRepository(session).held_elsewhere(org, number)


async def remove_route(session: AsyncSession, org: str, number: str) -> bool:
    """Forget the org's route at the number; whether there was one."""
    return await RouteRepository(session).remove(org, number)


async def move_route(session: AsyncSession, org: str, number: str, env: Env) -> bool:
    """Move the org's number into the env; whether it had it."""
    return await RouteRepository(session).move(org, number, env)


async def move_routes_with_agent(session: AsyncSession, agent: str, org: str) -> tuple[list[str], list[str]]:
    """Move the agent's numbers into the org; the numbers moved, and the ones that stayed."""
    return await RouteRepository(session).move_with_agent(agent, org)


async def managed_in(session: AsyncSession, org: str, env: Env) -> int:
    """How many of the org's numbers in the env the box bought."""
    return await RouteRepository(session).managed_in(org, env)


# The dispatch's agent first, then the number dialled, then the worker's own default.
def resolve_route(
    dispatch: Dispatch, arrival: Arrival, routes: Sequence[context.Route], default: str | None
) -> context.Route:
    """The route the call takes."""
    if dispatch.diverted_from is not None and dispatch.agent is None:
        raise NotFound("a ring handed over from production names no agent: its leg carried no X-Pinecall-*")
    agent = dispatch.agent or (None if arrival.number else default)
    if agent is not None:
        return _of_agent(agent, dispatch, arrival, routes)
    if arrival.number is None:
        raise NotFound("the job names no agent, no number was dialled, and this worker has no default agent")
    found = next(
        (route for route in routes if route.channel == arrival.channel and route.number == arrival.number), None
    )
    if found is None:
        raise NotFound(f"nobody answers {arrival.number} on {arrival.channel}")
    return found


# A widget's route is not stored: every agent answers on the widget, and the token endpoint
# already checked the agent is the key's. A handed-over ring dialled production's number.
def _of_agent(agent: str, dispatch: Dispatch, arrival: Arrival, routes: Sequence[context.Route]) -> context.Route:
    if dispatch.diverted_from is not None and arrival.number and dispatch.org and dispatch.env:
        return context.Route(
            org=dispatch.org, agent=agent, channel=arrival.channel, number=arrival.number, env=dispatch.env
        )
    found = next((route for route in routes if route.agent == agent and route.channel == arrival.channel), None)
    if found is not None:
        return found
    if arrival.channel is Channel.web and dispatch.org and dispatch.env:
        return context.Route(org=dispatch.org, agent=agent, channel=Channel.web, number=None, env=dispatch.env)
    looked = sorted({f"{route.org}/{route.env}" for route in routes}) or ["no org at all"]
    raise NotFound(f"agent {agent} answers on no {arrival.channel} route: it looked in {', '.join(looked)}")
