"""The local runtime's files: the settings written once, and where the gateway listens on Linux."""

from pathlib import Path

import pytest

from pinecall_runtime.cli import local

LISTEN = "PINECALL_GATEWAY_LISTEN=0.0.0.0:8080"


def test_linux_gateway_listens_on_every_interface(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """On Linux, LiveKit's container reaches the gateway through the bridge, so the gateway listens everywhere."""
    monkeypatch.setattr(local, "LISTEN_EVERYWHERE", f"{LISTEN}\n")
    local.write_shipped(tmp_path)
    env = (tmp_path / "env").read_text()
    assert LISTEN in env
    assert "PINECALL_GATEWAY_URL=http://127.0.0.1:8080" in env
    assert "?world=sandbox" in (tmp_path / "livekit.yaml").read_text()


def test_a_mac_keeps_the_gateway_on_loopback(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Docker Desktop routes host.docker.internal to the host's loopback: nothing more is opened."""
    monkeypatch.setattr(local, "LISTEN_EVERYWHERE", "")
    local.write_shipped(tmp_path)
    assert "PINECALL_GATEWAY_LISTEN" not in (tmp_path / "env").read_text()


def test_the_settings_are_written_once(tmp_path: Path) -> None:
    """A second run keeps the secrets the first one drew."""
    local.write_shipped(tmp_path)
    first = (tmp_path / "env").read_text()
    local.write_shipped(tmp_path)
    assert (tmp_path / "env").read_text() == first
