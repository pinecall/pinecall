"""The calibration door: a label is a verdict some judge of the agent's should have given, held or broken."""

import httpx

from tests.conftest import Gateway, Tenant, a_finished_call, holding, needs_the_services


async def labelled(gateway: Gateway, tenant: Tenant, call: str, judge: str, held: object) -> httpx.Response:
    return await gateway.http.post(
        "/v1/evals/calibration", json={"call": call, "judge": judge, "held": held}, headers=tenant.server
    )


async def judges_labelled(gateway: Gateway, tenant: Tenant, agent: str) -> list[str]:
    answer = await gateway.http.get("/v1/evals/calibration", params={"agent": agent}, headers=tenant.server)
    return [row["judge"] for row in answer.json()["judges"]]


@needs_the_services
async def test_a_label_for_a_judge_nobody_wrote_is_a_404_and_is_not_kept(
    gateway: Gateway, tenant: Tenant, agent: str
) -> None:
    """F F7: `no-such-judge labelled 1` stayed in the listing for ever, and no endpoint removes a label."""
    async with holding(gateway, tenant, agent):
        call = await a_finished_call(gateway, tenant, agent)
        refused = await labelled(gateway, tenant, call, "no-such-judge", True)
        assert refused.status_code == 404, refused.text
        assert f"{agent} has no judge called no-such-judge" in refused.json()["detail"]
        assert await judges_labelled(gateway, tenant, agent) == []


@needs_the_services
async def test_held_is_a_boolean_and_a_word_for_it_is_a_422(gateway: Gateway, tenant: Tenant, agent: str) -> None:
    async with holding(gateway, tenant, agent):
        call = await a_finished_call(gateway, tenant, agent)
        for held in ("yes", "true", 1, None):
            assert (await labelled(gateway, tenant, call, "consent", held)).status_code == 422
        assert await judges_labelled(gateway, tenant, agent) == []


@needs_the_services
async def test_a_judge_that_scores_or_chooses_takes_no_label_and_one_that_answers_a_verdict_does(
    gateway: Gateway, tenant: Tenant, agent: str
) -> None:
    async with holding(gateway, tenant, agent):
        call = await a_finished_call(gateway, tenant, agent)
        own = {"question": "How warm was the agent?", "answer": "score"}
        written = await gateway.http.put(f"/v1/agents/{agent}/judges/warmth", json=own, headers=tenant.server)
        assert written.status_code == 200, written.text
        refused = await labelled(gateway, tenant, call, "warmth", True)
        assert refused.status_code == 409, refused.text
        assert "warmth answers a score, not held or broken" in refused.json()["detail"]
        assert (await labelled(gateway, tenant, call, "consent", False)).status_code == 204
        assert await judges_labelled(gateway, tenant, agent) == ["consent"]
