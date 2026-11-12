"""The SIP rebuild: an org its LiveKit refuses is refused alone, and only what is owed is tried again until whole."""

import os
from collections.abc import AsyncIterator

import pytest
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from runtime.enums import Channel, Env
from runtime.kit.crypto import Vault
from runtime.telephony.repository import RouteRepository, RouteToWrite
from runtime.telephony.service import rebuild
from runtime.telephony.service.rebuild import NotWhole, Owed
from tests.conftest import Tenant, make_tenant, needs_the_database
from tests.fakes.livekit import Server, per_world
from tests.telephony.conftest import NAMES, a_number

pytestmark = needs_the_database

VAULT = Vault(os.environ["PINECALL_VAULT_KEY"])


async def routed(sessions: async_sessionmaker[AsyncSession], tenant: Tenant, env: Env) -> str:
    """A phone number of the tenant's in the env, as the table keeps it; the number."""
    number = a_number()
    async with sessions.begin() as session:
        await RouteRepository(session).put(
            RouteToWrite(org=tenant.org, number=number, agent="agenda", channel=Channel.phone, env=env)
        )
    return number


async def rebuilt(
    sessions: async_sessionmaker[AsyncSession], servers: dict[Env, Server], owed: Owed
) -> rebuild.Rebuilt:
    """One pass of the rebuild over what is owed, in one transaction as the loop runs it."""
    async with sessions.begin() as session:
        return await rebuild.rebuild(session, VAULT, servers, NAMES, owed)


def admitted(server: Server, number: str) -> bool:
    """Whether a trunk of that LiveKit admits the number."""
    return any(number in trunk.numbers for trunk in server.dialled.trunks.values())


@pytest.fixture
async def servers() -> AsyncIterator[dict[Env, Server]]:
    """Each env's own LiveKit, empty, as after Redis was emptied; closed after."""
    opened = per_world()
    yield opened
    for server in opened.values():
        await server.aclose()


# An org whose numbers raised anything but an SFU error ended the rebuild, and every org after it went
# unadmitted; the retry that waits for the SFU caught four classes and ended on any other.
async def test_an_org_its_livekit_refuses_is_refused_alone_and_the_next_is_admitted(
    sessions: async_sessionmaker[AsyncSession], servers: dict[Env, Server]
) -> None:
    starting, answering = await make_tenant(sessions), await make_tenant(sessions)
    refused = await routed(sessions, starting, Env.sandbox)
    number = await routed(sessions, answering, Env.production)
    # The sandbox's LiveKit is still starting: the first thing asked of it is refused.
    servers[Env.sandbox].dialled.starting = 1
    passed = await rebuilt(sessions, servers, Owed(orgs=[starting.org, answering.org]))
    assert (passed.numbers, passed.refused) == (1, [starting.org])
    assert admitted(servers[Env.production], number)
    assert not admitted(servers[Env.sandbox], refused)


# Until 2026-11 a pass that left one org refused rebuilt every org of the box again, once a minute.
async def test_a_pass_that_left_an_org_refused_owes_that_org_alone_until_it_stands(
    sessions: async_sessionmaker[AsyncSession], servers: dict[Env, Server]
) -> None:
    starting, answering = await make_tenant(sessions), await make_tenant(sessions)
    number = await routed(sessions, starting, Env.sandbox)
    await routed(sessions, answering, Env.production)
    owed = Owed(orgs=[starting.org, answering.org])
    assert not owed.nothing
    servers[Env.sandbox].dialled.starting = 1
    with pytest.raises(NotWhole):
        owed.settle(await rebuilt(sessions, servers, owed))
    assert owed.orgs == [starting.org]
    again = await rebuilt(sessions, servers, owed)
    assert (again.numbers, again.refused) == (1, [])
    owed.settle(again)
    assert owed.nothing
    assert admitted(servers[Env.sandbox], number)
