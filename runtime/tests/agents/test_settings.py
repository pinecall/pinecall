"""The settings doors: a diff reads this person's corner, or the team's when asked."""

from tests.conftest import Gateway, Tenant, holding, needs_the_services


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
