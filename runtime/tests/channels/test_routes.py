"""The routes: which agent answers a number, one org per number, and the route a call takes."""

import secrets

import pytest
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from pinecall_runtime.calls.context import Route
from pinecall_runtime.channels.models import Route as RouteRow
from pinecall_runtime.channels.service.routes import (
    Arrival,
    RouteWrite,
    held_elsewhere,
    move_route,
    put_route,
    remove_route,
    resolve_route,
    route_at,
    routes_of_org,
)
from pinecall_runtime.enums import Channel, Direction, Env, RouteOrigin
from pinecall_runtime.exceptions import NotFound
from pinecall_runtime.wire.dispatch import Dispatch
from tests.conftest import Tenant, make_tenant, needs_the_database

NUMBER = "+15550100"
CALLER = "+15550199"
A_PHONE = Arrival(caller=CALLER, channel=Channel.phone, direction=Direction.inbound, number=NUMBER)
A_PAGE = Arrival(caller="room_1", channel=Channel.web, direction=Direction.inbound)
AT_THE_NUMBER = Route(org="org_a", agent="front", channel=Channel.phone, number=NUMBER)
IN_THE_SANDBOX = Route(org="org_a", agent="front", channel=Channel.phone, number=NUMBER, env=Env.sandbox)
TYPED = RouteWrite(origin=RouteOrigin.typed)


def a_number() -> str:
    """A number of this test alone: a number is one org's on the whole box."""
    return f"+1555{secrets.randbelow(10**7):07d}"


def routed(tenant: Tenant, number: str, env: Env = Env.production, agent: str = "agenda") -> RouteRow:
    """The tenant's agent answering the number in the env, as the table keeps it."""
    return RouteRow(org=tenant.org, agent=agent, channel=Channel.phone, number=number, env=env, managed=False)


# ── the route a call takes ──


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


# ── the table ──


@needs_the_database
async def test_an_orgs_routes_are_its_own_in_the_env_asked(
    sessions: async_sessionmaker[AsyncSession], tenant: Tenant
) -> None:
    """An org reads its numbers of one env, never another env's or another org's."""
    other = await make_tenant(sessions)
    mine, sandboxed, theirs = a_number(), a_number(), a_number()
    async with sessions.begin() as session:
        await put_route(session, routed(tenant, mine), TYPED)
        await put_route(session, routed(tenant, sandboxed, Env.sandbox), TYPED)
        await put_route(session, routed(other, theirs), TYPED)
    async with sessions() as session:
        found = await routes_of_org(session, tenant.org, Env.production)
    assert [(route.number, route.env) for route in found] == [(mine, Env.production)]


@needs_the_database
async def test_a_number_one_org_holds_is_read_as_held_elsewhere_by_another(
    sessions: async_sessionmaker[AsyncSession], tenant: Tenant
) -> None:
    """One org holds a number on the box; to any other org it is held elsewhere."""
    other = await make_tenant(sessions)
    number = a_number()
    async with sessions.begin() as session:
        await put_route(session, routed(tenant, number), TYPED)
    async with sessions() as session:
        assert await held_elsewhere(session, other.org, number)
        assert not await held_elsewhere(session, tenant.org, number)


@needs_the_database
async def test_a_number_added_twice_moves_to_the_new_agent_and_never_doubles(
    sessions: async_sessionmaker[AsyncSession], tenant: Tenant
) -> None:
    """Writing the number again replaces its agent; a call to it finds one route."""
    number = a_number()
    async with sessions.begin() as session:
        await put_route(session, routed(tenant, number, agent="agenda"), TYPED)
        await put_route(session, routed(tenant, number, agent="ventas"), TYPED)
    async with sessions() as session:
        found = await route_at(session, Channel.phone, number)
        listed = await routes_of_org(session, tenant.org, Env.production)
    assert found is not None
    assert found.agent == "ventas"
    assert [route.number for route in listed] == [number]


@needs_the_database
async def test_a_number_moved_into_the_sandbox_answers_there_and_removing_says_if_it_was_there(
    sessions: async_sessionmaker[AsyncSession], tenant: Tenant
) -> None:
    """A number moves between the org's envs whole, and a removal says whether there was a row."""
    number = a_number()
    async with sessions.begin() as session:
        await put_route(session, routed(tenant, number), TYPED)
        assert await move_route(session, tenant.org, number, Env.sandbox)
    async with sessions() as session:
        assert [route.number for route in await routes_of_org(session, tenant.org, Env.sandbox)] == [number]
        assert await routes_of_org(session, tenant.org, Env.production) == []
    async with sessions.begin() as session:
        assert await remove_route(session, tenant.org, number)
        assert not await remove_route(session, tenant.org, number)
