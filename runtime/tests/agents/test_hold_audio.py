"""The hold melody's doors: what plays, after how long, kept apart, what a worker reads of both, and the class's own."""

import hashlib
import json
import struct

from pinecall_runtime.enums import Env, HoldPlayed
from pinecall_runtime.jobs.service.client import GatewayClient
from pinecall_runtime.kit.auth import Scope
from tests.conftest import Gateway, Tenant, holding, needs_the_services, received

pytestmark = needs_the_services


async def test_an_agent_nobody_chose_for_plays_the_runtimes_melody_after_the_runtimes_wait(
    gateway: Gateway, tenant: Tenant, agent: str
) -> None:
    async with holding(gateway, tenant, agent):
        read = await gateway.http.get(f"/v1/agents/{agent}/pipeline/hold-audio", headers=tenant.person)
    assert read.status_code == 200, read.text
    assert read.json() == {
        "played": "default",
        "sha256": None,
        "source_sha256": None,
        "seconds": None,
        "name": None,
        "after_s": 2.5,
        "fixed": False,
    }


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


# Two seconds of silence, 8 kHz mono 16-bit: the smallest file the converter takes.
def a_wav() -> bytes:
    samples = b"\x00\x00" * 16_000
    header = struct.pack(
        "<4sI4s4sIHHIIHH4sI",
        b"RIFF",
        36 + len(samples),
        b"WAVE",
        b"fmt ",
        16,
        1,
        1,
        8000,
        16000,
        2,
        16,
        b"data",
        len(samples),
    )
    return header + samples


async def declared(app: object, agent: str, hold: dict[str, object]) -> None:
    from websockets.asyncio.client import ClientConnection

    assert isinstance(app, ClientConnection)
    await app.send(
        json.dumps({"type": "agent.configure", "agent": agent, "call": None, "data": {"config": {"hold": hold}}})
    )
    await received(app, "agent.configured")


async def test_a_class_that_declares_its_melody_sets_the_wait_and_silence_and_the_doors_write_nothing(
    gateway: Gateway, tenant: Tenant, agent: str, fleet: GatewayClient
) -> None:
    """The class's wait and its silence win and are read by the worker; a PUT of either is 409 naming the class."""
    door = f"/v1/agents/{agent}/pipeline/hold-audio"
    async with holding(gateway, tenant, agent) as app:
        await declared(app, agent, {"after_s": 1.0, "off": True})
        read = await gateway.http.get(door, headers=tenant.person)
        heard = await fleet.hold_audio(agent, Scope(tenant.org, Env.sandbox, ""))
        waited = await gateway.http.put(f"{door}/after", json={"after_s": 0.8}, headers=tenant.person)
        chosen = await gateway.http.put(f"{door}/played", json={"played": "default"}, headers=tenant.person)
        uploaded = await gateway.http.put(door, content=a_wav(), headers=tenant.person)
        shipped = await gateway.http.put(f"/v1/agents/{agent}/hold-audio", content=a_wav(), headers=tenant.server)
    assert (read.json()["played"], read.json()["after_s"], read.json()["fixed"]) == ("off", 1.0, True)
    assert (heard.played, heard.after_s) == (HoldPlayed.off, 1.0)
    for refused in (waited, chosen, uploaded):
        assert refused.status_code == 409, refused.text
        assert refused.json()["detail"].startswith(f"hold set by the class of {agent}")
    assert shipped.status_code == 409 and "the file its class declares" in shipped.json()["detail"]


async def test_the_clip_a_class_ships_comes_through_the_door_by_its_hash_and_no_other_file_does(
    gateway: Gateway, tenant: Tenant, agent: str
) -> None:
    """The class names its file's sha256; its process ships that file on the app's key, and any other is refused."""
    ships = f"/v1/agents/{agent}/hold-audio"
    melody = a_wav()
    source = hashlib.sha256(melody).hexdigest()
    async with holding(gateway, tenant, agent) as app:
        nothing_declared = await gateway.http.put(ships, content=melody, headers=tenant.server)
        await declared(app, agent, {"clip": source, "name": "espera.wav", "after_s": 0.5})
        landed = await gateway.http.put(f"{ships}?name=espera.wav", content=melody, headers=tenant.server)
        other = await gateway.http.put(ships, content=melody + b"\x00\x00", headers=tenant.server)
        read = await gateway.http.get(f"/v1/agents/{agent}/pipeline/hold-audio", headers=tenant.person)
    assert nothing_declared.status_code == 409
    assert landed.status_code == 200, landed.text
    assert (landed.json()["played"], landed.json()["source_sha256"], landed.json()["after_s"]) == (
        "custom",
        source,
        0.5,
    )
    assert other.status_code == 409
    assert read.json()["fixed"] is True and read.json()["name"] == "espera.wav"
