"""The local runtime's files: the settings written once, and where the gateway listens on Linux."""

from pathlib import Path

import pytest
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker

from pinecall_runtime.accounts.service import keys
from pinecall_runtime.cli import local
from tests.conftest import needs_the_database

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


@needs_the_database
async def test_a_box_key_the_database_does_not_know_is_drawn_again(
    tmp_path: Path, engine: AsyncEngine, sessions: async_sessionmaker[AsyncSession]
) -> None:
    """`down --volumes` keeps the env file: its keys are of a database that is gone, and up draws new ones."""
    env = tmp_path / "env"
    env.write_text("PINECALL_VAULT_KEY=x\nPINECALL_WORKER_KEY=pc_of_a_database_deleted\n")
    values = {"PINECALL_WORKER_KEY": "pc_of_a_database_deleted"}
    await local.draw_box_keys(engine, values, env)
    lines = env.read_text().splitlines()
    assert lines[0] == "PINECALL_VAULT_KEY=x"
    assert values["PINECALL_WORKER_KEY"] != "pc_of_a_database_deleted"
    assert f"PINECALL_WORKER_KEY={values['PINECALL_WORKER_KEY']}" in lines
    assert f"PINECALL_RUNNER_KEY={values['PINECALL_RUNNER_KEY']}" in lines
    assert lines.count("PINECALL_WORKER_KEY=pc_of_a_database_deleted") == 0
    async with sessions() as session:
        for variable in ("PINECALL_WORKER_KEY", "PINECALL_RUNNER_KEY"):
            assert await keys.verify_key(session, values[variable]) is not None
    # Known now: drawn once, and kept.
    before = dict(values)
    await local.draw_box_keys(engine, values, env)
    assert values == before
