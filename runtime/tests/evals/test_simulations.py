"""A simulation plays the agent's and the library's personas, a run names who plays it, three at once per org."""

import asyncio

import httpx
import pytest
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from pinecall_runtime.billing import service as billing
from pinecall_runtime.enums import Env
from pinecall_runtime.evals.service.simulations import AT_ONCE, Simulations, TooManyAtOnce
from pinecall_runtime.kit.auth import Scope
from pinecall_runtime.redis import LocalSignal
from tests.conftest import Gateway, Tenant, holding, needs_the_services, until, used_of
from tests.fakes.acme import UNKNOWN

ACME = Scope("org_acme", Env.sandbox)
OTHER = Scope("org_other", Env.sandbox)


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
        await billing.set_quotas(session, tenant.org, Env.sandbox, billing.Quotas(simulations=0))
    async with holding(gateway, tenant, agent):
        for voice in (False, True):
            answer = await simulated(gateway, tenant, agent, {}, voice=voice)
            assert answer.status_code == 429
            assert "0 of its 0 simulations in the sandbox" in answer.text
        assert await used_of(gateway, tenant, "concurrent_calls") == 0
        assert await said_on_the_log(gateway, tenant, agent) == [("simulations", 0, 0)] * 2


# ── the calls on the line at once ──


async def waiting_on(ended: asyncio.Event) -> None:
    """A call that lasts until it is told to end."""
    await ended.wait()


async def test_a_call_counts_from_the_moment_it_is_admitted_until_it_ends() -> None:
    simulations = Simulations()
    ended = asyncio.Event()
    simulations.admit("call_1", ACME)
    assert simulations.on_the_line(ACME.org, ACME.env) == 1
    simulations.play("call_1", ACME, waiting_on(ended))
    assert simulations.on_the_line(ACME.org, ACME.env) == 1
    assert simulations.on_the_line(ACME.org, Env.production) == 0
    assert simulations.on_the_line(OTHER.org, OTHER.env) == 0
    ended.set()
    await until(lambda: simulations.on_the_line(ACME.org, ACME.env) == 0)
    await simulations.stop()


async def test_a_call_refused_after_it_was_admitted_gives_its_place_back() -> None:
    simulations = Simulations()
    simulations.admit("call_1", ACME)
    simulations.release("call_1")
    assert simulations.on_the_line(ACME.org, ACME.env) == 0
    async with simulations.admitted("call_2", ACME):
        assert simulations.on_the_line(ACME.org, ACME.env) == 1
    assert simulations.on_the_line(ACME.org, ACME.env) == 0
    await simulations.stop()


async def test_the_fourth_of_an_orgs_calls_in_an_env_is_refused_and_told_when_to_ask_again() -> None:
    simulations = Simulations()
    ended = asyncio.Event()
    for n in range(AT_ONCE):
        simulations.admit(f"call_{n}", ACME)
        simulations.play(f"call_{n}", ACME, waiting_on(ended))
    with pytest.raises(TooManyAtOnce, match="3 simulated calls on the line in sandbox") as refused:
        simulations.admit("call_4", ACME)
    assert refused.value.status == 429 and refused.value.retry_after_s is not None
    # Another org, and the org's other env, are not held to this org's calls.
    simulations.admit("call_5", OTHER)
    simulations.admit("call_6", Scope(ACME.org, Env.production))
    ended.set()
    await until(lambda: simulations.on_the_line(ACME.org, ACME.env) == 0)
    simulations.admit("call_7", ACME)
    await simulations.stop()


# Four requests at once on one gateway, each awaiting its database between the count and the
# call's start (2026-10-21: four placed in one burst were all answered 200).
async def test_a_burst_on_one_gateway_never_passes_the_ceiling() -> None:
    simulations = Simulations()
    ended = asyncio.Event()
    refused: list[str] = []

    async def placed(call: str) -> None:
        try:
            simulations.admit(call, ACME)
        except TooManyAtOnce:
            refused.append(call)
            return
        await asyncio.sleep(0.01)
        simulations.play(call, ACME, waiting_on(ended))

    await asyncio.gather(*(placed(f"call_{n}") for n in range(6)))
    assert len(refused) == 3
    assert simulations.on_the_line(ACME.org, ACME.env) == AT_ONCE
    ended.set()
    await until(lambda: simulations.on_the_line(ACME.org, ACME.env) == 0)
    await simulations.stop()


async def test_every_gateway_counts_the_calls_the_others_play() -> None:
    signal = LocalSignal()
    here, there = Simulations(signal), Simulations(signal)
    await here.start()
    await there.start()
    ended = asyncio.Event()
    try:
        # The listeners subscribe on their first turn; a count said before it is said again each beat.
        await asyncio.sleep(0)
        for call in ("call_1", "call_2"):
            here.admit(call, ACME)
            here.play(call, ACME, waiting_on(ended))
        await until(lambda: there.on_the_line(ACME.org, ACME.env) == 2)
        there.admit("call_3", ACME)
        there.play("call_3", ACME, waiting_on(ended))
        await until(lambda: here.on_the_line(ACME.org, ACME.env) == 3)
        with pytest.raises(TooManyAtOnce):
            there.admit("call_4", ACME)
        ended.set()
        await until(lambda: here.on_the_line(ACME.org, ACME.env) == 0)
    finally:
        await here.stop()
        await there.stop()
