"""A server's certificate asked for again: only when the name points here and Caddy holds none."""

import socket
from pathlib import Path

import pytest

from runtime.cli.setup import certificate
from runtime.cli.setup import server as server_
from runtime.cli.setup.compose import Compose
from runtime.cli.setup.files import write_shipped

NAME = "voice.example.com"
HERE = "203.0.113.7"


def _asked(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, *, holds: bool, found: list[str] | None
) -> list[tuple[str, ...]]:
    ran: list[tuple[str, ...]] = []

    def record(self: Compose, *verb: str, failed: str) -> None:
        ran.append(verb)

    def resolved(_name: str) -> list[str]:
        if found is None:
            raise socket.gaierror
        return found

    monkeypatch.setattr(Compose, "run", record)
    server = server_.Server(NAME)
    values = write_shipped(tmp_path).set(**server_.settings_of(server, {}))
    again = certificate.ask_again(
        tmp_path, server, values, holds=lambda _name: holds, resolve=resolved, here=lambda: HERE
    )
    assert again is bool(ran)
    return ran


def test_caddy_is_started_again_when_the_name_points_here_and_it_holds_no_certificate(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A name that has just arrived is asked for at once: Caddy alone is started again."""
    ran = _asked(tmp_path, monkeypatch, holds=False, found=[HERE])
    assert ran == [("--progress", "quiet", "restart", "caddy")]


def test_a_caddy_that_holds_the_certificate_is_left_serving(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """A server that answers its name is never started again for it."""
    assert _asked(tmp_path, monkeypatch, holds=True, found=[HERE]) == []


def test_a_name_that_points_elsewhere_or_nowhere_is_not_asked_for(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Asking again cannot succeed until the name is this machine's: Caddy is left to its own clock."""
    assert _asked(tmp_path, monkeypatch, holds=False, found=["203.0.113.9"]) == []
    assert _asked(tmp_path, monkeypatch, holds=False, found=None) == []
