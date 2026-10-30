"""A class that declares its hold melody names the file by its hash and ships it once registered."""

import hashlib
from pathlib import Path

import pytest

from pinecall import Agent, DeclarationRefused
from pinecall._melody import hold_config_of, upload_declared_hold
from pinecall.client import Client
from pinecall.wire._names import JsonObject

MELODY = b"RIFF\x01\x02\x03\x04"
SHA = hashlib.sha256(MELODY).hexdigest()


def beside(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    (tmp_path / "hold.mp3").write_bytes(MELODY)

    def folder(_cls: type) -> Path:
        return tmp_path

    monkeypatch.setattr("pinecall._melody.folder_of", folder)
    return tmp_path


def plays() -> type:
    return type(
        "Plays", (Agent,), {"hold": {"file": "hold.mp3", "after_s": 1.5}, "__doc__": "Plays."}
    )


def test_the_file_is_declared_by_its_hash_with_the_wait_and_silence_as_off(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    beside(tmp_path, monkeypatch)
    assert hold_config_of(plays()) == {"hold": {"after_s": 1.5, "clip": SHA, "name": "hold.mp3"}}
    quiet = type("Quiet", (Agent,), {"hold": "off", "__doc__": "Quiet."})
    assert hold_config_of(quiet) == {"hold": {"off": True}}
    assert hold_config_of(type("Silent", (Agent,), {"__doc__": "x"})) == {}
    gone = type("Gone", (Agent,), {"hold": {"file": "nowhere.mp3"}, "__doc__": "x"})
    with pytest.raises(DeclarationRefused, match="no such file beside the class"):
        hold_config_of(gone)
    with pytest.raises(DeclarationRefused, match="hold is the melody"):
        hold_config_of(type("Odd", (Agent,), {"hold": 3, "__doc__": "x"}))


async def test_the_file_is_shipped_once_registered_and_not_again_when_the_gateway_holds_it(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    beside(tmp_path, monkeypatch)
    held: JsonObject = {"played": "default", "after_s": 2.5, "source_sha256": None}
    shipped: list[tuple[str, bytes, str]] = []

    async def hold_audio(self: Client, agent: str) -> JsonObject:
        return held

    async def upload_hold_audio(self: Client, agent: str, data: bytes, name: str) -> JsonObject:
        shipped.append((agent, data, name))
        return {"played": "custom", "seconds": 41.2, "source_sha256": SHA}

    monkeypatch.setattr(Client, "hold_audio", hold_audio)
    monkeypatch.setattr(Client, "upload_hold_audio", upload_hold_audio)
    said: list[str] = []
    client = Client("https://gw", "pk_test", None)
    await upload_declared_hold(client, plays(), "plays", said.append)
    assert shipped == [("plays", MELODY, "hold.mp3")]
    assert said == ["hold.mp3 uploaded as the hold melody · 41.2 s"]
    held["source_sha256"] = SHA
    await upload_declared_hold(client, plays(), "plays", said.append)
    assert len(shipped) == 1
