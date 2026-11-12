"""The box's test line: set by the operator, and a ring at it sent to the caller's own sandbox agent."""

import json
import secrets

import pytest
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from runtime.enums import Channel, Env
from runtime.exceptions import ValidationError
from runtime.jobs.service.client import GatewayClient
from runtime.telephony.repository import RouteRepository, RouteToWrite
from runtime.telephony.service.test_line import find_test_line, put_test_line
from runtime.wire.commands import AgentRegister
from runtime.wire.worker import RingAtTestLine
from tests.conftest import BOX, Gateway, Tenant, holding, needs_the_database, needs_the_services, received


def a_number() -> str:
    """A number of this test alone: a number is one org's on the whole box."""
    return f"+1555{secrets.randbelow(10**7):07d}"


# A phone is one person's on the whole box and the suites run in parallel: each test says one of its own.
def sandbox_route(tenant: Tenant, number: str, env: Env = Env.sandbox, agent: str = "greeter") -> RouteToWrite:
    """The tenant's agent answering the number in the env."""
    return RouteToWrite(org=tenant.org, number=number, agent=agent, channel=Channel.phone, env=env)


@needs_the_database
async def test_the_test_line_is_one_of_the_boxs_own_sandbox_numbers_and_none_forgets_it(
    sessions: async_sessionmaker[AsyncSession], tenant: Tenant
) -> None:
    number = a_number()
    async with sessions.begin() as session:
        routes = RouteRepository(session)
        with pytest.raises(ValidationError, match="not a number of this box in the sandbox"):
            await put_test_line(session, number)
        await routes.put(sandbox_route(tenant, number, Env.production))
        with pytest.raises(ValidationError, match="not a number of this box in the sandbox"):
            await put_test_line(session, number)
        await routes.put(sandbox_route(tenant, number))
        assert await put_test_line(session, number) == number
        assert await find_test_line(session) == number
        assert await put_test_line(session, None) is None
        assert await find_test_line(session) is None


# The box has one test line and the suites run in parallel: every scenario that sets it is this one test.
@needs_the_services
async def test_a_ring_at_the_test_line_from_a_phone_a_person_said_was_theirs_is_their_orgs_agents(
    gateway: Gateway, tenant: Tenant, agent: str, fleet: GatewayClient, sessions: async_sessionmaker[AsyncSession]
) -> None:
    number, caller = a_number(), a_number()
    async with sessions.begin() as session:
        await RouteRepository(session).put(sandbox_route(tenant, number))
    made = await gateway.http.put("/v1/ops/test-line", json={"number": number}, headers=BOX)
    assert made.status_code == 200 and made.json() == {"number": number}
    assert await fleet.ring_at_test_line(number, caller) == RingAtTestLine(), "a phone nobody said was theirs"

    said = await gateway.http.put("/v1/line/from", json={"number": caller}, headers=tenant.person)
    assert said.status_code == 200, said.text
    assert (said.json()["calling"], said.json()["test_line"], said.json()["agent"]) == ([caller], number, None)
    assert await fleet.ring_at_test_line(number, caller) == RingAtTestLine(org=tenant.org), "nothing held yet"
    assert await fleet.ring_at_test_line(a_number(), caller) == RingAtTestLine(), "another number is not the line"

    # The org's own copy (a server's, a hosted app's, Studio's) takes it when nobody of theirs holds one.
    async with holding(gateway, tenant, agent):
        assert await fleet.ring_at_test_line(number, caller) == RingAtTestLine(org=tenant.org, agent=agent, holder="")
        # Their own copy first, once they hold one.
        async with gateway.socket("/v1/apps", tenant.person) as mine:
            register = AgentRegister(routes=[]).model_dump(mode="json")
            await mine.send(json.dumps({"type": "agent.register", "agent": agent, "call": None, "data": register}))
            await received(mine, "agent.registered")
            handed = await fleet.ring_at_test_line(number, caller)
            assert handed == RingAtTestLine(org=tenant.org, agent=agent, holder=tenant.member)
    assert await fleet.ring_at_test_line(number, caller) == RingAtTestLine(org=tenant.org), (
        "nobody holds anything now, and no agent was named"
    )

    # Two held and none named: the person picks; an agent the org never held is refused by name.
    async with holding(gateway, tenant, agent), holding(gateway, tenant, f"{agent}-2"):
        assert await fleet.ring_at_test_line(number, caller) == RingAtTestLine(org=tenant.org), "two held, none named"
        unknown = await gateway.http.put(
            "/v1/line/from", json={"number": caller, "agent": "nobodys"}, headers=tenant.person
        )
        assert unknown.status_code == 404
        named = await gateway.http.put("/v1/line/from", json={"number": caller, "agent": agent}, headers=tenant.person)
        assert named.json()["agent"] == agent
        assert await fleet.ring_at_test_line(number, caller) == RingAtTestLine(org=tenant.org, agent=agent, holder="")

    listed = await gateway.http.get("/v1/line/numbers", headers=tenant.person)
    assert (listed.json()["calling"], listed.json()["test_line"]) == ([caller], number)
    forgot = await gateway.http.delete("/v1/line/from", headers=tenant.person)
    assert forgot.json() == {"forgot": [caller]}
    assert await fleet.ring_at_test_line(number, caller) == RingAtTestLine()
    await gateway.http.put("/v1/ops/test-line", json={"number": None}, headers=BOX)
