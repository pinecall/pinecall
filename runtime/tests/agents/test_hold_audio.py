"""The hold melody's doors: what plays, after how long, kept apart, and what a worker reads of both."""

from pinecall_runtime.enums import Env, HoldPlayed
from pinecall_runtime.jobs.service.client import GatewayClient
from pinecall_runtime.kit.auth import Scope
from tests.conftest import Gateway, Tenant, holding, needs_the_services

pytestmark = needs_the_services


async def test_an_agent_nobody_chose_for_plays_the_runtimes_melody_after_the_runtimes_wait(
    gateway: Gateway, tenant: Tenant, agent: str
) -> None:
    async with holding(gateway, tenant, agent):
        read = await gateway.http.get(f"/v1/agents/{agent}/pipeline/hold-audio", headers=tenant.person)
    assert read.status_code == 200, read.text
    assert read.json() == {"played": "default", "sha256": None, "seconds": None, "name": None, "after_s": 2.5}


async def test_the_wait_is_kept_through_every_choice_of_what_plays_and_the_worker_reads_it(
    gateway: Gateway, tenant: Tenant, agent: str, fleet: GatewayClient
) -> None:
    door = f"/v1/agents/{agent}/pipeline/hold-audio"
    async with holding(gateway, tenant, agent):
        waited = await gateway.http.put(f"{door}/after", json={"after_s": 0.8}, headers=tenant.person)
        silenced = await gateway.http.put(f"{door}/played", json={"played": "off"}, headers=tenant.person)
        silent = await fleet.hold_audio(agent, Scope(tenant.org, Env.sandbox, ""))
        back = await gateway.http.put(f"{door}/played", json={"played": "default"}, headers=tenant.person)
        reset = await gateway.http.put(f"{door}/after", json={"after_s": None}, headers=tenant.person)
    assert waited.status_code == 200, waited.text
    assert waited.json()["played"] == "default" and waited.json()["after_s"] == 0.8
    assert silenced.json()["played"] == "off" and silenced.json()["after_s"] == 0.8
    assert silent.played is HoldPlayed.off and silent.after_s == 0.8
    assert back.json()["played"] == "default" and back.json()["after_s"] == 0.8
    assert reset.json()["played"] == "default" and reset.json()["after_s"] == 2.5


async def test_a_wait_out_of_range_is_refused_in_a_sentence_and_nothing_changes(
    gateway: Gateway, tenant: Tenant, agent: str
) -> None:
    door = f"/v1/agents/{agent}/pipeline/hold-audio"
    async with holding(gateway, tenant, agent):
        late = await gateway.http.put(f"{door}/after", json={"after_s": 31}, headers=tenant.person)
        early = await gateway.http.put(f"{door}/after", json={"after_s": -1}, headers=tenant.person)
        read = await gateway.http.get(door, headers=tenant.person)
    assert late.status_code == 400 and "0 to 30 seconds" in late.json()["detail"]
    assert early.status_code == 400
    assert read.json()["after_s"] == 2.5


async def test_a_person_hears_the_runtimes_melody_before_a_caller_does_and_nothing_when_it_is_off(
    gateway: Gateway, tenant: Tenant, agent: str
) -> None:
    door = f"/v1/agents/{agent}/pipeline/hold-audio"
    async with holding(gateway, tenant, agent):
        heard = await gateway.http.get(f"{door}/audio", headers=tenant.person)
        await gateway.http.put(f"{door}/played", json={"played": "off"}, headers=tenant.person)
        silent = await gateway.http.get(f"{door}/audio", headers=tenant.person)
    assert heard.status_code == 200 and heard.content[:4] == b"OggS"
    assert silent.status_code == 404 and "off" in silent.json()["detail"]
