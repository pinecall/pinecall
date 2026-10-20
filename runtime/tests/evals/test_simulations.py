"""A simulation plays the agent's own personas and the library's, and a run may name who plays the caller."""

import httpx

from tests.conftest import Gateway, Tenant


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
