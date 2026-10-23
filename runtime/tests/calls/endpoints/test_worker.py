"""A worker's endpoints on its call: what they take, what the seal does with it, and whose seat a sealed call holds."""

import asyncio
import time
from collections.abc import AsyncIterator
from datetime import date

import pytest
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from pinecall_runtime.accounts.service import keys
from pinecall_runtime.alerts import service as alerts
from pinecall_runtime.calls.context import CallContext, Route, new_call_id
from pinecall_runtime.calls.schemas import OpenCallRequest, SealCallRequest
from pinecall_runtime.calls.service import reaper, seal
from pinecall_runtime.calls.store import Store
from pinecall_runtime.enums import Channel, Direction, Env, KeyScope
from pinecall_runtime.exceptions import GatewayUnavailable
from pinecall_runtime.jobs.service.client import GatewayClient, gateway_at
from pinecall_runtime.kit.text import JsonObject
from pinecall_runtime.wire.base import BatchedEntry
from tests.calls.gateways import a_second_gateway
from tests.conftest import Gateway, Tenant, holding, make_tenant, needs_the_services

pytestmark = needs_the_services

NO_CALLER: JsonObject = {
    "channel": "web",
    "direction": "inbound",
    "from": "web_1",
    "to": "clinica-norte",
    "started_at": 1.0,
}
AN_END: JsonObject = {"reason": "caller_hung_up", "ended_by": "caller", "ended_at": 5.0, "duration_s": 4.0}
SEALING = SealCallRequest(usage=[], outcome="done")


def a_call(tenant: Tenant, agent: str) -> CallContext:
    """A sandbox call of the tenant's agent through the widget."""
    return CallContext(
        call=new_call_id(),
        channel=Channel.web,
        direction=Direction.inbound,
        caller="web_1",
        route=Route(org=tenant.org, agent=agent, channel=Channel.web, env=Env.sandbox),
        today=date(2026, 10, 23),
    )


# M B10 (2026-10-23): the endpoints took a call.started with no `caller` (`Contact | null`, required
# by wire/events-call.md), and the seal of its call answered 500 for ever, the call holding its seat.
async def test_a_call_started_with_no_caller_is_refused_by_every_endpoint_that_writes_and_nothing_is_written(
    fleet: GatewayClient, tenant: Tenant, agent: str, store: Store
) -> None:
    context = a_call(tenant, agent)
    call = context.call
    await fleet.open(OpenCallRequest(agent=agent, context=context))

    one = await fleet.http.post(f"/v1/calls/{call}/events", json={"type": "call.started", "data": NO_CALLER})
    assert one.status_code == 400 and "caller" in one.json()["detail"]

    lines: list[JsonObject] = [
        {"type": "custom", "data": {"name": "first", "data": {}}, "ts": time.time()},
        {"type": "call.started", "data": NO_CALLER, "ts": time.time()},
    ]
    batch = await fleet.http.post(f"/v1/calls/{call}/entries", json={"after": 0, "entries": lines})
    assert batch.status_code == 400 and "caller" in batch.json()["detail"]

    with pytest.raises(GatewayUnavailable, match="caller") as socket:
        await fleet.append_many(call, [BatchedEntry(type="call.started", data=NO_CALLER, ts=time.time())], after=0)
    assert socket.value.answered == 400

    assert [entry.type for entry in await store.whole(call)] == ["call.ringing"]
    answered = await fleet.http.post(
        f"/v1/calls/{call}/events", json={"type": "call.started", "data": {**NO_CALLER, "caller": None}}
    )
    assert answered.status_code == 200, answered.text
    await fleet.sealed(call, SEALING)
    assert await store.is_sealed(call)


async def test_a_call_whose_start_the_log_took_before_the_endpoints_read_it_is_sealed_all_the_same(
    fleet: GatewayClient, gateway: Gateway, tenant: Tenant, agent: str, store: Store
) -> None:
    """A log written before the refusal holds one: its seal writes the summary and the score, and lets go."""
    context = a_call(tenant, agent)
    call = context.call
    await fleet.open(OpenCallRequest(agent=agent, context=context))
    await store.append(call, agent, "call.started", NO_CALLER, ephemeral=False)
    await store.append(call, agent, "call.ended", AN_END, ephemeral=False)
    sealed = await fleet.http.post(f"/v1/calls/{call}/sealed", json=SEALING.dump())
    assert sealed.status_code == 204, sealed.text
    kinds = [entry.type for entry in await store.whole(call)]
    assert kinds[-2:] == ["call.summary", "call.score"]
    assert await store.is_sealed(call)
    assert call not in gateway.app.state.serving.live.calls


# K F5 (2026-10-23): the seat of a call is the gateway's memory of it, and it leaves only when the
# seal says so. The log is sealed by the score, and what the seal does after it must not hold it.
async def test_a_call_whose_bookkeeping_after_its_score_failed_is_over_and_holds_no_seat(
    monkeypatch: pytest.MonkeyPatch, fleet: GatewayClient, gateway: Gateway, tenant: Tenant, agent: str, store: Store
) -> None:
    async def unreadable(*_args: object, **_kwargs: object) -> None:
        raise RuntimeError("the org's monitors could not be read")

    monkeypatch.setattr(alerts, "check_monitors", unreadable)
    context = a_call(tenant, agent)
    await fleet.open(OpenCallRequest(agent=agent, context=context))
    sealed = await fleet.http.post(f"/v1/calls/{context.call}/sealed", json=SEALING.dump())
    assert sealed.status_code == 500
    assert await store.is_sealed(context.call)
    assert context.call not in gateway.app.state.serving.live.calls


@pytest.fixture
async def opened_here_sealed_there(
    gateway: Gateway, sessions: async_sessionmaker[AsyncSession]
) -> AsyncIterator[tuple[GatewayClient, GatewayClient]]:
    """A worker's client to the suite's gateway and to a second one: a call opens on one, seals on the other."""
    the_box = await make_tenant(sessions)
    async with sessions.begin() as session:
        issue = keys.Issue(
            org=the_box.org, env=Env.sandbox, scopes=frozenset({KeyScope.fleet}), label="the suite's fleet"
        )
        _, secret = await keys.issue_key(session, issue)
    async with a_second_gateway() as other:
        opener, sealer = gateway_at(gateway.url, secret), gateway_at(other.url, secret)
        yield opener, sealer
        await opener.aclose()
        await sealer.aclose()


# The balancer hashes a call's requests to one gateway, but `POST /v1/calls` names no call, so the
# gateway that opened a call and the one its worker seals it on are the same only half the time.
async def test_a_call_the_other_gateway_sealed_is_let_go_by_the_one_that_opened_it(
    opened_here_sealed_there: tuple[GatewayClient, GatewayClient], gateway: Gateway, tenant: Tenant, agent: str
) -> None:
    opener, sealer = opened_here_sealed_there
    live = gateway.app.state.serving.live
    context = a_call(tenant, agent)
    await opener.open(OpenCallRequest(agent=agent, context=context))
    assert live.running(tenant.org, Env.sandbox) == 1
    await sealer.sealed(context.call, SEALING)
    assert live.running(tenant.org, Env.sandbox) == 1, "the seat is the opener's memory, told at its next pass"
    assert context.call in await reaper.let_go(gateway.app.state.serving, time.monotonic())
    assert live.running(tenant.org, Env.sandbox) == 0


async def test_a_call_erased_after_the_other_gateway_sealed_it_holds_no_seat_either(
    opened_here_sealed_there: tuple[GatewayClient, GatewayClient], gateway: Gateway, tenant: Tenant, agent: str
) -> None:
    """Erasing the stuck calls of the eval freed none of their seats: the head the pass looked for was gone."""
    opener, sealer = opened_here_sealed_there
    live = gateway.app.state.serving.live
    context = a_call(tenant, agent)
    await opener.open(OpenCallRequest(agent=agent, context=context))
    await sealer.sealed(context.call, SEALING)
    erased = await gateway.http.delete(f"/v1/calls/{context.call}", headers=tenant.person)
    assert erased.status_code == 200, erased.text
    assert live.running(tenant.org, Env.sandbox) == 1
    assert context.call in await reaper.let_go(gateway.app.state.serving, time.monotonic())
    assert live.running(tenant.org, Env.sandbox) == 0


# S2 (2026-10-23): what an app logs from its end hook lands only before call.score. A worker's call is
# sealed by the gateway while its session is in the worker: the app's word comes down the commands stream
# to the session, which says it to the gateway on `/done`, and the seal that waited goes on.
async def test_a_seal_waits_for_the_app_that_says_done_until_the_worker_says_it_on_done(
    monkeypatch: pytest.MonkeyPatch, fleet: GatewayClient, gateway: Gateway, tenant: Tenant, agent: str, store: Store
) -> None:
    monkeypatch.setattr(seal, "END_HOOK_WAITED_S", 60.0)
    context = a_call(tenant, agent)
    call = context.call
    async with holding(gateway, tenant, agent, says_done=True):
        await fleet.open(OpenCallRequest(agent=agent, context=context))
        sealing = asyncio.create_task(fleet.sealed(call, SEALING))
        waited, _ = await asyncio.wait({sealing}, timeout=0.5)
        assert not waited and not await store.is_sealed(call), "the seal waits for the app's word"
        await fleet.done(call)
        await asyncio.wait_for(sealing, 30)
    assert await store.is_sealed(call)


async def test_the_apps_word_for_a_call_sealed_already_is_taken_without_an_error(
    fleet: GatewayClient, tenant: Tenant, agent: str
) -> None:
    context = a_call(tenant, agent)
    await fleet.open(OpenCallRequest(agent=agent, context=context))
    await fleet.sealed(context.call, SEALING)
    await fleet.done(context.call)
