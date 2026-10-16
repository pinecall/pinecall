"""A written call end to end: an app holds the agent, a caller chats, the call is sealed and metered."""

import asyncio
import json
import secrets
import time

import pytest
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from pinecall_runtime.calls.models.drift import DriftCall
from pinecall_runtime.enums import Env
from pinecall_runtime.kit.text import JsonObject
from tests.conftest import Gateway, Tenant, holding, needs_the_services, received
from tests.fakes import acme

# The seal runs after the caller hangs up: the log is read until it says the call is over.
SEALED_WITHIN_S = 5.0


async def sealed_log(gateway: Gateway, tenant: Tenant, call: str) -> list[JsonObject]:
    """The call's durable entries, once the gateway has sealed it."""
    deadline = time.monotonic() + SEALED_WITHIN_S
    while True:
        answer = await gateway.http.get(f"/v1/calls/{call}/events", params={"durable": True}, headers=tenant.server)
        page = answer.json()
        if not page["live"]:
            return list(page["entries"])
        kinds = [entry["type"] for entry in page["entries"]]
        assert time.monotonic() < deadline, f"call {call} was never sealed; its log holds {kinds}"
        await asyncio.sleep(0.05)


@pytest.fixture
def agent() -> str:
    """A slug of this test alone: a slug is one org's, and tests of other orgs run beside it."""
    return f"agent-{secrets.token_hex(4)}"


@needs_the_services
async def test_a_written_call_is_answered_sealed_and_metered(
    gateway: Gateway, tenant: Tenant, agent: str, sessions: async_sessionmaker[AsyncSession]
) -> None:
    """Two lines answered by the model, the call ended by the caller, its log sealed with its cost."""
    async with holding(gateway, tenant, agent), gateway.socket(f"/v1/chat?agent={agent}", tenant.server) as chat:
        call = str((await received(chat, "call.started"))["call"])
        for line in ("quiero un turno", "el martes por la mañana"):
            await chat.send(json.dumps({"text": line}))
            assert (await received(chat, "turn.user"))["data"]["text"] == line
            assert (await received(chat, "turn.agent"))["data"]["text"] == acme.HEARD.format(said=line)
    entries = await sealed_log(gateway, tenant, call)
    kinds = [str(entry["type"]) for entry in entries]
    assert kinds[0] == "call.started"
    assert kinds.count("turn.user") == 2
    assert "call.ended" in kinds
    summary = next(entry["data"] for entry in entries if entry["type"] == "call.summary")
    assert summary["reason"] == "caller_hung_up"
    # Priced per million tokens, as the catalog's rates are: 1.00 in and 2.00 out, every reply alike.
    replies = kinds.count("turn.agent")
    spent = replies * (acme.PROMPT_TOKENS * 1.0 + acme.COMPLETION_TOKENS * 2.0) / 1_000_000
    assert summary["cost"]["usd"] == pytest.approx(spent)
    # The seal counts the call into its day's drift; a fold that breaks is only logged, so it is asked here.
    async with sessions() as session:
        counted = await session.get(DriftCall, call)
    assert counted is not None and counted.env is Env.sandbox
