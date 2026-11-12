"""What an app logs from its end hook lands: the seal waits, bounded, for the app that says it will answer."""

import asyncio
import json
import time
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager

import pytest

from runtime.kit.text import JsonObject
from runtime.live.service.ending import END_HOOK_WAITED_S
from tests.conftest import Gateway, Tenant, holding, needs_the_services, received

# Every wait is on the thing itself, with a bound a loaded runner never reaches: a chat, its summary and its
# seal are several round trips, and the default 10 s per test is the quick suites' bound, not theirs.
pytestmark = [needs_the_services, pytest.mark.timeout(120)]

WITHIN_S = 30.0


async def sealed_log(gateway: Gateway, tenant: Tenant, call: str, *, within_s: float = WITHIN_S) -> list[JsonObject]:
    """The call's durable entries, once the gateway has sealed it."""
    deadline = time.monotonic() + within_s
    while True:
        page = (
            await gateway.http.get(f"/v1/calls/{call}/events", params={"durable": True}, headers=tenant.server)
        ).json()
        if not page["live"]:
            return list(page["entries"])
        assert time.monotonic() < deadline, f"call {call} was never sealed"
        await asyncio.sleep(0.05)


@asynccontextmanager
async def a_hung_up_call(gateway: Gateway, tenant: Tenant, agent: str) -> AsyncGenerator[str]:
    """A chat that said one line, was answered, and was ended by its caller; the call's id."""
    async with gateway.socket(f"/v1/chat?agent={agent}", tenant.server) as chat:
        call = str((await received(chat, "call.started"))["call"])
        await chat.send(json.dumps({"text": "hola"}))
        await received(chat, "turn.agent")
        await chat.send(json.dumps({"hangup": True}))
        yield call


def lines_of(entries: list[JsonObject]) -> list[str]:
    """The log's entries by type, an app's own line by its name."""
    return [f"custom:{entry['data']['name']}" if entry["type"] == "custom" else str(entry["type"]) for entry in entries]


# S2 (2026-10-23): a line an app logged from its end hook landed only if it beat call.score, which seals
# the log; the session's writer swallowed the refusal and only a warning was left. The app here answers
# only once the summary is written, when a seal that did not wait would score at once.
async def test_a_line_the_app_logs_from_its_end_hook_lands_before_the_score(
    gateway: Gateway, tenant: Tenant, agent: str
) -> None:
    async with holding(gateway, tenant, agent, says_done=True) as app, a_hung_up_call(gateway, tenant, agent) as call:
        await asyncio.wait_for(received(app, "call.summary"), WITHIN_S)
        logged = {"name": "closed", "data": {"by": "the end hook"}}
        await app.send(json.dumps({"type": "call.log", "agent": agent, "call": call, "data": logged}))
        await app.send(json.dumps({"type": "call.done", "agent": agent, "call": call, "data": {}}))
        lines = lines_of(await sealed_log(gateway, tenant, call))
    assert "custom:closed" in lines
    assert lines.index("custom:closed") < lines.index("call.score") == len(lines) - 1


async def test_an_app_that_never_answers_costs_the_call_the_bound_and_no_more(
    gateway: Gateway, tenant: Tenant, agent: str, caplog: pytest.LogCaptureFixture
) -> None:
    async with holding(gateway, tenant, agent, says_done=True), a_hung_up_call(gateway, tenant, agent) as call:
        lines = lines_of(await sealed_log(gateway, tenant, call))
    assert lines[-1] == "call.score" and "call.summary" in lines
    assert f"call {call}: its app did not say its end hook ran within {END_HOOK_WAITED_S:g} s" in caplog.text


# A seal that waited for it would say, the bound over, that the app never answered.
async def test_an_app_that_does_not_say_it_will_answer_is_not_waited_for(
    gateway: Gateway, tenant: Tenant, agent: str, caplog: pytest.LogCaptureFixture
) -> None:
    async with holding(gateway, tenant, agent), a_hung_up_call(gateway, tenant, agent) as call:
        lines = lines_of(await sealed_log(gateway, tenant, call))
    assert lines[-1] == "call.score"
    assert "did not say its end hook ran" not in caplog.text


# The app's word after its hook, for a call sealed already, is dropped: a refusal on the agent's log for
# every call whose hook was slow would be noise nobody reads.
async def test_a_call_done_for_a_call_that_was_sealed_already_is_dropped_without_an_error(
    gateway: Gateway, tenant: Tenant, agent: str
) -> None:
    async with holding(gateway, tenant, agent) as app:
        async with a_hung_up_call(gateway, tenant, agent) as call:
            await sealed_log(gateway, tenant, call)
        await app.send(json.dumps({"type": "call.done", "agent": agent, "call": call, "data": {}}))
        await app.send(json.dumps({"type": "ping", "agent": agent, "call": None, "data": {}}))
        errors: list[JsonObject] = []
        while True:
            frame: JsonObject = json.loads(await asyncio.wait_for(app.recv(), WITHIN_S))
            if frame["type"] == "pong":
                break
            if frame["type"] == "error":
                errors.append(frame)
    assert errors == []


# What an app logs once its call's log is sealed never lands, whether the gateway still serves the call
# when the line arrives or let it go already. Sent once the log says sealed: a line sent as the score
# arrives races the seal that follows the score. That the refusal is named in the journal is the
# session's writer's to say (`tests/session/test_writing.py`).
async def test_a_line_logged_after_the_log_was_sealed_never_lands(gateway: Gateway, tenant: Tenant, agent: str) -> None:
    async with holding(gateway, tenant, agent) as app, a_hung_up_call(gateway, tenant, agent) as call:
        await sealed_log(gateway, tenant, call)
        late: JsonObject = {"name": "too-late", "data": {}}
        await app.send(json.dumps({"type": "call.log", "agent": agent, "call": call, "data": late}))
        await app.send(json.dumps({"type": "ping", "agent": agent, "call": None, "data": {}}))
        await asyncio.wait_for(received(app, "pong"), WITHIN_S)
        lines = lines_of(await sealed_log(gateway, tenant, call))
    assert "custom:too-late" not in lines
    assert lines[-1] == "call.score"
