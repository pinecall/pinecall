"""A written call end to end: an app holds the agent, a caller chats, the call is sealed and metered."""

import asyncio
import json
import secrets
import time
from datetime import UTC, datetime
from urllib.parse import quote

import pytest
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker
from websockets.exceptions import ConnectionClosed

from pinecall_runtime.billing import service as billing
from pinecall_runtime.calls.models.drift import DriftCall
from pinecall_runtime.enums import Env
from pinecall_runtime.kit.text import JsonObject
from tests.conftest import Gateway, Tenant, holding, needs_the_services, received, used_of
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


# ── a persona on the call: a simulation, admitted before the call opens ──

IN_A_HURRY = "&persona=in-a-hurry"


def played_by(who: dict[str, str]) -> str:
    return f"&played_by={quote(json.dumps(who))}"


async def refusal_of(gateway: Gateway, tenant: Tenant, path: str) -> tuple[int, str]:
    """The close code and the reason a chat that is refused is closed with."""
    async with gateway.socket(path, tenant.server) as chat:
        with pytest.raises(ConnectionClosed) as closed:
            await chat.recv()
    assert closed.value.rcvd is not None
    return closed.value.rcvd.code, closed.value.rcvd.reason


@needs_the_services
async def test_a_chat_whose_persona_is_played_on_a_vendor_nobody_keyed_is_refused_before_it_opens(
    gateway: Gateway, tenant: Tenant, agent: str
) -> None:
    """F F3 and F F4: the caller's model is asked at the door, so no call is left open and none is counted."""
    async with holding(gateway, tenant, agent):
        path = f"/v1/chat?agent={agent}{IN_A_HURRY}{played_by({'llm': 'openai/gpt-5.4-mini'})}"
        code, reason = await refusal_of(gateway, tenant, path)
        assert (code, reason.split(":")[0]) == (4503, "openai has no key")
        assert await used_of(gateway, tenant, "concurrent_calls") == 0
    assert await used_of(gateway, tenant, "simulations") == 0


@needs_the_services
async def test_a_chat_with_a_persona_past_the_orgs_simulations_is_refused_before_it_opens_and_said_on_the_log(
    sessions: async_sessionmaker[AsyncSession], gateway: Gateway, tenant: Tenant, agent: str
) -> None:
    """H F3 and H F6: the third simulation of a limit of two never opens, and the log of the agent says why."""
    async with sessions.begin() as session:
        await billing.set_quotas(session, tenant.org, Env.sandbox, billing.Quotas(simulations=0))
    async with holding(gateway, tenant, agent):
        code, reason = await refusal_of(gateway, tenant, f"/v1/chat?agent={agent}{IN_A_HURRY}")
        assert (code, "0 of its 0 simulations" in reason) == (4429, True)
        assert await used_of(gateway, tenant, "concurrent_calls") == 0
        answer = await gateway.http.get(
            f"/v1/agents/{agent}/calls", headers={**tenant.server, "accept": "application/json"}
        )
    said = [entry["data"]["quota"] for entry in answer.json()["entries"] if entry["type"] == "credits.exhausted"]
    assert said == ["simulations"]


@needs_the_services
async def test_a_chat_that_names_a_persona_nobody_wrote_is_refused_and_one_that_names_none_takes_no_run(
    gateway: Gateway, tenant: Tenant, agent: str
) -> None:
    async with holding(gateway, tenant, agent):
        code, reason = await refusal_of(gateway, tenant, f"/v1/chat?agent={agent}&persona=nobody-wrote-me")
        assert (code, "no persona called nobody-wrote-me" in reason) == (4404, True)
        code, reason = await refusal_of(gateway, tenant, f"/v1/chat?agent={agent}{played_by({'llm': 'acme/acme-1'})}")
        assert (code, "name it with ?persona=" in reason) == (4400, True)


@needs_the_services
async def test_the_model_that_plays_a_chats_persona_is_kept_with_the_call_for_its_run(
    gateway: Gateway, tenant: Tenant, agent: str
) -> None:
    """F F8: a written run named no player; the run's row said played_by null."""
    async with holding(gateway, tenant, agent):
        path = f"/v1/chat?agent={agent}{IN_A_HURRY}{played_by({'llm': 'acme/acme-1'})}"
        async with gateway.socket(path, tenant.server) as chat:
            call = str((await received(chat, "call.started"))["call"])
            runs: list[JsonObject] = []

            async def listed() -> bool:
                answer = await gateway.http.get(f"/v1/agents/{agent}/personas/in-a-hurry/runs", headers=tenant.server)
                runs[:] = answer.json()["runs"]
                return any(run["call"] == call for run in runs)

            for _ in range(100):
                if await listed():
                    break
                await asyncio.sleep(0.05)
    (run,) = [run for run in runs if run["call"] == call]
    assert run["played_by"] == {"llm": "acme/acme-1", "tts": None, "voice": None}


@needs_the_services
async def test_a_written_chat_spends_the_orgs_messages_and_none_of_its_minutes(
    gateway: Gateway, tenant: Tenant, agent: str, sessions: async_sessionmaker[AsyncSession]
) -> None:
    """J F9: minutes are what is spoken; a chat of a few seconds is turns, and the meter says so."""
    async with holding(gateway, tenant, agent), gateway.socket(f"/v1/chat?agent={agent}", tenant.server) as chat:
        call = str((await received(chat, "call.started"))["call"])
        await chat.send(json.dumps({"text": "quiero un turno"}))
        await received(chat, "turn.agent")
    await sealed_log(gateway, tenant, call)
    async with sessions() as session:
        used = await billing.get_usage(session, tenant.org, Env.sandbox, datetime.now(UTC).date())
    assert (used.calls, used.minutes, used.messages) == (1, 0.0, 1)


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


@needs_the_services
async def test_a_call_opened_as_a_contact_is_theirs_on_the_log_the_state_and_their_erasure(
    gateway: Gateway, tenant: Tenant, agent: str
) -> None:
    """`chat --as +1415…`: the contact is the caller of the entry and the state, and "delete my data" finds the call."""
    contact = "+14155550198"
    async with (
        holding(gateway, tenant, agent),
        gateway.socket(f"/v1/chat?agent={agent}&contact={quote(contact)}", tenant.server) as chat,
    ):
        started = await received(chat, "call.started")
        call = str(started["call"])
        assert started["data"]["caller"] == {"id": contact}
        assert str(started["data"]["from"]).startswith("web_")
        await chat.send(json.dumps({"text": "hola"}))
        await received(chat, "turn.agent")
    await sealed_log(gateway, tenant, call)
    read = (await gateway.http.get(f"/v1/calls/{call}/state", headers=tenant.server)).json()
    assert read["state"]["caller"] == {"id": contact}
    erased = await gateway.http.delete(f"/v1/contacts/{quote(contact)}", headers=tenant.person)
    assert erased.status_code == 200, erased.text
    assert erased.json()["calls"] == 1
    assert (await gateway.http.get(f"/v1/calls/{call}/state", headers=tenant.server)).status_code == 404
