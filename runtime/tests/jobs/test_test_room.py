"""A test room's own voice and models: asked for at the token, carried to the worker, over the agent for that call."""

import json

from pinecall_runtime.enums import Env
from pinecall_runtime.jobs.service.client import GatewayClient
from pinecall_runtime.kit.auth import Scope
from pinecall_runtime.wire.dispatch import Dispatch
from tests.conftest import Gateway, Tenant, holding, needs_the_services

pytestmark = needs_the_services


async def test_a_worker_asking_for_a_calls_config_with_a_test_rooms_values_gets_the_agent_under_them(
    gateway: Gateway, tenant: Tenant, agent: str, fleet: GatewayClient
) -> None:
    """The values ride the call's reads and are checked again there; the agent's own settings do not move."""
    scope = Scope(tenant.org, Env.sandbox, "")
    async with holding(gateway, tenant, agent):
        plain = await fleet.agent(agent, scope, call="call_a")
        tried = await fleet.agent(agent, scope, call="call_b", test={"voice": "a-voice-of-the-test-room"})
        again = await fleet.agent(agent, scope, call="call_c")
    assert tried.voice != plain.voice and "a-voice-of-the-test-room" in str(tried.voice)
    assert again.voice == plain.voice


async def test_a_room_token_carries_the_values_in_its_dispatch_and_asks_for_nothing_it_may_not(
    gateway: Gateway, tenant: Tenant, agent: str
) -> None:
    """The sandbox's token takes a voice; another knob is refused with the reason."""
    async with holding(gateway, tenant, agent):
        taken = await gateway.http.post(
            "/v1/tokens",
            json={"agent": agent, "scope": "talk", "tuning": {"voice": "lucia"}},
            headers=tenant.person,
        )
        assert taken.status_code == 201, taken.text
        refused = await gateway.http.post(
            "/v1/tokens",
            json={"agent": agent, "scope": "talk", "tuning": {"record": False}},
            headers=tenant.person,
        )
        assert refused.status_code == 400, refused.text
    assert "record" in json.dumps(refused.json())
    assert Dispatch(tuning={"voice": "lucia"}).dump() == '{"tuning":{"voice":"lucia"}}'
