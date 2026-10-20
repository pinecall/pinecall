"""A server's files and settings: its name checked, Caddy's routes, LiveKit's own pair or the operator's, the phone."""

import socket
from pathlib import Path

import pytest

from pinecall_runtime.cli import local
from pinecall_runtime.cli import setup_server as server_
from pinecall_runtime.exceptions import ValidationError

NAME = "voice.example.com"
THEIRS = server_.TheirLiveKit("wss://acme.livekit.cloud", "APIacme", "their-secret")


def written(tmp_path: Path, server: server_.Server) -> dict[str, str]:
    local.write_shipped(tmp_path)
    env = tmp_path / "env"
    values = local.set_values(env, server_.settings_of(server, local.read_env(env)))
    server_.write_files(tmp_path, server, values, None)
    return values


def test_a_server_draws_its_own_livekit_pair_and_keeps_the_gateway_on_loopback(tmp_path: Path) -> None:
    """Never the laptop's development pair; LiveKit's events reach the gateway on loopback; Caddy is the door."""
    values = written(tmp_path, server_.Server(NAME))
    assert values["PINECALL_DOMAIN"] == NAME
    assert values["LIVEKIT_API_KEY"] == server_.LIVEKIT_KEY
    assert values["LIVEKIT_API_SECRET"] != "a-laptop-only-livekit-secret-0123456789"
    assert "PINECALL_GATEWAY_LISTEN" not in values and "LIVEKIT_PUBLIC_URL" not in values
    config = (tmp_path / "livekit.server.yaml").read_text()
    assert f"pinecall: {values['LIVEKIT_API_SECRET']}" in config
    assert "http://127.0.0.1:8080/v1/livekit/webhook" in config and "use_external_ip: true" in config
    assert (tmp_path / "livekit.server.yaml").stat().st_mode & 0o077 == 0
    caddy = (tmp_path / "Caddyfile").read_text()
    assert caddy.startswith(f"{NAME} {{") and "/rtc" in caddy and "reverse_proxy 127.0.0.1:8080" in caddy


def test_a_second_run_keeps_the_pair(tmp_path: Path) -> None:
    """Run again, the server keeps the secret LiveKit and its rooms were signed with."""
    first = written(tmp_path, server_.Server(NAME))
    again = written(tmp_path, server_.Server(NAME))
    assert again["LIVEKIT_API_SECRET"] == first["LIVEKIT_API_SECRET"]


def test_their_livekit_is_the_runtimes_and_the_browsers(tmp_path: Path) -> None:
    """With the operator's own LiveKit, Caddy carries no /rtc and every setting names theirs."""
    values = written(tmp_path, server_.Server(NAME, THEIRS))
    assert values["LIVEKIT_URL"] == values["LIVEKIT_PUBLIC_URL"] == THEIRS.url
    assert values["LIVEKIT_API_KEY"] == THEIRS.key and values["LIVEKIT_API_SECRET"] == THEIRS.secret
    assert "/rtc" not in (tmp_path / "Caddyfile").read_text()
    assert server_.from_the_env(values) == server_.Server(NAME, THEIRS)


def test_the_env_file_says_which_server_this_is(tmp_path: Path) -> None:
    """A laptop's env names no server; a server's names its name, its LiveKit and its phone."""
    local.write_shipped(tmp_path)
    assert server_.from_the_env(local.read_env(tmp_path / "env")) is None
    values = written(tmp_path, server_.Server(NAME, phone=True))
    assert values["PINECALL_SIP_DOMAIN"] == NAME
    assert server_.from_the_env(values) == server_.Server(NAME, phone=True)


def test_the_image_installs_this_release_or_the_wheel_given(tmp_path: Path) -> None:
    """From PyPI at this package's version, or the wheel `--from` names, copied beside the Dockerfile."""
    assert server_.image_of(None)["PINECALL_RUNTIME_SPEC"].startswith("pinecall-runtime[voice]==")
    wheel = tmp_path / "pinecall_runtime-9.9.9-py3-none-any.whl"
    wheel.write_bytes(b"wheel")
    local.write_shipped(tmp_path)
    values = local.set_values(tmp_path / "env", server_.settings_of(server_.Server(NAME), {}))
    server_.write_files(tmp_path, server_.Server(NAME), values, wheel)
    assert (tmp_path / "runtime" / "wheels" / wheel.name).read_bytes() == b"wheel"
    assert server_.image_of(wheel)["PINECALL_RUNTIME_SPEC"] == f"/wheels/{wheel.name}[voice]"


def test_a_name_pointing_elsewhere_is_refused_with_both_addresses(monkeypatch: pytest.MonkeyPatch) -> None:
    """The name must point here, or Let's Encrypt never issues: the sentence says what to set."""

    def resolved(*_args: object, **_kwargs: object) -> list[tuple[object, ...]]:
        return [(socket.AF_INET, socket.SOCK_STREAM, 6, "", ("203.0.113.9", 443))]

    monkeypatch.setattr(socket, "getaddrinfo", resolved)
    monkeypatch.setattr(server_, "this_machines_address", lambda: "203.0.113.7")
    with pytest.raises(ValidationError, match=r"points at 203\.0\.113\.9, and this machine is 203\.0\.113\.7"):
        server_.check_name(NAME)
    monkeypatch.setattr(server_, "this_machines_address", lambda: "203.0.113.9")
    assert server_.check_name(NAME).endswith("this machine ✓")


def test_a_name_that_resolves_nowhere_is_refused(monkeypatch: pytest.MonkeyPatch) -> None:
    """No A record: refused before anything is brought up."""

    def nowhere(*_args: object, **_kwargs: object) -> list[object]:
        raise socket.gaierror

    monkeypatch.setattr(socket, "getaddrinfo", nowhere)
    with pytest.raises(ValidationError, match="resolves to no address"):
        server_.check_name(NAME)
