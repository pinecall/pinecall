"""Which agent answers a number, as a worker and the domains above read it, and an agent's numbers moved with it."""

from collections.abc import Sequence
from datetime import timedelta

from sqlalchemy.ext.asyncio import AsyncSession

from runtime.actor import Actor, Scope
from runtime.enums import Channel, Env, KeyScope
from runtime.exceptions import ValidationError
from runtime.kit.crypto import Vault
from runtime.kit.time import now
from runtime.livekit import Servers
from runtime.scoping import box_wide
from runtime.telephony.models import Route
from runtime.telephony.repository import RouteRepository
from runtime.telephony.service import rebuild, sfu
from runtime.wire import parts

# A number rung all day is written once a minute, never once a call.
CALLED_EVERY = timedelta(minutes=1)
NOT_ROUTED = (
    "{number} on {channel} is not a route of {slug} in {env}: a number reaches an agent once imported, "
    "`pinecall numbers import {number} --agent {slug}`"
)
NO_NUMBER = "a {channel} route names its number: only web answers with none"


async def list_routes(
    session: AsyncSession, org: str, env: Env, *, agent: str | None = None, channel: Channel | None = None
) -> list[Route]:
    """The org's numbers in one env, oldest first; one agent's, or one channel's, when named."""
    found = await RouteRepository(session).list_of_org(org, env, agent=agent, channel=channel)
    return [numbered.route for numbered in found]


# A number reaches an agent through the org's routes (`pinecall numbers import`), never through a
# registration: what the app says it answers is checked against them, and agent.registered says what
# the agent really answers, web always among it.
async def list_answered_routes(
    session: AsyncSession, scope: Scope, slug: str, wanted: Sequence[parts.Route]
) -> list[parts.Route]:
    """The routes the agent answers in the scope's env; one the app names and the org never routed is refused."""
    rows = await list_routes(session, scope.org, scope.env, agent=slug)
    labels = {(route.channel, route.number): route.label for route in wanted}
    web = parts.Route(channel=Channel.web, number=None, label=labels.get((Channel.web, None)))
    held = [web] + [
        parts.Route(channel=row.channel, number=row.number, label=labels.get((row.channel, row.number))) for row in rows
    ]
    for route in wanted:
        if route.channel is Channel.web:
            continue
        if route.number is None:
            raise ValidationError(NO_NUMBER.format(channel=route.channel.value))
        if not any(had.channel is route.channel and had.number == route.number for had in held):
            raise ValidationError(
                NOT_ROUTED.format(number=route.number, channel=route.channel.value, slug=slug, env=scope.env.value)
            )
    return held


async def find_route_at(session: AsyncSession, channel: Channel, number: str) -> Route | None:
    """The route a call dialled to this number takes, whatever org holds it."""
    with box_wide():
        return await RouteRepository(session).find_at(channel, number)


async def count_managed(session: AsyncSession, org: str, env: Env) -> int:
    """How many of the org's numbers in the env the box bought: the numbers quota counts these."""
    return await RouteRepository(session).count_managed(org, env)


async def note_call(session: AsyncSession, org: str, number: str) -> None:
    """Note that a call to the org's number reached the box now."""
    at = now()
    await RouteRepository(session).note_call(org, number, at=at, unless_since=at - CALLED_EVERY)


# A route the operator adds answers the next job: nothing is cached. A fleet's key acts in the scope
# its dispatch named (the middleware resolved it), and with a number and no scope it asks which org's
# the number is: the one row, in its own env alone.
async def list_for_worker(
    session: AsyncSession, actor: Actor, *, number: str | None, channel: Channel
) -> Sequence[Route]:
    """The routes of a worker's scope; for a fleet's key and a number, the route that number rings."""
    if actor.opens(KeyScope.fleet) and number is not None:
        found = await find_route_at(session, channel, number)
        return [] if found is None or found.env is not actor.env else [found]
    return await list_routes(session, actor.org, actor.env)


# Until 2026-11 the rows moved and the SFU stayed as it was: the old org's trunk went on listing each
# number and its rule dispatching it there, and nobody else could import a number so "held".
# A number the target org already holds stays where it was: one row per number per org.
async def move_routes_with_agent(
    session: AsyncSession, vault: Vault, servers: Servers, agent: str, org: str
) -> tuple[list[str], list[str]]:
    """Move the agent's numbers into the org, on the SFU too; the numbers moved, and the ones that stayed."""
    repository = RouteRepository(session)
    with box_wide():
        before = [
            (route.org, route.number, route.env, route.channel)
            for route in await repository.list_of_agent_outside(agent, org)
        ]
        moved = await repository.move_with_agent(agent, org)
        for was, number, env, channel in before:
            if number in moved and channel is Channel.phone:
                await sfu.let_go(servers[env], was, number)
        if moved:
            await rebuild.readmit(session, vault, servers, org)
    return moved, sorted(number for _, number, _, _ in before if number not in moved)
