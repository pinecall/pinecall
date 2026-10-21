"""A simulation plays the agent's and the library's personas, a run names who plays it, three at once per org."""

import asyncio

import httpx
import pytest

from pinecall_runtime.enums import Env
from pinecall_runtime.evals.service.simulations import AT_ONCE, Simulations, TooManyAtOnce, admit_one_more
from pinecall_runtime.kit.auth import Scope
from pinecall_runtime.redis import LocalSignal
from tests.conftest import Gateway, Tenant, until

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


async def simulated(gateway: Gateway, tenant: Tenant, agent: str, played_by: dict[str, str]) -> httpx.Response:
    body = {"agent": agent, "persona": "in-a-hurry", "voice": False, "turns": 1, "played_by": played_by}
    return await gateway.http.post("/v1/simulations", json=body, headers=tenant.server)


async def test_a_run_played_on_a_vendor_this_box_lacks_is_refused_before_it_starts(
    gateway: Gateway, tenant: Tenant, agent: str
) -> None:
    """The run's own model and voice are checked as a persona's are when written: before the answer."""
    answer = await simulated(gateway, tenant, agent, {"tts": "nonvendor"})
    assert answer.status_code == 400
    assert "no vendor named 'nonvendor'" in answer.text


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


# ── the calls on the line at once ──


async def waiting_on(ended: asyncio.Event) -> None:
    """A call that lasts until it is told to end."""
    await ended.wait()


async def test_a_call_counts_from_the_moment_it_is_placed_until_it_ends() -> None:
    simulations = Simulations()
    ended = asyncio.Event()
    simulations.play("call_1", ACME, waiting_on(ended))
    assert simulations.on_the_line(ACME.org, ACME.env) == 1
    assert simulations.on_the_line(ACME.org, Env.production) == 0
    assert simulations.on_the_line(OTHER.org, OTHER.env) == 0
    ended.set()
    await until(lambda: simulations.on_the_line(ACME.org, ACME.env) == 0)
    await simulations.stop()


async def test_a_call_played_by_the_request_itself_counts_for_as_long_as_it_plays() -> None:
    simulations = Simulations()
    async with simulations.holding("call_1", ACME):
        assert simulations.on_the_line(ACME.org, ACME.env) == 1
    assert simulations.on_the_line(ACME.org, ACME.env) == 0
    await simulations.stop()


async def test_the_fourth_of_an_orgs_calls_in_an_env_is_refused_and_told_when_to_ask_again() -> None:
    simulations = Simulations()
    ended = asyncio.Event()
    for n in range(AT_ONCE):
        admit_one_more(simulations, ACME)
        simulations.play(f"call_{n}", ACME, waiting_on(ended))
    with pytest.raises(TooManyAtOnce, match="3 simulated calls on the line in sandbox") as refused:
        admit_one_more(simulations, ACME)
    assert refused.value.status == 429 and refused.value.retry_after_s is not None
    # Another org, and the org's other env, are not held to this org's calls.
    admit_one_more(simulations, OTHER)
    admit_one_more(simulations, Scope(ACME.org, Env.production))
    ended.set()
    await until(lambda: simulations.on_the_line(ACME.org, ACME.env) == 0)
    admit_one_more(simulations, ACME)
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
        here.play("call_1", ACME, waiting_on(ended))
        here.play("call_2", ACME, waiting_on(ended))
        await until(lambda: there.on_the_line(ACME.org, ACME.env) == 2)
        there.play("call_3", ACME, waiting_on(ended))
        await until(lambda: here.on_the_line(ACME.org, ACME.env) == 3)
        with pytest.raises(TooManyAtOnce):
            admit_one_more(there, ACME)
        ended.set()
        await until(lambda: here.on_the_line(ACME.org, ACME.env) == 0)
    finally:
        await here.stop()
        await there.stop()
