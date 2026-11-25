"""A server's name checked, what its env file says of it, and what a run brings up: the image, overflow, the night."""

import socket
from pathlib import Path

import pytest

from runtime.cli.setup import server as server_
from runtime.cli.setup.compose import Compose
from runtime.cli.setup.files import write_shipped
from runtime.exceptions import ValidationError
from tests.cli.setup.test_server_files import written

NAME = "voice.example.com"
# The order that keeps the name answering through an update: Caddy and its file read again, one
# gateway waited for while the other serves, the other, then everything else.
# What the processes write is made theirs before any of them starts.
THE_ROLL = ["run own", "up caddy", "reload caddy", "up gateway", "up gateway-b", "up everything"]


def steps_of(ran: list[tuple[str, ...]]) -> list[str]:
    """Each compose verb a run made, as the word that tells it from the others."""
    steps: list[str] = []
    for verb in ran:
        if verb[0] == "exec":
            steps.append("reload caddy")
        elif verb[2] == "up":
            steps.append(f"up {verb[-1]}" if "--no-deps" in verb else "up everything")
        elif verb[2] in ("restart", "run"):
            steps.append(f"{verb[2]} {verb[-1]}")
        else:
            steps.append(verb[2])
    return steps


THEIRS = server_.TheirLiveKit("wss://acme.livekit.cloud", "APIacme", "their-secret")


def test_the_env_file_says_which_server_this_is(tmp_path: Path) -> None:
    """A laptop's env names no server; a server's names its name, its LiveKit and its phone."""
    assert server_.from_the_env(write_shipped(tmp_path).read()) is None
    values = written(tmp_path, server_.Server(NAME, phone=True))
    assert values["PINECALL_SIP_DOMAIN"] == NAME
    assert server_.from_the_env(values) == server_.Server(NAME, phone=True)


def test_a_sip_name_of_the_operators_own_is_kept(tmp_path: Path) -> None:
    """Carriers' trunks name it already: `setup` says the server's name only where the env file says none."""
    env = write_shipped(tmp_path)
    server = server_.Server(NAME, phone=True)
    assert env.set(**server_.settings_of(server, env.read()))["PINECALL_SIP_DOMAIN"] == NAME
    given = env.set(PINECALL_SIP_DOMAIN="sip.example.com")
    assert env.set(**server_.settings_of(server, given))["PINECALL_SIP_DOMAIN"] == "sip.example.com"
    # The phone turned off, the env file names no SIP at all.
    assert "PINECALL_SIP_DOMAIN" not in env.set(**server_.settings_of(server_.Server(NAME), env.read()))


def test_a_registrys_image_is_run_as_it_is_and_never_built(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """`--image`: the env file names it, every service runs it, and it is pulled where a build would be."""
    image = "registry.example.com/pinecall/runtime:1a2b3c4d"
    server = server_.Server(NAME, image=image)
    values = written(tmp_path, server)
    assert values[server_.IMAGE] == image and server_.from_the_env(values) == server
    assert server_.image_of(None, image)[server_.IMAGE] == image
    assert server_.image_of(None)[server_.IMAGE].startswith("pinecall-runtime:")
    # Built here again, the env file names no image: the next run builds this release.
    assert server_.IMAGE not in written(tmp_path, server_.Server(NAME))
    ran: list[tuple[str, ...]] = []

    def record(self: Compose, *verb: str, failed: str) -> None:
        ran.append(verb)

    monkeypatch.setattr(Compose, "run", record)
    server_.bring_up(tmp_path, server, values, None)
    assert steps_of(ran) == ["rm", "pull", *THE_ROLL]
    ran.clear()
    server_.bring_up(tmp_path, server_.Server(NAME), values, None)
    assert steps_of(ran) == ["rm", "build", *THE_ROLL]


def test_a_server_answers_past_its_last_seat_and_runs_the_night(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Each environment's overflow and the nightly retention are started with its workers, on the one image."""
    ran: list[tuple[str, ...]] = []

    def record(self: Compose, *verb: str, failed: str) -> None:
        ran.append(verb)

    monkeypatch.setattr(Compose, "run", record)
    server_.bring_up(tmp_path, server_.Server(NAME), {}, None, build=False)
    started = ran[-1]
    for service in ("overflow-sandbox", "overflow-production", "retention", "worker-sandbox", "worker-production"):
        assert service in started
    # And the service that plays the callers of spoken simulations, which a server's gateways only place.
    assert "callers" in started
    written(tmp_path, server_.Server(NAME))
    compose = (tmp_path / "server.yaml").read_text()
    # A worker told to stop ends when its last call does: Docker's ten seconds cut every call in flight.
    assert compose.count("stop_grace_period: 10m") == 2
    # Each environment's seats are its own line of the env file, else the one line both read.
    assert '"${PINECALL_SANDBOX_MAX_JOBS:-${PINECALL_MAX_JOBS:-4}}"' in compose
    assert '"${PINECALL_PRODUCTION_MAX_JOBS:-${PINECALL_MAX_JOBS:-4}}"' in compose
    assert compose.count('command: ["worker", "overflow"]') == 2 and 'command: ["retention", "nightly"]' in compose


def test_a_place_for_the_backups_starts_the_nightly_beside_postgres(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """`PINECALL_BACKUP_URL` in the env file: the base backups' service runs; without it, it is removed."""
    ran: list[tuple[tuple[str, ...], tuple[str, ...]]] = []

    def record(self: Compose, *verb: str, failed: str) -> None:
        ran.append((self.profiles, verb))

    monkeypatch.setattr(Compose, "run", record)
    server_.bring_up(tmp_path, server_.Server(NAME), {server_.BACKUPS: "s3://backups/voice"}, None, build=False)
    (_, removed), *_, (profiles, up) = ran
    assert "postgres-backup" not in removed
    assert "server-backups" in profiles and up[-1] == "postgres-backup"
    ran.clear()
    server_.bring_up(tmp_path, server_.Server(NAME), {}, None, build=False)
    (_, removed), *_, (profiles, up) = ran
    assert removed[-1] == "postgres-backup" and "server-backups" not in profiles and "postgres-backup" not in up
    # Postgres hands every finished segment to the script that archives it, or says it is done.
    written(tmp_path, server_.Server(NAME))
    assert "archive_command=/usr/local/bin/archive-wal %p" in (tmp_path / "compose.yaml").read_text()
    for script in ("archive-wal", "backup-nightly"):
        assert (tmp_path / "postgres" / script).read_text().startswith("#!/usr/bin/env bash")


def test_a_name_pointing_elsewhere_is_refused_with_both_addresses() -> None:
    """The name must point here, or Let's Encrypt never issues: the sentence says what to set."""

    def resolved(_name: str) -> list[str]:
        return ["203.0.113.9"]

    with pytest.raises(ValidationError, match=r"points at 203\.0\.113\.9, and this machine is 203\.0\.113\.7"):
        server_.check_name(NAME, resolve=resolved, here=lambda: "203.0.113.7")
    assert server_.check_name(NAME, resolve=resolved, here=lambda: "203.0.113.9").endswith("this machine ✓")


def test_a_name_that_resolves_nowhere_is_refused() -> None:
    """No A record: refused before anything is brought up."""

    def nowhere(_name: str) -> list[str]:
        raise socket.gaierror

    with pytest.raises(ValidationError, match="resolves to no address"):
        server_.check_name(NAME, resolve=nowhere, here=lambda: None)


def test_what_this_server_does_not_run_is_removed_with_every_profile_on(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """`sip-server` depends on `livekit-server`: compose refuses to remove one while the other's profile is off."""
    ran: list[tuple[tuple[str, ...], tuple[str, ...]]] = []

    def record(self: Compose, *verb: str, failed: str) -> None:
        ran.append((self.profiles, verb))

    monkeypatch.setattr(Compose, "run", record)
    server_.bring_up(tmp_path, server_.Server(NAME), {}, None, build=False)
    removed, *_, up = ran
    assert removed == (
        server_.EVERY_PROFILE,
        ("--progress", "quiet", "rm", "--stop", "--force", "livekit", "sip", "sip-server", "postgres-backup"),
    )
    # What runs is this server's own: its LiveKit's profile on, the phone's off.
    assert up[0] == ("server", "server-livekit") and up[1][-1] == "livekit-server"


def test_a_config_that_changed_is_read_again(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Caddy reloads its file on every run; LiveKit's and SIP's configs are compose's, so nothing else restarts."""
    ran: list[tuple[str, ...]] = []

    def record(self: Compose, *verb: str, failed: str) -> None:
        ran.append(verb)

    monkeypatch.setattr(Compose, "run", record)
    server = server_.Server(NAME, phone=True)
    values = written(tmp_path, server)
    server_.bring_up(tmp_path, server, values, None, build=False)
    assert steps_of(ran) == ["rm", *THE_ROLL]
