"""The next process takes the call the last one parked, whichever gateways the call and the processes are on."""

import asyncio
import json

import pytest

from runtime.actor import Scope
from runtime.enums import Env
from runtime.kit.text import JsonObject
from runtime.live.parts import LiveParts
from runtime.live.served import Served
from tests.conftest import Gateway, Tenant, holding, needs_the_services, received, until
from tests.live.gateways import a_second_gateway

DRAIN: JsonObject = {"type": "agent.drain", "call": None, "data": {}}
# Every wait is on the thing itself, with a bound a loaded runner never reaches: the handoff is two gateways
# talking on a lossy signal, and the test acts only once each side is listening (the second gateway's
# lifespan returns once its handoffs are heard on, and a socket's frames are read once its inbox is).
WITHIN_S = 30.0


def served_as(live: LiveParts, call: str) -> Served:
    """The call as the gateway serves it."""
    served = live.calls.find(call)
    assert served is not None, f"{call} is not served here"
    return served


# B B2 (2026-10-23): the call opened on one gateway, its process held the agent on one gateway and
# left, and the next process registered on one gateway again; any two of the three could be the
# same, and the call was handed on only when the opener held the next socket too, or never: its
# tools waited out their deadline and it ended as app_detached.
@needs_the_services
@pytest.mark.timeout(120)
@pytest.mark.parametrize(
    ("old_on", "new_on"),
    [("opener", "opener"), ("opener", "other"), ("other", "other"), ("other", "opener")],
    ids=["all-on-one", "next-on-the-other", "last-and-next-on-the-other", "last-on-the-other"],
)
async def test_the_next_process_takes_the_call_the_last_one_parked(
    gateway: Gateway, tenant: Tenant, agent: str, old_on: str, new_on: str
) -> None:
    scope = Scope(tenant.org, Env.sandbox)
    live: LiveParts = gateway.state["live"]
    async with a_second_gateway() as other:
        gateways = {"opener": gateway, "other": other}
        async with holding(gateways[old_on], tenant, agent) as old:
            await until(lambda: live.holders.find_holder(scope, agent) is not None, WITHIN_S)
            async with gateway.socket(f"/v1/chat?agent={agent}", tenant.server) as chat:
                call = str((await asyncio.wait_for(received(chat, "call.started"), WITHIN_S))["call"])
                await asyncio.wait_for(received(old, "call.started"), WITHIN_S)

                await old.send(json.dumps({**DRAIN, "agent": agent}))
                draining = (await asyncio.wait_for(received(old, "agent.draining"), WITHIN_S))["data"]
                assert (draining["handed"], draining["parked"]) == (0, 1)
                await until(lambda: served_as(live, call).app is None, WITHIN_S)
                assert call in [parked.call for parked in live.calls.list_parked()]

                async with holding(gateways[new_on], tenant, agent) as new:
                    attached = (await asyncio.wait_for(received(new, "call.attached"), WITHIN_S))["data"]
                    assert attached["started"]["to"] == agent
                    await chat.send(json.dumps({"text": "hola"}))
                    heard = (await asyncio.wait_for(received(new, "turn.user"), WITHIN_S))["data"]
                    assert heard["text"] == "hola"
                    assert served_as(live, call).app is not None
                await chat.send(json.dumps({"hangup": True}))
