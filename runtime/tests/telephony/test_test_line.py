"""The box's test line: set by the operator, and a ring at it sent to the caller's own sandbox agent."""

import json

import pytest
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from pinecall_runtime.calls.context import Route
from pinecall_runtime.channels.models import Route as RouteRow
from pinecall_runtime.channels.service.routes import put_route
from pinecall_runtime.enums import Channel, Env
from pinecall_runtime.exceptions import ValidationError
from pinecall_runtime.jobs.service.client import GatewayClient
from pinecall_runtime.telephony.schemas import RingAtTestLine
from pinecall_runtime.telephony.service.test_line import get_test_line, handed_to, may_be_a_testers, put_test_line
from pinecall_runtime.wire.commands import AgentRegister
from pinecall_runtime.wire.dispatch import Dispatch
from tests.channels.test_routes import A_PAGE, A_PHONE, AT_THE_NUMBER, IN_THE_SANDBOX, NUMBER, TYPED
from tests.conftest import BOX, Gateway, Tenant, holding, make_tenant, needs_the_database, needs_the_services, received
from tests.telephony.conftest import a_number


def test_only_an_undispatched_ring_at_a_sandbox_number_may_be_a_testers() -> None:
    assert may_be_a_testers(Dispatch(org="org_box", env=Env.sandbox), A_PHONE, IN_THE_SANDBOX)
    assert not may_be_a_testers(Dispatch(), A_PHONE, AT_THE_NUMBER), "production's rings are the hand-over's"
    assert not may_be_a_testers(Dispatch(agent="front"), A_PHONE, IN_THE_SANDBOX), "a job told its agent"
    assert not may_be_a_testers(Dispatch(), A_PAGE, IN_THE_SANDBOX), "a page dialled no number"


def test_the_route_a_known_caller_takes_is_their_orgs_agent_at_the_number_dialled() -> None:
    assert handed_to(IN_THE_SANDBOX, A_PHONE, "org_b", "front") == Route(
        org="org_b", agent="front", channel=Channel.phone, number=NUMBER, env=Env.sandbox
    )


# A phone is one person's on the whole box and the suites run in parallel: each test says one of its own.
def sandbox_route(tenant: Tenant, number: str, env: Env = Env.sandbox, agent: str = "greeter") -> RouteRow:
    """The tenant's agent answering the number in the env, as the table keeps it."""
    return RouteRow(org=tenant.org, agent=agent, channel=Channel.phone, number=number, env=env, managed=False)


@needs_the_database
async def test_the_test_line_is_one_of_the_boxs_own_sandbox_numbers_and_none_forgets_it(
    sessions: async_sessionmaker[AsyncSession], tenant: Tenant
) -> None:
    number = a_number()
    async with sessions.begin() as session:
        with pytest.raises(ValidationError, match="not a number of this box in the sandbox"):
            await put_test_line(session, number)
        await put_route(session, sandbox_route(tenant, number, Env.production), TYPED)
        with pytest.raises(ValidationError, match="not a number of this box in the sandbox"):
            await put_test_line(session, number)
        await put_route(session, sandbox_route(tenant, number), TYPED)
        assert await put_test_line(session, number) == number
        assert await get_test_line(session) == number
        assert await put_test_line(session, None) is None
        assert await get_test_line(session) is None


# The box has one test line and the suites run in parallel: every scenario that sets it is this one test.
@needs_the_services
async def test_a_ring_at_the_test_line_from_a_phone_a_person_said_was_theirs_is_their_orgs_agents(
    gateway: Gateway, tenant: Tenant, agent: str, fleet: GatewayClient, sessions: async_sessionmaker[AsyncSession]
) -> None:
    number, caller = a_number(), a_number()
    async with sessions.begin() as session:
        await put_route(session, sandbox_route(tenant, number), TYPED)
    made = await gateway.http.put("/v1/ops/test-line", json={"number": number}, headers=BOX)
    assert made.status_code == 200 and made.json() == {"number": number}
    assert await fleet.test_line_rings_for(number, caller) == RingAtTestLine(), "a phone nobody said was theirs"

    said = await gateway.http.put("/v1/line/from", json={"number": caller}, headers=tenant.person)
    assert said.status_code == 200, said.text
    assert (said.json()["calling"], said.json()["test_line"], said.json()["agent"]) == ([caller], number, None)
    assert await fleet.test_line_rings_for(number, caller) == RingAtTestLine(org=tenant.org), "nothing held yet"
    assert await fleet.test_line_rings_for(a_number(), caller) == RingAtTestLine(), "another number is not the line"

    # The org's own copy (a server's, a hosted app's, Studio's) takes it when nobody of theirs holds one.
    async with holding(gateway, tenant, agent):
        assert await fleet.test_line_rings_for(number, caller) == RingAtTestLine(org=tenant.org, agent=agent, holder="")
        # Their own copy first, once they hold one.
        async with gateway.socket("/v1/apps", tenant.person) as mine:
            register = AgentRegister(routes=[]).model_dump(mode="json")
            await mine.send(json.dumps({"type": "agent.register", "agent": agent, "call": None, "data": register}))
            await received(mine, "agent.registered")
            handed = await fleet.test_line_rings_for(number, caller)
            assert handed == RingAtTestLine(org=tenant.org, agent=agent, holder=tenant.member)
    assert await fleet.test_line_rings_for(number, caller) == RingAtTestLine(org=tenant.org), (
        "nobody holds anything now, and no agent was named"
    )

    # Two held and none named: the person picks; an agent the org never held is refused by name.
    async with holding(gateway, tenant, agent), holding(gateway, tenant, f"{agent}-2"):
        assert await fleet.test_line_rings_for(number, caller) == RingAtTestLine(org=tenant.org), "two held, none named"
        unknown = await gateway.http.put(
            "/v1/line/from", json={"number": caller, "agent": "nobodys"}, headers=tenant.person
        )
        assert unknown.status_code == 404
        named = await gateway.http.put("/v1/line/from", json={"number": caller, "agent": agent}, headers=tenant.person)
        assert named.json()["agent"] == agent
        assert await fleet.test_line_rings_for(number, caller) == RingAtTestLine(org=tenant.org, agent=agent, holder="")

    listed = await gateway.http.get("/v1/line/numbers", headers=tenant.person)
    assert (listed.json()["calling"], listed.json()["test_line"]) == ([caller], number)
    forgot = await gateway.http.delete("/v1/line/from", headers=tenant.person)
    assert forgot.json() == {"forgot": [caller]}
    assert await fleet.test_line_rings_for(number, caller) == RingAtTestLine()
    await gateway.http.put("/v1/ops/test-line", json={"number": None}, headers=BOX)


# A Studio agent is held by the gateway in the org's own corner: a developer's phone at the
# production number reached nothing of the sandbox's (2026-11-05), the hand-over wanted a person's.
@needs_the_services
async def test_a_production_ring_from_a_members_phone_is_handed_to_the_orgs_own_sandbox_copy_and_to_no_other_orgs(
    gateway: Gateway, tenant: Tenant, agent: str, fleet: GatewayClient, sessions: async_sessionmaker[AsyncSession]
) -> None:
    caller = a_number()
    async with holding(gateway, tenant, agent):
        assert (await fleet.rings_for(agent, tenant.org, caller)).holder is None, "a phone nobody said was theirs"
        await gateway.http.put("/v1/line/from", json={"number": caller}, headers=tenant.person)
        assert (await fleet.rings_for(agent, tenant.org, caller)).holder == ""
        # Another org's member saying the phone is theirs takes it: it diverts nothing of this org's.
        other = await make_tenant(sessions)
        await gateway.http.put("/v1/line/from", json={"number": caller}, headers=other.person)
        assert (await fleet.rings_for(agent, tenant.org, caller)).holder is None
        await gateway.http.delete("/v1/line/from", headers=other.person)
