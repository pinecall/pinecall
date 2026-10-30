"""The settings doors: a diff reads this person's corner or the team's; what the class fixed outlives the socket."""

import json

from tests.conftest import Gateway, Tenant, holding, needs_the_services, received
from tests.fakes import acme


# J F6 (2026-10-23): `agent diff` compared the person's own corner alone, so a team whose settings
# equalled production's was still shown a difference; `team=true` reads the team's.
@needs_the_services
async def test_a_diff_reads_the_persons_corner_unless_the_teams_is_asked_for(
    gateway: Gateway, tenant: Tenant, agent: str
) -> None:
    door = f"/v1/agents/{agent}/settings"
    async with holding(gateway, tenant, agent):
        team = await gateway.http.put(door, json={"config": {"language": "es-ES"}, "team": True}, headers=tenant.person)
        assert team.status_code == 200, team.text
        mine = await gateway.http.put(door, json={"config": {"language": "fr-FR"}}, headers=tenant.person)
        assert mine.status_code == 200, mine.text
        own = await gateway.http.get(f"{door}/diff", params={"against": "team"}, headers=tenant.person)
        assert own.status_code == 200, own.text
        assert "language" in own.json()["changed"]
        asked = {"against": "team", "team": "true"}
        teams = await gateway.http.get(f"{door}/diff", params=asked, headers=tenant.person)
        assert teams.status_code == 200, teams.text
        assert teams.json()["changed"] == []
        assert teams.json()["ours"]["config"]["language"] == "es-ES"


# R F16 (2026-10-24): `--judge-option foo=1` was kept with no trial while `--stt-option foo=1` was
# refused; a judge the vendor refuses fails every hang-up, so it is tried as the `--llm` pair is.
@needs_the_services
async def test_a_judge_option_its_vendor_refuses_is_refused_before_it_is_kept(
    gateway: Gateway, tenant: Tenant, agent: str
) -> None:
    door = f"/v1/agents/{agent}/settings"
    judge = f"{acme.ACME}/{acme.MODEL}"
    # Options and builds run on the org's own key alone.
    own = await gateway.http.put(f"/v1/provider-keys/{acme.ACME}", json={"key": "acme-good-key"}, headers=tenant.person)
    assert own.status_code == 204, own.text
    async with holding(gateway, tenant, agent):
        refused = await gateway.http.put(
            door, json={"config": {"judge": judge, "judge_options": {"nope": 1}}}, headers=tenant.person
        )
        assert refused.status_code == 400, refused.text
        assert f"{acme.ACME} refused the judge this sets" in refused.json()["detail"]
        kept = await gateway.http.put(door, json={"config": {"judge": judge}}, headers=tenant.person)
        assert kept.status_code == 200, kept.text


# R F14 (2026-10-24): the refusal carried `turn Turn(min_interruption_words=None, endpointing_ms=400, …)`.
@needs_the_services
async def test_a_turn_the_ears_refuse_is_named_by_the_knobs_typed(gateway: Gateway, tenant: Tenant, agent: str) -> None:
    own = await gateway.http.put(f"/v1/provider-keys/{acme.ACME}", json={"key": "acme-good-key"}, headers=tenant.person)
    assert own.status_code == 204, own.text
    async with holding(gateway, tenant, agent):
        refused = await gateway.http.put(
            f"/v1/agents/{agent}/settings", json={"config": {"turn": {"endpointing_ms": 50}}}, headers=tenant.person
        )
    assert refused.status_code == 400, refused.text
    assert "(turn endpointing_ms=50)" in refused.json()["detail"]
    assert "Turn(" not in refused.json()["detail"]


# What the class fixed outlives the socket: a settings screen opened with nobody holding the agent,
# and a gateway that restarted, still say what the class declared.
@needs_the_services
async def test_what_the_class_fixed_is_still_fixed_once_nobody_holds_the_agent(
    gateway: Gateway, tenant: Tenant, agent: str
) -> None:
    door = f"/v1/agents/{agent}/settings"
    async with holding(gateway, tenant, agent) as app:
        declared = {"config": {"language": "es-ES", "record": False}}
        await app.send(json.dumps({"type": "agent.configure", "agent": agent, "call": None, "data": declared}))
        await received(app, "agent.configured")
    held_by_nobody = await gateway.http.get(door, headers=tenant.person)
    assert held_by_nobody.status_code == 200, held_by_nobody.text
    assert held_by_nobody.json()["fixed"] == ["language", "record"]
    refused = await gateway.http.put(door, json={"config": {"language": "fr-FR"}}, headers=tenant.person)
    assert refused.status_code == 409, refused.text
    assert f"language set by the class of {agent}" in refused.json()["detail"]
