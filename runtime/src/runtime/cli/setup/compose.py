"""docker compose as `setup` and `local` run it: the files, the profiles, the environment, one way to fail."""

import os
import socket
import subprocess
import time
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from pathlib import Path
from shutil import which

from runtime.exceptions import ConfigurationError, UpstreamError

# Docker says a container is healthy before the host's side of its port answers: a moment, on a Mac.
PORTS_WITHIN_S = 60.0
# What a failure keeps of compose's own words: its last lines, where the reason is.
SAID_AT_MOST = 2000


def docker_or_refuse() -> None:
    """Docker on PATH, and its compose plugin answering; or the sentence that says what to do."""
    if which("docker") is None:
        raise ConfigurationError(
            "Docker is not here: install Docker Desktop (macOS, Windows) or Docker Engine with the compose "
            "plugin, start it, and run this again"
        )
    version = subprocess.run(["docker", "compose", "version", "--short"], capture_output=True, text=True, check=False)
    if version.returncode != 0:
        raise UpstreamError("docker compose did not answer: start Docker and run this again")


# Until 2026-11 eleven calls built the command six ways and cut the error five times.
@dataclass(frozen=True)
class Compose:
    """docker compose on these files, with these profiles and this environment."""

    files: tuple[Path, ...]
    profiles: tuple[str, ...] = ()
    environment: Mapping[str, str] = field(default_factory=dict[str, str])

    def run(self, *verb: str, failed: str) -> None:
        """One compose verb, quiet; UpstreamError with compose's last words when it fails."""
        done = subprocess.run(
            self._command(*verb), capture_output=True, text=True, check=False, env={**os.environ, **self.environment}
        )
        if done.returncode != 0:
            raise UpstreamError(failed.format(output=(done.stderr or done.stdout).strip()[-SAID_AT_MOST:]))

    def follow(self, *verb: str) -> int:
        """One compose verb whose output is the person's to read (`logs`, `down`); its exit."""
        return subprocess.run(self._command(*verb), check=False, env={**os.environ, **self.environment}).returncode

    def is_running(self, service: str) -> bool:
        """Whether compose runs that service now."""
        listed = subprocess.run(
            self._command("ps", "--status", "running", "--quiet", service),
            capture_output=True,
            text=True,
            check=False,
            env={**os.environ, **self.environment},
        )
        return listed.returncode == 0 and bool(listed.stdout.strip())

    def _command(self, *verb: str) -> list[str]:
        files = [option for path in self.files for option in ("-f", str(path))]
        profiles = [option for profile in self.profiles for option in ("--profile", profile)]
        return ["docker", "compose", *files, *profiles, *verb]


def wait_for_ports(ports: Sequence[tuple[str, int]], within_s: float = PORTS_WITHIN_S) -> None:
    """Wait until each service accepts a connection on its loopback port, or say which did not."""
    for service, port in ports:
        deadline = time.monotonic() + within_s
        while True:
            try:
                with socket.create_connection(("127.0.0.1", port), timeout=1.0):
                    break
            except OSError:
                if time.monotonic() > deadline:
                    raise UpstreamError(
                        f"{service} did not answer on 127.0.0.1:{port} within {within_s:.0f} s: `docker compose ps`"
                    ) from None
                time.sleep(0.5)


# The services on loopback, as the settings name them: the name a person reads, the port, the service.
SERVICES = ("postgres", "redis", "livekit")
PORTS: dict[str, tuple[int, str]] = {
    "Postgres": (55433, "postgres"),
    "Redis": (56380, "redis"),
    "LiveKit": (7880, "livekit"),
}
COMPOSE_FAILED = "docker compose could not bring the services up:\n{output}"


def services_up(where: Path, services: Sequence[str]) -> None:
    """The services' `docker compose up`, built, waited for, and each one's loopback port answering."""
    up = ("--progress", "quiet", "up", "-d", "--build", "--wait", *services)
    Compose((where / "compose.yaml",)).run(*up, failed=COMPOSE_FAILED)
    wait_for_ports([(name, port) for name, (port, service) in PORTS.items() if service in services])
