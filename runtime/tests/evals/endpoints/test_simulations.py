"""A simulation through the gateway: the agent's and the library's personas, who plays a run, what refuses it."""

import asyncio
import json
import time
from collections.abc import Callable
from functools import partial
from typing import Any

import httpx
import pytest
from sqlalchemy import select
from sqlalchemy.exc import TimeoutError as PoolTimeout
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from runtime.actor import Scope
from runtime.billing import service as billing
from runtime.billing.service import quotas
from runtime.enums import Env
from runtime.evals.models import CallerJob
from runtime.evals.parts import Harness
from runtime.evals.repository import CallerJobRepository, ComparisonRepository
from runtime.evals.service import caller_jobs, placing, plans, simulated_calls
from runtime.evals.service.callers import Improvised
from runtime.evals.service.simulated_calls import Simulation
from runtime.evals.tasks import LEFT_AFTER_S, Callers
from runtime.exceptions import ServiceUnavailable
from runtime.postgres import when_free
from tests.conftest import Gateway, Tenant, holding, needs_the_services, until, used_of
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


# A call's end is written before its summary, which carries how it ended in words: the row says the
# one a moment before the other, and a reader that asked between the two read an end with no reason.
async def summarized(gateway: Gateway, tenant: Tenant, call: str) -> dict[str, object]:
    """The simulated call's row, once it ended and its summary says why."""
    run: dict[str, object] = {}
    for _ in range(200):
        run = await ended(gateway, tenant, call)
        if run.get("outcome") is not None:
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
        run = await summarized(gateway, tenant, str(placed_one.json()["call"]))
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


# ── a spoken call's caller is a job a process claims ──


async def a_spoken_call(gateway: Gateway, tenant: Tenant, agent: str) -> str:
    body = {"agent": agent, "persona": "in-a-hurry", "voice": True, "turns": 1}
    placed_one = await gateway.http.post("/v1/simulations", json=body, headers=tenant.server)
    assert placed_one.status_code == 200, placed_one.text
    return str(placed_one.json()["call"])


async def on_the_line(gateway: Gateway, tenant: Tenant) -> int:
    limits = await gateway.http.get("/v1/simulations/limits", headers=tenant.server)
    return int(limits.json()["on_the_line"])


async def job_of(sessions: async_sessionmaker[AsyncSession], call: str) -> CallerJob:
    async with sessions.begin() as session:
        found = await CallerJobRepository(session).find(call)
    assert found is not None, "a spoken simulation is its caller's row from the moment it is placed"
    return found


# 2026-11-25: the caller of a spoken simulation was a task of the gateway that took the request, with
# every other caller and everything else that gateway does: nineteen at once were late with their
# frames, and a release ended them all. The gateway writes the caller's row and plays nothing: the row
# is the call's place on its org's line, and whichever process claims it plays it as it was placed.
@needs_the_services
@pytest.mark.usefixtures("the_callers_to_itself")
async def test_a_spoken_simulation_is_placed_as_its_callers_row_and_played_by_the_process_that_claims_it(
    gateway: Gateway, tenant: Tenant, agent: str, sessions: async_sessionmaker[AsyncSession]
) -> None:
    played: list[tuple[str, Simulation]] = []

    async def play(job: CallerJob, process: str) -> None:
        played.append((process, caller_jobs.load(job)))

    async with holding(gateway, tenant, agent):
        call = await a_spoken_call(gateway, tenant, agent)
        placed_as = await job_of(sessions, call)
        assert (placed_as.org, placed_as.agent, placed_as.claimed_by, placed_as.ended_at) == (
            tenant.org,
            agent,
            None,
            None,
        )
        assert await on_the_line(gateway, tenant) == 1
        # No gateway of the suite plays it: it waits until a process claims it.
        await asyncio.sleep(1.5)
        assert (await job_of(sessions, call)).claimed_by is None
        process = Callers(sessions, play, name="a callers process", at_once=3)
        await process.claim()
        await until(lambda: len(played) == 1)
        by, simulation = played[0]
        assert (by, simulation.call, simulation.agent, simulation.spoken) == ("a callers process", call, agent, True)
        assert (simulation.persona.name, simulation.turns, simulation.waits_for_slot) == ("in-a-hurry", 1, True)
        # The app that holds the agent is said on the row: the process that plays the caller serves none.
        assert simulation.held_by is not None and simulation.held_by.org == tenant.org
        await process.stop(0.0)


# What a process that plays callers leaves to a gateway is settled every two seconds by each of them:
# a test asks the suite's own gateway now, and the others' passes change nothing it waits for.
async def settled(gateway: Gateway) -> None:
    await caller_jobs.settle(gateway.state["harness"])


# A process that plays callers has no live side: it cannot end a call. One whose caller breaks before
# the call began says why on the row, and a gateway ends the call with that reason: the reader of the
# call is told what a gateway's own task told it until now.
@needs_the_services
@pytest.mark.usefixtures("the_callers_to_itself")
async def test_a_caller_its_process_could_not_play_ends_its_call_saying_why_and_gives_its_place_back(
    gateway: Gateway, tenant: Tenant, agent: str, sessions: async_sessionmaker[AsyncSession]
) -> None:
    parts: Harness = gateway.state["harness"]

    async def breaks(*_: object) -> None:
        raise ServiceUnavailable("the simulated call could not be held: no agent joined room in 110s")

    async with holding(gateway, tenant, agent):
        call = await a_spoken_call(gateway, tenant, agent)
        process = Callers(sessions, partial(caller_jobs.play_claimed, parts.playing), name="a process", at_once=1)
        with pytest.MonkeyPatch.context() as patched:
            patched.setattr(caller_jobs, "play_spoken", breaks)
            await process.claim()
            await process.stop(5.0)
        await settled(gateway)
        run = await summarized(gateway, tenant, call)
        assert run["end_reason"] == "error", run
        assert run["outcome"] == "the simulated call could not be held: no agent joined room in 110s"
        ended = await job_of(sessions, call)
        for _ in range(100):
            if ended.ended_at is not None:
                break
            await asyncio.sleep(0.05)
            ended = await job_of(sessions, call)
        assert ended.ended_at is not None and not ended.lost
        assert await on_the_line(gateway, tenant) == 0, "a job that is over holds no place on its org's line"


# A process that stops saying it plays a caller is gone, with the caller's leg. Before the call began,
# another process plays it whole, once; a second process gone, the call ends saying so.
@needs_the_services
@pytest.mark.usefixtures("the_callers_to_itself")
async def test_a_caller_whose_process_is_gone_is_another_ones_to_play_once_and_then_its_call_says_why(
    gateway: Gateway, tenant: Tenant, agent: str, sessions: async_sessionmaker[AsyncSession]
) -> None:
    async def gone(job: CallerJob, _process: str) -> None:
        # Taken, and never said again: long ago, as far as its row tells.
        async with sessions.begin() as session:
            found = await CallerJobRepository(session).find(job.call)
            assert found is not None
            found.heard_at = time.time() - 4 * LEFT_AFTER_S

    async def taken_up(done: Callable[[CallerJob], bool]) -> CallerJob:
        row = await job_of(sessions, call)
        for _ in range(100):
            if done(row):
                break
            await settled(gateway)
            await asyncio.sleep(0.05)
            row = await job_of(sessions, call)
        return row

    async with holding(gateway, tenant, agent):
        call = await a_spoken_call(gateway, tenant, agent)
        first = Callers(sessions, gone, name="gone first", at_once=1)
        await first.claim()
        await first.stop(5.0)
        left = await taken_up(lambda row: row.claimed_by is None)
        assert (left.claimed_by, left.ended_at, left.played) == (None, None, 1)
        second = Callers(sessions, gone, name="gone second", at_once=1)
        await second.claim()
        await second.stop(5.0)
        ended = await taken_up(lambda row: row.ended_at is not None)
        assert ended.ended_at is not None and ended.lost and ended.played == 2
        run = await summarized(gateway, tenant, call)
        assert run["end_reason"] == "error", run
        assert "stopped before the call began, twice" in str(run["outcome"])


# A comparison counts a call for each pair it was asked for. One whose caller's process left it on the
# line is over and stands for nothing: it leaves the table and is placed again, and the table still
# says every call asked for, once.
@needs_the_services
@pytest.mark.usefixtures("the_callers_to_itself")
async def test_a_comparisons_call_its_process_left_is_placed_again_and_the_table_counts_each_call_once(
    gateway: Gateway,
    tenant: Tenant,
    agent: str,
    sessions: async_sessionmaker[AsyncSession],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    quickly(monkeypatch)
    # The two that stand are ended here by a process that cannot play them, which is no call that counts:
    # placed again they would wait for a process this test has not. Their places are refused instead.
    monkeypatch.setattr(plans, "PLACED_AGAIN_AT_MOST", 0)
    against: list[dict[str, object]] = [{"llm": "acme/acme-1"}, {"temperature": 0.2}]
    body = {"agent": agent, "persona": "in-a-hurry", "voice": True, "turns": 1, "against": against}

    # Read as the person who asked for it: a spoken call is claimed in the scope of whoever placed it.
    async def table() -> dict[str, Any]:
        read = await gateway.http.get(f"/v1/simulations/compare/{started['comparison']}", headers=tenant.person)
        return dict(read.json())

    async def breaks(job: CallerJob, process: str) -> None:
        async with sessions.begin() as session:
            await CallerJobRepository(session).say_broke(job.call, process, "nobody plays in a test")

    async def jobs_of_comparison() -> list[CallerJob]:
        placed_in = select(CallerJob).where(CallerJob.comparison == started["comparison"])
        async with sessions.begin() as session:
            return list((await session.execute(placed_in)).scalars())

    async with holding(gateway, tenant, agent):
        answer = await gateway.http.post("/v1/simulations/compare", json=body, headers=tenant.person)
        assert answer.status_code == 200, answer.text
        started = answer.json()
        both = sorted(str(one["call"]) for one in started["calls"])
        assert len(both) == 2
        # One of the two is left on the line by its process: its job is over, and its row says lost.
        async with sessions.begin() as session:
            taken = await CallerJobRepository(session).claim("a process", time.time())
            assert taken is not None
            lost = taken.call
            taken.ended_at, taken.lost = time.time(), True
        (other,) = [call for call in both if call != lost]
        # It is placed again: a third call, for the pair the lost one stood for.
        replacement = ""
        for _ in range(100):
            new = [job.call for job in await jobs_of_comparison() if job.call not in both and job.document]
            if new:
                replacement = new[0]
                break
            await asyncio.sleep(0.05)
        assert replacement, "the call its process left is placed again"
        # The two that stand are played to an end, here by a process that says it cannot play them.
        process = Callers(sessions, breaks, name="a process", at_once=2)
        await process.claim()
        await process.stop(5.0)
        read: dict[str, Any] = {}
        for _ in range(100):
            await settled(gateway)
            read = await table()
            if read["waiting"] == 0 and len(read["rows"]) == 2 and all(row["ended_at"] for row in read["rows"]):
                break
            await asyncio.sleep(0.05)
        # The lost one is no row of the table: the two that stand for the two pairs asked for are.
        assert sorted(str(row["call"]) for row in read["rows"]) == sorted([other, replacement])
        assert (await jobs_of_comparison()) and all(job.ended_at for job in await jobs_of_comparison())
        placed_on = sorted(json.dumps(row["against"], sort_keys=True) for row in read["rows"])
        assert placed_on == sorted(json.dumps(values, sort_keys=True) for values in against)
        assert (read["planned"], int(read["waiting"])) == (2, 0)


# ── a comparison's call that did not count ──


def quickly(monkeypatch: pytest.MonkeyPatch) -> None:
    """A comparison's passes, seconds apart on a server, cut to what a test can wait."""
    monkeypatch.setattr(placing, "STILL_PLACING_EVERY_S", 0.1)
    monkeypatch.setattr(placing, "A_LINE_IS_READ_EVERY_S", 0.05)
    monkeypatch.setattr(placing, "SWEPT_EVERY_S", 0.05)


# The suite's vendor plays no caller (it answers no tool), so a caller that does not break hangs up
# with its first line: a call that began, ended by its caller, with nothing on its log to discount it.
def breaking(times: int | None) -> Callable[..., Any]:
    """The caller's next line: broken the first so many times it is asked for, or always; then a hang-up."""
    broke = 0

    async def improvise(*_: object) -> Improvised:
        nonlocal broke
        if times is None or broke < times:
            broke += 1
            raise RuntimeError("the caller's model answered nothing a line can be read from")
        return Improvised(say="", hangup=True)

    return improvise


async def compared(gateway: Gateway, tenant: Tenant, comparison: str, ended: Callable[[dict[str, Any]], bool]) -> Any:
    """The comparison's table, read until it says what the test waits for."""
    table: dict[str, Any] = {}
    for _ in range(160):
        read = await gateway.http.get(f"/v1/simulations/compare/{comparison}", headers=tenant.person)
        table = dict(read.json())
        if ended(table):
            break
        await asyncio.sleep(0.05)
    return table


# 2026-11-26, cmp_cd80e04794c7: nineteen of 140 calls did not count and the table ended at 121; the
# fourteen a vendor refused were placed again by hand, in two more comparisons.
@needs_the_services
@pytest.mark.timeout(30)
async def test_a_comparisons_call_that_did_not_count_is_placed_again_and_the_table_ends_with_what_it_planned(
    gateway: Gateway,
    tenant: Tenant,
    agent: str,
    sessions: async_sessionmaker[AsyncSession],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    quickly(monkeypatch)
    monkeypatch.setattr(simulated_calls, "improvise_line", breaking(1))
    against: list[dict[str, object]] = [{"llm": "acme/acme-1"}, {"temperature": 0.2}]
    body = {"agent": agent, "persona": "in-a-hurry", "voice": False, "turns": 1, "against": against}
    async with holding(gateway, tenant, agent):
        answer = await gateway.http.post("/v1/simulations/compare", json=body, headers=tenant.person)
        assert answer.status_code == 200, answer.text
        comparison = str(answer.json()["comparison"])
        table = await compared(gateway, tenant, comparison, lambda read: read["playing"] is False)
        rows: list[dict[str, Any]] = table["rows"]
        # The call whose caller broke stays a row, marked; another was placed in its stead.
        assert sorted(row["valid"] for row in rows) == [False, True, True]
        (broke,) = [row for row in rows if not row["valid"]]
        assert broke["invalid"]["kind"] == "platform"
        counted = [row for row in rows if row["valid"]]
        placed_on = sorted(json.dumps(row["against"], sort_keys=True) for row in counted)
        assert placed_on == sorted(json.dumps(values, sort_keys=True) for values in against)
        assert (table["planned"], table["waiting"], table["refused"], table["stopped"]) == (2, 0, [], [])
        # Another gateway that takes the comparison up finds every place stood for: it places nothing.
        async with sessions.begin() as session:
            kept = await ComparisonRepository(session).find(tenant.org, Env.sandbox, comparison)
            assert kept is not None
            plan = plans.read_plan(kept, Scope(tenant.org, Env.sandbox))
        assert [(one.call, one.placed_again) for one in plan.uncounted] == [(broke["call"], True)]
        await placing.take_up(gateway.state["harness"], plan, time.time())
        again = await compared(gateway, tenant, comparison, lambda read: read["playing"] is False)
        assert sorted(row["call"] for row in again["rows"]) == sorted(row["call"] for row in rows)
        assert (again["waiting"], again["refused"]) == (0, [])


@needs_the_services
@pytest.mark.timeout(30)
async def test_a_place_whose_calls_never_count_is_refused_once_it_was_placed_again_as_often_as_it_may_be(
    gateway: Gateway, tenant: Tenant, agent: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    quickly(monkeypatch)
    # Once more for each call planned, where a server places twice: a test waits for every call's end.
    monkeypatch.setattr(plans, "PLACED_AGAIN_AT_MOST", 1)
    monkeypatch.setattr(simulated_calls, "improvise_line", breaking(None))
    against: list[dict[str, object]] = [{"llm": "acme/acme-1"}, {"temperature": 0.2}]
    body = {"agent": agent, "persona": "in-a-hurry", "voice": False, "turns": 1, "against": against}
    async with holding(gateway, tenant, agent):
        answer = await gateway.http.post("/v1/simulations/compare", json=body, headers=tenant.person)
        assert answer.status_code == 200, answer.text
        comparison = str(answer.json()["comparison"])
        table = await compared(gateway, tenant, comparison, lambda read: read["playing"] is False)
        rows: list[dict[str, Any]] = table["rows"]
        # Each of the two places: the call asked for and one more, neither of which counted.
        assert len(rows) == 4 and not any(row["valid"] for row in rows)
        refused: list[dict[str, Any]] = table["refused"]
        assert sorted(json.dumps(one["against"], sort_keys=True) for one in refused) == sorted(
            json.dumps(values, sort_keys=True) for values in against
        )
        assert all("counted, 1 placed again among them" in str(one["why"]) for one in refused)
        assert (table["planned"], table["waiting"]) == (2, 0)
