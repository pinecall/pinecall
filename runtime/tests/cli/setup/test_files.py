"""What the package ships for a machine's runtime: written where it keeps it, the settings drawn once."""

from pathlib import Path

from runtime.cli.setup.files import find_shipped, write_shipped

LISTEN = "PINECALL_GATEWAY_LISTEN=0.0.0.0:8080"


def test_linux_gateway_listens_on_every_interface(tmp_path: Path) -> None:
    """On Linux, LiveKit's container reaches the gateway through the bridge, so the gateway listens everywhere."""
    env = write_shipped(tmp_path, listen=f"{LISTEN}\n").path.read_text()
    assert LISTEN in env
    assert "PINECALL_GATEWAY_URL=http://127.0.0.1:8080" in env
    assert "?world=sandbox" in (tmp_path / "livekit.yaml").read_text()


def test_a_mac_keeps_the_gateway_on_loopback(tmp_path: Path) -> None:
    """Docker Desktop routes host.docker.internal to the host's loopback: nothing more is opened."""
    assert "PINECALL_GATEWAY_LISTEN" not in write_shipped(tmp_path, listen="").path.read_text()


def test_the_settings_are_written_once(tmp_path: Path) -> None:
    """A second run keeps the secrets the first one drew."""
    first = write_shipped(tmp_path).path.read_text()
    assert write_shipped(tmp_path).path.read_text() == first


def test_the_package_ships_the_list_prices_their_notice_and_what_was_measured(tmp_path: Path) -> None:
    """The prices file rides beside the compose files with the MIT notice of the rows it took."""
    write_shipped(tmp_path)
    assert (tmp_path / "prices.csv").read_text().splitlines()[0].startswith("# What each model")
    assert "MIT License" in (tmp_path / "prices.LICENSE").read_text()
    assert (tmp_path / "models.gpu.yaml").is_file()
    assert (tmp_path / "measured.csv").is_file()


def test_the_services_come_back_after_a_reboot(tmp_path: Path) -> None:
    """Postgres, Redis and LiveKit restart with Docker: a server's gateway would find no database otherwise."""
    write_shipped(tmp_path)
    compose = (tmp_path / "compose.yaml").read_text()
    for service in ("postgres", "redis", "livekit"):
        block = compose.split(f"\n  {service}:\n", 1)[1].split("\n\n", 1)[0]
        assert "restart: unless-stopped" in block, service


def test_sip_reads_its_config_where_the_image_looks_for_it(tmp_path: Path) -> None:
    """LiveKit's SIP image opens /sip/config.yaml; a file mounted anywhere else left it restarting forever."""
    write_shipped(tmp_path)
    assert "./sip.yaml:/sip/config.yaml:ro" in (tmp_path / "compose.yaml").read_text()
    assert "./sip.server.yaml:/sip/config.yaml:ro" in find_shipped("server.yaml").read_text(encoding="utf-8")


# A fleet's key is a setting since R11: the production worker reads its fleet's from the settings file.
def test_a_servers_production_worker_reads_its_fleets_key_from_the_settings() -> None:
    assert "PINECALL_WORKER_KEY: ${PINECALL_PRODUCTION_FLEET_KEY}" in find_shipped("server.yaml").read_text(
        encoding="utf-8"
    )
