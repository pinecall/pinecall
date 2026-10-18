"""This machine's processes as the runner drives them: a process a host, no sandbox, for a runtime of one's own."""

import asyncio
import io
import os
import shutil
import signal
import tarfile
import time
from collections import deque
from collections.abc import Mapping
from dataclasses import dataclass, field
from pathlib import Path

from pinecall_runtime.exceptions import UpstreamError
from pinecall_runtime.hosting.service.hosts import (
    DEPENDENCIES,
    DRAIN_S,
    INSTALL_WITHIN_S,
    Container,
    Launch,
    cli_installed,
)

# What a host keeps of its output, its install's and its process's together: what `logs` reads.
KEPT_LINES = 2000
# A host's folder holds the release, the platform's CLI beside it, and the pid of its process.
RELEASE = "app"
CLI = "cli"
PID = "host.pid"
# What the runner's own environment lends an app's install and process, and nothing else: the
# runner's settings hold the vault's key, the database's address and its own key.
LENT = ("PATH", "HOME", "LANG", "LC_ALL", "TMPDIR", "SSL_CERT_FILE")
INSTALL_TIMED_OUT = f"the install did not end within {INSTALL_WITHIN_S}s"
NOT_LAID_DOWN = "the release could not be laid down on this machine: {why}"
# The shell's own word for a command it could not run.
NOT_STARTED = 127
# A process of a runner that died is no child of this one: whether it left is asked this often.
LEFT_EVERY_S = 0.5


@dataclass
class _Host:
    """One host while the runner holds it: its folder, its output, the child running now."""

    app: str
    env: str
    release: int
    folder: Path
    # Given the install's time before its registering is timed, as a pod not yet running is.
    started_at: float
    lines: deque[str] = field(default_factory=lambda: deque[str](maxlen=KEPT_LINES))
    # The install, then the process.
    child: asyncio.subprocess.Process | None = None
    running: bool = False
    exit: int | None = None
    stopping: bool = False
    task: asyncio.Task[None] | None = None

    @property
    def state(self) -> str:
        """How it is, in a pod's words, which the runner's plan reads."""
        if self.exit is not None:
            return "Succeeded" if self.exit == 0 else "Failed"
        return "Running" if self.running else "Pending"


# The code is the machine's owner's: nothing fences it. A host is gone when the runner leaves, and
# one a runner that died left behind is stopped by the next before it starts anything.
@dataclass
class Processes:
    """The hosts of this machine, one process each, under one folder."""

    home: Path
    hosts: dict[str, _Host] = field(default_factory=dict[str, _Host])
    swept: bool = False

    async def running(self, env: str) -> list[Container]:
        """Every host of the env this runner started, running or not."""
        await self._swept()
        return [
            Container(name=name, app=host.app, release=host.release, state=host.state, started_at=host.started_at)
            for name, host in self.hosts.items()
            if host.env == env
        ]

    async def start(self, launch: Launch, environment: Mapping[str, str]) -> None:
        """The release laid down in the host's folder, then installed and run on a task of its own."""
        await self._swept()
        folder = self.home / launch.host
        try:
            await asyncio.to_thread(_laid_down, launch.source, folder)
        except (OSError, tarfile.TarError) as failed:
            raise UpstreamError(NOT_LAID_DOWN.format(why=failed)) from failed
        host = _Host(launch.app, launch.env, launch.release, folder, time.time() + INSTALL_WITHIN_S)
        self.hosts[launch.host] = host
        host.task = asyncio.create_task(_run(host, launch, environment))

    async def stop(self, name: str, grace_s: int = DRAIN_S) -> None:
        """SIGTERM, then grace_s before the kill; its folder goes with it."""
        host = self.hosts.pop(name, None)
        if host is not None:
            host.stopping = True
            if host.child is not None:
                await _ended(host.child, grace_s)
            if host.task is not None:
                await asyncio.gather(host.task, return_exceptions=True)
        await asyncio.to_thread(shutil.rmtree, self.home / name, True)

    async def logs(self, name: str, lines: int) -> str:
        """The last lines the host printed, its install's first."""
        host = self.hosts.get(name)
        if host is None or not host.lines:
            return ""
        return "\n".join(list(host.lines)[-lines:]) + "\n"

    async def close(self) -> None:
        """Every host drained and stopped: on this machine an app does not outlive its runner."""
        await asyncio.gather(*(self.stop(name) for name in list(self.hosts)))

    # Once, before this runner holds anything, so it never takes a host of its own for a leftover.
    async def _swept(self) -> None:
        if not self.swept:
            self.swept = True
            await asyncio.to_thread(_sweep, self.home)


# A command this machine cannot start (no sh, no npm) is the host's exit, with the reason as its output.
async def _run(host: _Host, launch: Launch, environment: Mapping[str, str]) -> None:
    try:
        await _installed_then_run(host, launch, environment)
    except OSError as failed:
        host.lines.append(str(failed))
        host.exit = NOT_STARTED


# A stop while it installs leaves it there: what was installed never runs.
async def _installed_then_run(host: _Host, launch: Launch, environment: Mapping[str, str]) -> None:
    lent = {name: os.environ[name] for name in LENT if name in os.environ}
    release = host.folder / RELEASE
    script = f"{DEPENDENCIES} && {cli_installed(str(host.folder / CLI))}"
    install = await _spawned(host, ["sh", "-c", script], release, lent)
    try:
        code = await asyncio.wait_for(_followed(install, host), INSTALL_WITHIN_S)
    except TimeoutError:
        await _ended(install, 0)
        host.lines.append(INSTALL_TIMED_OUT)
        code = 1
    if code != 0 or host.stopping:
        host.exit = code
        return
    command = [str(host.folder / CLI / "bin" / "pinecall"), *launch.arguments]
    process = await _spawned(host, command, release, {**lent, "NO_COLOR": "1", **environment})
    host.running, host.started_at = True, time.time()
    await asyncio.to_thread((host.folder / PID).write_text, str(process.pid))
    host.exit = await _followed(process, host)


# Its own session, so a signal reaches every process it starts (the CLI starts the agent's).
async def _spawned(
    host: _Host, command: list[str], cwd: Path, environment: dict[str, str]
) -> asyncio.subprocess.Process:
    child = await asyncio.create_subprocess_exec(
        *command,
        cwd=cwd,
        env=environment,
        stdin=asyncio.subprocess.DEVNULL,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.STDOUT,
        start_new_session=True,
    )
    host.child = child
    return child


async def _followed(child: asyncio.subprocess.Process, host: _Host) -> int:
    if child.stdout is not None:
        async for line in child.stdout:
            host.lines.append(line.decode(errors="replace").rstrip("\n"))
    return await child.wait()


async def _ended(child: asyncio.subprocess.Process, grace_s: int) -> None:
    if child.returncode is not None:
        return
    _signal(child.pid, signal.SIGTERM if grace_s else signal.SIGKILL)
    try:
        await asyncio.wait_for(child.wait(), grace_s or None)
    except TimeoutError:
        _signal(child.pid, signal.SIGKILL)
        await child.wait()


def _signal(group: int, sent: signal.Signals) -> None:
    try:
        os.killpg(group, sent)
    except ProcessLookupError:
        return


# Checked by the gateway when it was kept: files and folders under the project's own folder.
def _laid_down(source: bytes, folder: Path) -> None:
    shutil.rmtree(folder, ignore_errors=True)
    (folder / RELEASE).mkdir(parents=True)
    with tarfile.open(fileobj=io.BytesIO(source), mode="r:gz") as tarball:
        tarball.extractall(folder / RELEASE, filter="data")


# What a runner that died left: each process drained as a stop would, then its folder removed.
def _sweep(home: Path) -> None:
    if not home.is_dir():
        return
    for folder in home.iterdir():
        named = folder / PID
        if named.is_file() and (pid := int(named.read_text() or 0)) > 0:
            _signal(pid, signal.SIGTERM)
            deadline = time.monotonic() + DRAIN_S
            while _alive(pid) and time.monotonic() < deadline:
                time.sleep(LEFT_EVERY_S)
            _signal(pid, signal.SIGKILL)
        shutil.rmtree(folder, ignore_errors=True)


def _alive(pid: int) -> bool:
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    return True
