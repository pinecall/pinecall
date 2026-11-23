"""docker compose as the installer runs it: the files a server's services are laid over."""

import subprocess
from pathlib import Path

import pytest

from runtime.cli.setup import compose
from runtime.cli.setup.compose import compose_files
from runtime.cli.setup.files import write_shipped
from runtime.exceptions import UpstreamError

NO_ACCESS = "permission denied while trying to connect to the docker API at unix:///var/run/docker.sock"


def docker_answering(monkeypatch: pytest.MonkeyPatch, *, daemon: int) -> None:
    """Docker on PATH with its compose plugin, and a daemon that answers this user with that exit."""

    def run(command: list[str], **_how: object) -> subprocess.CompletedProcess[str]:
        refused = command[1] == "info" and daemon != 0
        return subprocess.CompletedProcess(command, daemon if refused else 0, "", NO_ACCESS if refused else "")

    def found(_name: str) -> str:
        return "/usr/bin/docker"

    monkeypatch.setattr(compose, "which", found)
    monkeypatch.setattr(subprocess, "run", run)


def test_a_daemon_this_user_cannot_reach_is_refused_before_anything_is_asked(monkeypatch: pytest.MonkeyPatch) -> None:
    """Docker installed and its daemon closed to this user: said in one sentence, with what lets them in."""
    docker_answering(monkeypatch, daemon=1)
    with pytest.raises(UpstreamError, match="did not answer this user") as refused:
        compose.docker_or_refuse()
    assert NO_ACCESS in str(refused.value) and "sudo usermod -aG docker $USER" in str(refused.value)
    docker_answering(monkeypatch, daemon=0)
    compose.docker_or_refuse()


def test_a_servers_compose_is_laid_over_the_services(tmp_path: Path) -> None:
    """`down` and `logs` reach a server's services too, once server.yaml is there."""
    write_shipped(tmp_path)
    assert compose_files(tmp_path) == (tmp_path / "compose.yaml",)
    (tmp_path / "server.yaml").write_text("services: {}\n")
    assert compose_files(tmp_path) == (tmp_path / "compose.yaml", tmp_path / "server.yaml")


def test_postgres_is_built_when_its_files_changed_and_never_on_every_run(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A build of the same files is a new image to Docker, and compose would stop the database to start it on that."""
    ran: list[str] = []
    held: list[str] = []

    def record(self: compose.Compose, *verb: str, failed: str) -> None:
        ran.append(verb[2])
        if verb[2] == "build":
            held.append(compose.POSTGRES_IMAGE)

    def no_ports(ports: object) -> None:
        return None

    def is_held(image: str) -> bool:
        return image in held

    monkeypatch.setattr(compose.Compose, "run", record)
    monkeypatch.setattr(compose, "is_built", is_held)
    monkeypatch.setattr(compose, "wait_for_ports", no_ports)
    write_shipped(tmp_path)
    compose.services_up(tmp_path, ("postgres", "redis"), {})
    compose.services_up(tmp_path, ("postgres", "redis"), {})
    assert ran == ["build", "up", "up"]
    # A file of the image changed (a release brought another Dockerfile): built once more.
    (tmp_path / "postgres" / "extensions.sql").write_text("-- another release\n")
    compose.services_up(tmp_path, ("postgres",), {})
    # The image gone from this machine: built again from the same files.
    held.clear()
    compose.services_up(tmp_path, ("postgres",), {})
    assert ran == ["build", "up", "up", "build", "up", "build", "up"]
    # The image compose.yaml names is the one asked about.
    assert f"image: {compose.POSTGRES_IMAGE}" in (tmp_path / "compose.yaml").read_text()
