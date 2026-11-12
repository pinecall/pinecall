"""The routes table: one org per number on the box, an org's numbers its own in each env, a number moved whole."""

import secrets

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from runtime.enums import Channel, Env
from runtime.scoping import box_wide
from runtime.telephony.repository import RouteRepository, RouteToWrite
from tests.conftest import Tenant, make_tenant, needs_the_database

pytestmark = needs_the_database


def a_number() -> str:
    """A number of this test alone: a number is one org's on the whole box."""
    return f"+1555{secrets.randbelow(10**7):07d}"


def routed(tenant: Tenant, number: str, env: Env = Env.production, agent: str = "agenda") -> RouteToWrite:
    """The tenant's agent answering the number in the env."""
    return RouteToWrite(org=tenant.org, number=number, agent=agent, channel=Channel.phone, env=env)


async def numbers_of(session: AsyncSession, org: str, env: Env) -> list[tuple[str, Env]]:
    """The org's numbers in the env, as its list reads them."""
    return [(one.route.number, one.route.env) for one in await RouteRepository(session).list_of_org(org, env)]


async def test_an_orgs_routes_are_its_own_in_the_env_asked(
    sessions: async_sessionmaker[AsyncSession], tenant: Tenant
) -> None:
    """An org reads its numbers of one env, never another env's or another org's."""
    other = await make_tenant(sessions)
    mine, sandboxed, theirs = a_number(), a_number(), a_number()
    async with sessions.begin() as session:
        routes = RouteRepository(session)
        await routes.put(routed(tenant, mine))
        await routes.put(routed(tenant, sandboxed, Env.sandbox))
        await routes.put(routed(other, theirs))
    async with sessions() as session:
        assert await numbers_of(session, tenant.org, Env.production) == [(mine, Env.production)]


async def test_a_number_one_org_holds_is_read_as_held_elsewhere_by_another(
    sessions: async_sessionmaker[AsyncSession], tenant: Tenant
) -> None:
    """One org holds a number on the box; to any other org it is held elsewhere."""
    other = await make_tenant(sessions)
    number = a_number()
    async with sessions.begin() as session:
        await RouteRepository(session).put(routed(tenant, number))
    async with sessions() as session:
        routes = RouteRepository(session)
        with box_wide():
            assert await routes.is_held_elsewhere(other.org, number)
            assert not await routes.is_held_elsewhere(tenant.org, number)


async def test_a_number_added_twice_moves_to_the_new_agent_and_never_doubles(
    sessions: async_sessionmaker[AsyncSession], tenant: Tenant
) -> None:
    """Writing the number again replaces its agent; a call to it finds one route."""
    number = a_number()
    async with sessions.begin() as session:
        routes = RouteRepository(session)
        await routes.put(routed(tenant, number, agent="agenda"))
        await routes.put(routed(tenant, number, agent="ventas"))
    async with sessions() as session:
        with box_wide():
            found = await RouteRepository(session).find_at(Channel.phone, number)
        listed = await numbers_of(session, tenant.org, Env.production)
    assert found is not None and found.agent == "ventas"
    assert listed == [(number, Env.production)]


async def test_a_number_written_into_the_sandbox_answers_there_and_a_removal_says_if_it_was_there(
    sessions: async_sessionmaker[AsyncSession], tenant: Tenant
) -> None:
    """A number moves between the org's envs whole, and a removal says whether there was a row."""
    number = a_number()
    async with sessions.begin() as session:
        routes = RouteRepository(session)
        await routes.put(routed(tenant, number))
        await routes.put(routed(tenant, number, Env.sandbox))
    async with sessions() as session:
        assert await numbers_of(session, tenant.org, Env.sandbox) == [(number, Env.sandbox)]
        assert await numbers_of(session, tenant.org, Env.production) == []
    async with sessions.begin() as session:
        routes = RouteRepository(session)
        assert await routes.delete_of(tenant.org, number)
        assert not await routes.delete_of(tenant.org, number)
