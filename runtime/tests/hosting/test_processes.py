"""This machine's hosts: a release laid down, installed and run as a process, stopped, and swept after a runner dies."""

import asyncio
import gzip
import io
import subprocess
import tarfile
import time
from collections.abc import Callable
from pathlib import Path

import pytest

from pinecall_runtime.hosting.service.hosts import Launch
from pinecall_runtime.hosting.service.processes import PID, Processes, _alive

HOST = "front-r1-0a1b2c3d"
# The platform's CLI as a fake: npm lays it down where --prefix says, and it prints what it was
# started with, then serves until a SIGTERM drains it.
NPM = """#!/bin/sh
for word in "$@"; do [ -n "$prefix" ] && [ -z "$at" ] && at="$word"; [ "$word" = --prefix ] && prefix=1; done
mkdir -p "$at/bin"
cat > "$at/bin/pinecall" <<'CLI'
#!/bin/sh
echo "pinecall $* as $PINECALL_HOST key=$PINECALL_KEY vault=${PINECALL_VAULT_KEY:-none}"
trap 'echo drained; exit 0' TERM
while :; do sleep 0.1; done
CLI
chmod +x "$at/bin/pinecall"
"""
WITHIN_S = 8.0


def _tools(tmp_path: Path, uv: str) -> Path:
    tools = tmp_path / "bin"
    tools.mkdir()
    for name, body in {"npm": NPM, "uv": f"#!/bin/sh\n{uv}\n"}.items():
        (tools / name).write_text(body)
        (tools / name).chmod(0o755)
    return tools


def _release(files: list[str]) -> bytes:
    packed = io.BytesIO()
    with tarfile.open(fileobj=packed, mode="w") as tarball:
        for path in files:
            member = tarfile.TarInfo(path)
            member.size = 1
            tarball.addfile(member, io.BytesIO(b"x"))
    return gzip.compress(packed.getvalue())


def _launch(source: bytes) -> Launch:
    return Launch(env="sandbox", app="acme/front", host=HOST, release=1, sha256="", source=source, arguments=["start"])


async def _until(found: Callable[[], bool]) -> None:
    deadline = time.monotonic() + WITHIN_S
    while not found() and time.monotonic() < deadline:
        await asyncio.sleep(0.05)
    assert found()


@pytest.fixture
def python_release() -> bytes:
    return _release(["agents/front/agent.py", "pyproject.toml"])


async def test_a_release_is_installed_then_run_with_its_environment_and_nothing_of_the_runners(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, python_release: bytes
) -> None:
    monkeypatch.setenv("PATH", f"{_tools(tmp_path, 'echo "uv $*"')}:/usr/bin:/bin")
    monkeypatch.setenv("PINECALL_VAULT_KEY", "the-runners-own")
    hosts = Processes(tmp_path / "apps")
    await hosts.start(_launch(python_release), {"PINECALL_KEY": "pk_app", "PINECALL_HOST": HOST})
    await _until(lambda: "pinecall start" in hosts.hosts[HOST].lines[-1] if hosts.hosts[HOST].lines else False)

    [running] = await hosts.running("sandbox")
    assert (running.name, running.app, running.release, running.state) == (HOST, "acme/front", 1, "Running")
    assert await hosts.running("production") == []
    said = await hosts.logs(HOST, 10)
    assert "uv sync --no-dev" in said
    assert f"pinecall start as {HOST} key=pk_app vault=none" in said
    assert (tmp_path / "apps" / HOST / PID).is_file()

    child = hosts.hosts[HOST].child
    await hosts.stop(HOST)
    assert child is not None and child.returncode == 0
    assert await hosts.running("sandbox") == []
    assert not (tmp_path / "apps" / HOST).exists()


async def test_an_install_that_fails_is_a_failed_host_with_its_lines_and_never_runs(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, python_release: bytes
) -> None:
    monkeypatch.setenv("PATH", f"{_tools(tmp_path, 'echo no solution for pinecall; exit 1')}:/usr/bin:/bin")
    hosts = Processes(tmp_path / "apps")
    await hosts.start(_launch(python_release), {})
    await _until(lambda: hosts.hosts[HOST].state == "Failed")

    said = await hosts.logs(HOST, 10)
    assert "no solution for pinecall" in said
    assert "pinecall start" not in said
    await hosts.close()
    assert hosts.hosts == {}


async def test_what_a_runner_that_died_left_is_drained_and_removed_before_anything_starts(tmp_path: Path) -> None:
    # Its process belongs to nobody here once its shell leaves, as one of a dead runner does.
    started = subprocess.run(
        ["sh", "-c", "setsid sleep 30 >/dev/null 2>&1 & echo $!"], capture_output=True, text=True, check=True
    )
    pid = int(started.stdout)
    left = tmp_path / "apps" / HOST
    left.mkdir(parents=True)
    (left / PID).write_text(str(pid))

    hosts = Processes(tmp_path / "apps")
    assert await hosts.running("sandbox") == []
    assert not left.exists()
    # Ended, which a zombie init has not reaped yet is too: it still answers a signal, and a loaded box
    # reaps late.
    assert not _alive(pid)


async def test_the_hosts_this_runner_started_are_never_taken_for_what_another_left(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, python_release: bytes
) -> None:
    monkeypatch.setenv("PATH", f"{_tools(tmp_path, 'echo "uv $*"')}:/usr/bin:/bin")
    hosts = Processes(tmp_path / "apps")
    await hosts.start(_launch(python_release), {"PINECALL_HOST": HOST})
    await _until(lambda: hosts.hosts[HOST].state == "Running")
    await asyncio.sleep(0.2)
    assert [each.state for each in await hosts.running("sandbox")] == ["Running"]
    await hosts.close()
