"""`local restore`: what writes is stopped, the database emptied and the dump fed to it, in that order."""

from pathlib import Path

import pytest

from runtime.cli.setup import compose, restore
from runtime.cli.setup.compose import Compose
from runtime.exceptions import ValidationError


def test_a_dump_replaces_the_database_with_every_writer_stopped(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """On a server the gateway, the workers, the overflows and the night stop first; then empty, then restore."""
    did: list[tuple[str, ...]] = []

    def run(self: Compose, *verb: str, failed: str) -> None:
        did.append(verb)

    def feed(self: Compose, *verb: str, source: Path, failed: str) -> None:
        did.append((*verb, f"< {source.name}"))

    def no_ports(ports: object) -> None:
        return None

    def built(image: str) -> bool:
        return True

    monkeypatch.setattr(Compose, "run", run)
    monkeypatch.setattr(Compose, "feed", feed)
    monkeypatch.setattr(compose, "wait_for_ports", no_ports)
    monkeypatch.setattr(compose, "is_built", built)
    (tmp_path / "postgres").mkdir()
    (tmp_path / compose.BUILT_FROM).write_text(compose.files_of_postgres(tmp_path))
    (tmp_path / "compose.yaml").write_text("services: {}\n")
    (tmp_path / "server.yaml").write_text("services: {}\n")
    dump = tmp_path / "production.dump"
    dump.write_bytes(b"PGDMP")
    restore.replace_database(tmp_path, dump)
    up, stop, empty, restored = did
    assert up[-1] == "postgres" and "up" in up
    assert stop[2] == "stop" and set(stop[3:]) == {"gateway", "gateway-b", *restore.WRITERS}
    assert empty[:3] == ("exec", "-T", "postgres") and empty[-1].startswith("DROP SCHEMA public CASCADE")
    assert restored[3] == "pg_restore" and restored[-1] == "< production.dump"

    # A laptop runs its gateway in a terminal: there is no service to stop.
    did.clear()
    (tmp_path / "server.yaml").unlink()
    restore.replace_database(tmp_path, dump)
    assert [verb[2 if verb[0] == "--progress" else 0] for verb in did] == ["up", "exec", "exec"]


def test_a_dump_that_is_not_there_is_refused_before_anything_stops(tmp_path: Path) -> None:
    """The path is read before the runtime is touched."""
    with pytest.raises(ValidationError, match="is not a file"):
        restore.replace_database(tmp_path, tmp_path / "nothing.dump")
