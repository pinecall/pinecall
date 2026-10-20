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


def test_set_values_replaces_adds_and_takes_out_keeping_the_rest(tmp_path: Path) -> None:
    """A server's settings land in the env file: a name set, one added, one taken out, every secret kept."""
    local.write_shipped(tmp_path)
    env = tmp_path / "env"
    vault = local.read_env(env)["PINECALL_VAULT_KEY"]
    values = local.set_values(env, {"LIVEKIT_URL": "wss://x", "PINECALL_DOMAIN": "a.example", "PINECALL_FLEET": None})
    assert values["LIVEKIT_URL"] == "wss://x" and values["PINECALL_DOMAIN"] == "a.example"
    assert "PINECALL_FLEET" not in values and values["PINECALL_VAULT_KEY"] == vault


def test_a_servers_compose_is_laid_over_the_services(tmp_path: Path) -> None:
    """`down` and `logs` reach a server's services too, once server.yaml is there."""
    local.write_shipped(tmp_path)
    assert local.compose_files(tmp_path) == ["docker", "compose", "-f", str(tmp_path / "compose.yaml")]
    (tmp_path / "server.yaml").write_text("services: {}\n")
    assert local.compose_files(tmp_path)[-2:] == ["-f", str(tmp_path / "server.yaml")]


def test_the_package_ships_the_list_prices_and_their_notice(tmp_path: Path) -> None:
    """The prices file rides beside the compose files with the MIT notice of the rows it took."""
    local.write_shipped(tmp_path)
    assert (tmp_path / "prices.csv").read_text().splitlines()[0].startswith("# What each model")
    assert "MIT License" in (tmp_path / "prices.LICENSE").read_text()
    assert (tmp_path / "models.gpu.yaml").is_file()


def test_the_services_come_back_after_a_reboot(tmp_path: Path) -> None:
    """Postgres, Redis and LiveKit restart with Docker: a server's gateway would find no database otherwise."""
    local.write_shipped(tmp_path)
    compose = (tmp_path / "compose.yaml").read_text()
    for service in ("postgres", "redis", "livekit"):
        block = compose.split(f"\n  {service}:\n", 1)[1].split("\n\n", 1)[0]
        assert "restart: unless-stopped" in block, service


def test_sip_reads_its_config_where_the_image_looks_for_it(tmp_path: Path) -> None:
    """LiveKit's SIP image opens /sip/config.yaml; a file mounted anywhere else left it restarting forever."""
    local.write_shipped(tmp_path)
    assert "./sip.yaml:/sip/config.yaml:ro" in (tmp_path / "compose.yaml").read_text()
    shipped = local.files("pinecall_runtime.cli").joinpath("local", "server.yaml").read_text(encoding="utf-8")
    assert "./sip.server.yaml:/sip/config.yaml:ro" in shipped
