"""A simulation through the gateway: the agent's and the library's personas, who plays a run, what refuses it."""

import asyncio

import httpx
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from runtime.billing import service as billing
from runtime.billing.service import quotas
from runtime.enums import Env
from tests.conftest import Gateway, Tenant, holding, needs_the_services, used_of
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
