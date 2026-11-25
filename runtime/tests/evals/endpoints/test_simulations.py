"""A simulation through the gateway: the agent's and the library's personas, who plays a run, what refuses it."""

import asyncio
from functools import partial

import httpx
import pytest
from sqlalchemy.exc import TimeoutError as PoolTimeout
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from runtime.billing import service as billing
from runtime.billing.service import quotas
from runtime.enums import Env
from runtime.evals.service import placing, simulated_calls
from runtime.postgres import when_free
from tests.conftest import Gateway, Tenant, holding, needs_the_services, used_of
from tests.fakes import talker
from tests.fakes.acme import UNKNOWN


def voice_call(persona: str, agent: str) -> dict[str, object]:
    return {
        "call": "call_voicepersona",
        "agent": agent,
        "persona": {"name": persona, "goal": "Leave a message.", "style": "Brief."},
        "turns": 1,
    }


async def placed(gateway: Gateway, tenant: Tenant, persona: str, agent: str) -> httpx.Response:
    return await gateway.http.post("/v1/evals/voice", json=voice_call(persona, agent), headers=tenant.server)


async def test_a_library_persona_is_played_on_a_spoken_line_as_on_a_written_one(
    gateway: Gateway, tenant: Tenant, agent: str
) -> None:
    """Pinecall's own caller is refused only for what is missing: nobody holds the agent."""
    answer = await placed(gateway, tenant, "elderly-slow", agent)
    assert answer.status_code == 404
    assert "no app holds agent" in answer.text


async def test_a_persona_nobody_wrote_is_refused_by_its_name(gateway: Gateway, tenant: Tenant, agent: str) -> None:
    """A name that is neither the agent's nor the library's is the refusal it always was."""
    answer = await placed(gateway, tenant, "nobody-wrote-me", agent)
    assert answer.status_code == 404
    assert "no persona called nobody-wrote-me" in answer.text


async def simulated(
    gateway: Gateway, tenant: Tenant, agent: str, played_by: dict[str, str], *, voice: bool = False
) -> httpx.Response:
    body = {"agent": agent, "persona": "in-a-hurry", "voice": voice, "turns": 1, "played_by": played_by}
    return await gateway.http.post("/v1/simulations", json=body, headers=tenant.server)


async def test_a_run_played_on_a_vendor_this_box_lacks_is_refused_before_it_starts(
    gateway: Gateway, tenant: Tenant, agent: str
) -> None:
    """The run's own model and voice are checked as a persona's are when written: before the answer."""
    answer = await simulated(gateway, tenant, agent, {"tts": "nonvendor"})
    assert answer.status_code == 400
    assert "no vendor named 'nonvendor'" in answer.text


@needs_the_services
async def test_a_persona_whose_model_the_vendor_lacks_is_refused_before_a_call_opens_or_is_counted(
    gateway: Gateway, tenant: Tenant, agent: str
) -> None:
    """P F11: the vendor's no came as a 500 once the call had opened, and the call counted as a simulation."""
    async with holding(gateway, tenant, agent):
        answer = await simulated(gateway, tenant, agent, {"llm": f"acme/{UNKNOWN}"})
        assert answer.status_code == 400
        assert "acme refused the caller's model: no such model" in answer.text
        assert await used_of(gateway, tenant, "concurrent_calls") == 0
    assert await used_of(gateway, tenant, "simulations") == 0


async def test_a_run_that_names_nobody_new_is_played_as_the_persona_is(
    gateway: Gateway, tenant: Tenant, agent: str
) -> None:
    """An empty played_by changes nothing: the refusal is the one any simulation gets, nobody holding the agent."""
    answer = await simulated(gateway, tenant, agent, {})
    assert answer.status_code == 404
    assert "no app holds agent" in answer.text


async def test_a_spoken_call_whose_caller_names_a_vendor_this_box_lacks_is_refused_as_one(
    gateway: Gateway, tenant: Tenant, agent: str
) -> None:
    """The persona sent whole is checked as a written one is, never tried as some vendor's model."""
    call = {**voice_call("", agent), "persona": {"goal": "Leave a message.", "style": "Brief.", "tts": "nonvendor"}}
    answer = await gateway.http.post("/v1/evals/voice", json=call, headers=tenant.server)
    assert answer.status_code == 400
    assert "no vendor named 'nonvendor'" in answer.text


# ── what refuses a simulation is asked before its call opens ──


async def said_on_the_log(gateway: Gateway, tenant: Tenant, agent: str) -> list[tuple[str, float, int]]:
    """The credits.exhausted entries of the agent's own log: quota, used, limit."""
    answer = await gateway.http.get(
        f"/v1/agents/{agent}/calls", headers={**tenant.server, "accept": "application/json"}
    )
    said = [entry["data"] for entry in answer.json()["entries"] if entry["type"] == "credits.exhausted"]
    return [(one["quota"], one["used"], one["limit"]) for one in said]


@needs_the_services
async def test_a_run_whose_caller_is_on_a_vendor_nobody_keyed_is_refused_before_a_call_opens_or_is_counted(
    gateway: Gateway, tenant: Tenant, agent: str
) -> None:
    """F F3 and F F4: the 503 was heard after the call was opened, which nobody hung up, and counted."""
    async with holding(gateway, tenant, agent):
        for voice in (False, True):
            answer = await simulated(gateway, tenant, agent, {"llm": "openai/gpt-5.4-mini"}, voice=voice)
            assert answer.status_code == 503
            assert "openai has no key: the org brought none and the box holds none" in answer.text
        assert await used_of(gateway, tenant, "concurrent_calls") == 0
    assert await used_of(gateway, tenant, "simulations") == 0


@needs_the_services
async def test_a_spoken_caller_whose_voice_is_on_a_vendor_nobody_keyed_is_refused_before_its_call_is_claimed(
    gateway: Gateway, tenant: Tenant, agent: str
) -> None:
    async with holding(gateway, tenant, agent):
        answer = await simulated(gateway, tenant, agent, {"tts": "openai"}, voice=True)
    assert answer.status_code == 503
    assert "openai has no key" in answer.text


# ── a caller that rings by phone, and the network its packets cross ──


async def test_a_written_call_is_refused_a_phone_line(gateway: Gateway, tenant: Tenant, agent: str) -> None:
    """Nothing rings on a written call: asked to reach the agent by phone, it is refused in a sentence."""
    body = {"agent": agent, "persona": "in-a-hurry", "voice": False, "turns": 1, "via": "sip"}
    answer = await gateway.http.post("/v1/simulations", json=body, headers=tenant.server)
    assert answer.status_code == 400
    assert "a written call rings nobody" in answer.text


async def test_a_network_no_call_could_cross_is_refused_by_its_bounds(
    gateway: Gateway, tenant: Tenant, agent: str
) -> None:
    """A delay past two seconds, a jitter past half of one and a rate under the line's own signalling are no network."""
    for shape in ({"delay_ms": 2001}, {"jitter_ms": 501}, {"rate_kbps": 7}, {"via": "pstn"}):
        body = {"agent": agent, "persona": "in-a-hurry", "voice": True, "turns": 1, **shape}
        answer = await gateway.http.post("/v1/simulations", json=body, headers=tenant.server)
        assert answer.status_code == 422, (shape, answer.text)


# The suites' box has one LiveKit for both envs, as a box of one machine does: no SIP of its own admits
# a leg dialled from the other.
@needs_the_services
async def test_a_ring_this_boxs_sip_would_not_admit_is_refused_before_a_call_is_claimed_or_counted(
    gateway: Gateway, tenant: Tenant, agent: str
) -> None:
    body = {"agent": agent, "persona": "in-a-hurry", "voice": True, "turns": 1, "via": "sip"}
    async with holding(gateway, tenant, agent):
        answer = await gateway.http.post("/v1/simulations", json=body, headers=tenant.server)
        assert answer.status_code == 503, answer.text
        assert "rings by phone in the sandbox alone" in answer.text
        assert await used_of(gateway, tenant, "concurrent_calls") == 0
    assert await used_of(gateway, tenant, "simulations") == 0


@needs_the_services
async def test_a_simulation_past_the_orgs_simulations_is_refused_before_it_opens_and_said_on_the_agents_log(
    sessions: async_sessionmaker[AsyncSession], gateway: Gateway, tenant: Tenant, agent: str
) -> None:
    """H F3 and H F6: written and spoken alike, past the limit nothing opens and the refusal is kept."""
    async with sessions.begin() as session:
        await quotas.put_quotas(session, tenant.org, Env.sandbox, billing.Quotas(simulations=0))
    async with holding(gateway, tenant, agent):
        for voice in (False, True):
            answer = await simulated(gateway, tenant, agent, {}, voice=voice)
            assert answer.status_code == 429
            assert "0 of its 0 simulations in the sandbox" in answer.text
        assert await used_of(gateway, tenant, "concurrent_calls") == 0
        assert await said_on_the_log(gateway, tenant, agent) == [("simulations", 0, 0)] * 2


@needs_the_services
async def test_a_comparison_places_each_persona_against_the_agent_under_each_values_and_reads_them_as_a_table(
    gateway: Gateway, tenant: Tenant, agent: str
) -> None:
    """Two callers by two values, four written calls at once under one id; the list and the table carry them."""
    against: list[dict[str, object]] = [{"llm": "acme/acme-1"}, {"temperature": 0.2}]
    personas = ["in-a-hurry", "asks-for-a-person"]
    body = {
        "agent": agent,
        "persona": personas[0],
        "more_personas": personas[1:],
        "voice": False,
        "turns": 1,
        "against": against,
    }
    async with holding(gateway, tenant, agent):
        answer = await gateway.http.post("/v1/simulations/compare", json=body, headers=tenant.person)
        assert answer.status_code == 200, answer.text
        started = answer.json()
        assert started["comparison"].startswith("cmp_") and started["refused"] == [] and started["voice"] is False
        pairs = [(persona, values) for persona in personas for values in against]
        assert [(one["persona"], one["against"]) for one in started["calls"]] == pairs
        calls = [str(one["call"]) for one in started["calls"]]
        page: dict[str, object] = {}
        for _ in range(200):
            listed = await gateway.http.get(
                "/v1/simulations", params={"comparison": started["comparison"]}, headers=tenant.server
            )
            page = listed.json()
            if sorted(run["call"] for run in page["runs"]) == sorted(calls):  # type: ignore[index]
                break
            await asyncio.sleep(0.05)
        runs: list[dict[str, object]] = page["runs"]  # type: ignore[assignment]
        assert {run["call"]: run["against"] for run in runs} == {
            call: values for call, (_, values) in zip(calls, pairs, strict=True)
        }
        assert {run["comparison"] for run in runs} == {started["comparison"]}
        table = (
            await gateway.http.get(f"/v1/simulations/compare/{started['comparison']}", headers=tenant.server)
        ).json()
        assert (table["agent"], table["voice"], sorted(table["personas"])) == (agent, False, sorted(personas))
        assert {row["call"]: row["persona"] for row in table["rows"]} == {
            call: persona for call, (persona, _) in zip(calls, pairs, strict=True)
        }
        measures = {"e2e_latency", "llm_node_ttft", "tts_node_ttfb", "transcription_delay", "end_of_turn_delay"}
        assert all(set(row["latency"]) == measures for row in table["rows"])
    # A key that does not edit the pipeline is refused before anything opens; so is a knob no test room has.
    refused = await gateway.http.post("/v1/simulations/compare", json=body, headers=tenant.server)
    assert refused.status_code == 403 and "pipeline" in refused.text
    stray = await gateway.http.post("/v1/simulations", json={**body, "against": {"foo": "bar"}}, headers=tenant.person)
    assert stray.status_code == 422
    missing = await gateway.http.get("/v1/simulations/compare/cmp_nobody", headers=tenant.server)
    assert missing.status_code == 404
    # One call per pair, ten at most: six callers by two values is refused before anything is placed.
    many = {**body, "more_personas": ["a", "b", "c", "d", "e"]}
    too_many = await gateway.http.post("/v1/simulations/compare", json=many, headers=tenant.person)
    assert too_many.status_code == 400 and "10 calls at most" in too_many.text


async def listed_calls(gateway: Gateway, tenant: Tenant, calls: list[str]) -> list[dict[str, object]]:
    """The simulated calls' rows, once the list carries every one of them."""
    runs: list[dict[str, object]] = []
    for _ in range(200):
        listed = await gateway.http.get("/v1/simulations", headers=tenant.server)
        runs = [run for run in listed.json()["runs"] if run["call"] in calls]
        if len(runs) == len(calls):
            break
        await asyncio.sleep(0.05)
    return runs


# 2026-11-25: a realtime model is a value of the run, as the pipeline's models are. It hears and speaks,
# so a written call asked for on it is refused before it is placed; whose key it runs on is
# `providers.talking_of`'s, tested with it.
@needs_the_services
async def test_a_realtime_model_asked_of_a_written_call_is_refused_before_a_call_opens(
    gateway: Gateway, tenant: Tenant, agent: str
) -> None:
    talks = {"realtime": f"{talker.install()}/voice-3"}
    body = {"agent": agent, "persona": "in-a-hurry", "voice": False, "turns": 1}
    async with holding(gateway, tenant, agent):
        compared = await gateway.http.post(
            "/v1/simulations/compare", json={**body, "against": [talks]}, headers=tenant.person
        )
        assert compared.status_code == 400 and "runs a spoken call" in compared.text, compared.text
        one = await gateway.http.post("/v1/simulations", json={**body, "against": talks}, headers=tenant.person)
        assert one.status_code == 400 and "runs a spoken call" in one.text, one.text
        assert await used_of(gateway, tenant, "concurrent_calls") == 0
    assert await used_of(gateway, tenant, "simulations") == 0


async def test_a_simulated_call_is_placed_again_as_it_was_on_a_new_call(
    gateway: Gateway, tenant: Tenant, agent: str
) -> None:
    """The same caller on the same line about the same thing, under a call id of its own; and again from that one."""
    scenario = {"goal": "I want to move my appointment to Friday.", "facts": {"name": "Ana"}}
    body = {"agent": agent, "persona": "in-a-hurry", "voice": False, "turns": 1, "scenario": scenario}
    async with holding(gateway, tenant, agent):
        first = await gateway.http.post("/v1/simulations", json=body, headers=tenant.server)
        assert first.status_code == 200, first.text
        call = str(first.json()["call"])
        again = await gateway.http.post(f"/v1/simulations/{call}/again", headers=tenant.server)
        assert again.status_code == 200, again.text
        second = str(again.json()["call"])
        assert second != call and again.json()["voice"] is False
        # What the second was placed with is the first's: it is placed again in its turn.
        third = await gateway.http.post(f"/v1/simulations/{second}/again", headers=tenant.server)
        assert third.status_code == 200, third.text
        runs = await listed_calls(gateway, tenant, [call, second, str(third.json()["call"])])
        assert [(run["agent"], run["persona"], run["comparison"]) for run in runs] == [(agent, "in-a-hurry", None)] * 3


async def test_a_call_nobody_simulated_here_is_not_placed_again(gateway: Gateway, tenant: Tenant, agent: str) -> None:
    """An id that is no simulated call of the key's scope is refused by its name, and nothing is counted."""
    answer = await gateway.http.post("/v1/simulations/call_nobodysimulated/again", headers=tenant.server)
    assert answer.status_code == 404
    assert "no simulated call call_nobodysimulated here" in answer.text
    assert await used_of(gateway, tenant, "simulations") == 0


async def ended(gateway: Gateway, tenant: Tenant, call: str) -> dict[str, object]:
    """The simulated call's row, once the list says it ended."""
    run: dict[str, object] = {}
    for _ in range(200):
        runs = await listed_calls(gateway, tenant, [call])
        run = runs[0] if runs else {}
        if run.get("ended_at") is not None:
            break
        await asyncio.sleep(0.05)
    return run


# The row says a call ended as its end is written, a moment before the gateway lets go of the call.
async def is_off_the_line(gateway: Gateway, tenant: Tenant) -> bool:
    """Whether the org holds no call at once any more, within a few seconds."""
    for _ in range(100):
        if await used_of(gateway, tenant, "concurrent_calls") == 0:
            return True
        await asyncio.sleep(0.05)
    return False


# 2026-11-25: a simulated call is played by a task of the gateway that nobody awaits. One that broke
# before its call began (the database had no connection for it) was a warning in the gateway's log and
# a call left open for good: only a seat never got and a line that could not be held ended it.
async def test_a_simulated_call_whose_caller_breaks_before_the_call_begins_ends_saying_why(
    gateway: Gateway, tenant: Tenant, agent: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    async def breaks(*_: object) -> None:
        raise RuntimeError("select secret from vault")

    monkeypatch.setattr(simulated_calls, "stage_of_caller", breaks)
    body = {"agent": agent, "persona": "in-a-hurry", "voice": False, "turns": 1}
    async with holding(gateway, tenant, agent):
        placed_one = await gateway.http.post("/v1/simulations", json=body, headers=tenant.server)
        assert placed_one.status_code == 200, placed_one.text
        run = await ended(gateway, tenant, str(placed_one.json()["call"]))
        assert run["end_reason"] == "error", run
        # Named by its kind alone: what a fault of the gateway's says may carry a statement.
        assert run["outcome"] == "the gateway could not play this call's caller (RuntimeError): its log says why"
        assert await is_off_the_line(gateway, tenant), "the call it had opened holds none of the org's calls at once"


async def test_a_written_call_whose_caller_breaks_on_the_line_is_ended_whatever_broke_it(
    gateway: Gateway, tenant: Tenant, agent: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    async def breaks(*_: object) -> None:
        raise RuntimeError("the caller's model answered nothing a line can be read from")

    monkeypatch.setattr(simulated_calls, "improvise_line", breaks)
    body = {"agent": agent, "persona": "in-a-hurry", "voice": False, "turns": 1}
    async with holding(gateway, tenant, agent):
        placed_one = await gateway.http.post("/v1/simulations", json=body, headers=tenant.server)
        assert placed_one.status_code == 200, placed_one.text
        run = await ended(gateway, tenant, str(placed_one.json()["call"]))
        assert run["end_reason"] == "error", run
        assert await is_off_the_line(gateway, tenant)


# A written call is opened, on the org's line, before it is kept as placed: one that cannot be kept is
# refused to whoever asked and ended, where it would have stayed open with nobody to play it.
async def test_a_written_call_that_cannot_be_kept_as_placed_is_refused_and_ended(
    gateway: Gateway, tenant: Tenant, agent: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    async def breaks(*_: object) -> None:
        raise RuntimeError("the row could not be written")

    monkeypatch.setattr(simulated_calls, "keep_as_placed", breaks)
    body = {"agent": agent, "persona": "in-a-hurry", "voice": False, "turns": 1}
    async with holding(gateway, tenant, agent):
        refused = await gateway.http.post("/v1/simulations", json=body, headers=tenant.server)
        assert refused.status_code == 500, refused.text
        assert await is_off_the_line(gateway, tenant)


# 2026-11-25, cmp_bf669d1c4545: twenty calls planned, nineteen rows, none waiting, none refused, and a
# command waiting on the twentieth for good. Every call asked for is a row, a call that waits or a
# refusal with its reason: here the database never has a connection for one caller's calls.
@needs_the_services
async def test_a_comparisons_call_the_database_never_has_a_connection_for_is_a_refusal_its_table_says(
    gateway: Gateway, tenant: Tenant, agent: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    busy_for, placed_as_ever = "in-a-hurry", placing.place_simulation

    async def place(parts: object, actor: object, wanted: object, **how: object) -> object:
        if getattr(wanted, "persona", None) == busy_for:
            raise PoolTimeout("QueuePool limit of size 8 overflow 0 reached, connection timed out, timeout 2.00")
        return await placed_as_ever(parts, actor, wanted, **how)  # type: ignore[arg-type]

    monkeypatch.setattr(placing, "place_simulation", place)
    # The wait for a connection, twenty seconds, cut to what a test can wait.
    monkeypatch.setattr(placing, "when_free", partial(when_free, within_s=0.3))
    against: list[dict[str, object]] = [{"llm": "acme/acme-1"}, {"temperature": 0.2}]
    body = {
        "agent": agent,
        "persona": busy_for,
        "more_personas": ["asks-for-a-person"],
        "voice": False,
        "turns": 1,
        "against": against,
    }
    async with holding(gateway, tenant, agent):
        answer = await gateway.http.post("/v1/simulations/compare", json=body, headers=tenant.person)
        assert answer.status_code == 200, answer.text
        started = answer.json()
        # No connection for the first call: it waits its turn with the ones behind it, and nothing is refused yet.
        assert (started["calls"], started["refused"], started["waiting"]) == ([], [], 4)
        table: dict[str, object] = {}
        for _ in range(400):
            read = await gateway.http.get(f"/v1/simulations/compare/{started['comparison']}", headers=tenant.server)
            table = read.json()
            rows: list[dict[str, object]] = table["rows"]  # type: ignore[assignment]
            if table["waiting"] == 0 and len(rows) == 2 and all(row["ended_at"] is not None for row in rows):
                break
            await asyncio.sleep(0.05)
        refused: list[dict[str, object]] = table["refused"]  # type: ignore[assignment]
        assert [(one["persona"], one["against"]) for one in refused] == [(busy_for, values) for values in against]
        assert all("the database was busy: no connection came free" in str(one["why"]) for one in refused)
        rows = table["rows"]  # type: ignore[assignment]
        assert sorted(str(row["persona"]) for row in rows) == ["asks-for-a-person"] * 2
        assert table["planned"] == len(rows) + int(str(table["waiting"])) + len(refused) == 4
