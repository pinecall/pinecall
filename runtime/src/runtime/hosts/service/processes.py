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

from runtime.exceptions import UpstreamError
from runtime.hosts.service.install import DEPENDENCIES, install_cli
from runtime.hosts.service.place import DRAIN_S, INSTALL_WITHIN_S, Container, HostState, Launch

# What a host keeps of its output, its install's and its process's together: what `logs` reads.
KEPT_LINES = 2000
# A host's folder holds the release, the platform's CLI beside it, and its process: the pid, and when
# the machine says that process started, which is what tells it from another under the same number.
RELEASE = "app"
CLI = "cli"
PID = "host.pid"
# Where Linux says when a process started, in its own ticks since the machine came up.
STARTED_FIELD = 19
# What the runner's own environment lends an app's install and process, and nothing else: the
# runner's settings hold the vault's key, the database's address and its own key.
LENT = ("PATH", "HOME", "LANG", "LC_ALL", "TMPDIR", "SSL_CERT_FILE")
INSTALL_TIMED_OUT = f"the install did not end within {INSTALL_WITHIN_S}s"
# The shell's own word for a command it could not run.
NOT_STARTED = 127
# A process of a runner that died is no child of this one: whether it left is asked this often.
LEFT_EVERY_S = 0.5
ZOMBIE = "Z"


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
    # When the process this host continues exited on its own before it, as its launch said.
    exits: tuple[float, ...] = ()

    @property
    def state(self) -> HostState:
        """How it is, as the runner's plan reads it."""
        if self.exit is not None:
            return "exited"
        return "running" if self.running else "pending"


# The code is the machine's owner's: nothing fences it. A host is gone when the runner leaves, and
# one a runner that died left behind is stopped by the next before it starts anything.
@dataclass
class Processes:
    """The hosts of this machine, one process each, under one folder."""

    home: Path
    hosts: dict[str, _Host] = field(default_factory=dict[str, _Host])
    is_swept: bool = False

    # The exits a host was launched with are answered back, as a pod's annotation is: until 2026-11
    # they were dropped here, so a process that kept exiting was run again for ever on this place,
    # which is the one `setup` writes for a laptop.
    async def list_running(self, env: str) -> list[Container]:
        """Every host of the env this runner started, running or not."""
        await self._sweep_once()
        return [
            Container(
                name=name,
                app=host.app,
                release=host.release,
                state=host.state,
                started_at=host.started_at,
                exits=host.exits,
            )
            for name, host in self.hosts.items()
            if host.env == env
        ]

    async def start(self, launch: Launch, environment: Mapping[str, str]) -> None:
        """The release laid down in the host's folder, then installed and run on a task of its own."""
        await self._sweep_once()
        folder = self.home / launch.host
        try:
            await asyncio.to_thread(_lay_down, launch.source, folder)
        except (OSError, tarfile.TarError) as failed:
            raise UpstreamError(f"the release could not be laid down on this machine: {failed}") from failed
        started = time.time() + INSTALL_WITHIN_S
        host = _Host(launch.app, launch.env, launch.release, folder, started, exits=tuple(launch.exits))
        self.hosts[launch.host] = host
        host.task = asyncio.create_task(_run(host, launch, environment))

    async def stop(self, name: str, grace_s: int = DRAIN_S) -> None:
        """SIGTERM, then grace_s before the kill; its folder goes with it."""
        host = self.hosts.pop(name, None)
        if host is not None:
            host.stopping = True
            if host.child is not None:
                await _end(host.child, grace_s)
            if host.task is not None:
                await asyncio.gather(host.task, return_exceptions=True)
        await asyncio.to_thread(shutil.rmtree, self.home / name, True)

    async def read_logs(self, name: str, lines: int) -> str:
        """The last lines the host printed, its install's first."""
        host = self.hosts.get(name)
        if host is None or not host.lines:
            return ""
        return "\n".join(list(host.lines)[-lines:]) + "\n"

    async def close(self) -> None:
        """Every host drained and stopped: on this machine an app does not outlive its runner."""
        await asyncio.gather(*(self.stop(name) for name in list(self.hosts)))

    # Once, before this runner holds anything, so it never takes a host of its own for a leftover.
    async def _sweep_once(self) -> None:
        if not self.is_swept:
            self.is_swept = True
            await asyncio.to_thread(_sweep, self.home)


# A command this machine cannot start (no sh, no npm) is the host's exit, with the reason as its output.
async def _run(host: _Host, launch: Launch, environment: Mapping[str, str]) -> None:
    try:
        await _install_then_run(host, launch, environment)
    except OSError as failed:
        host.lines.append(str(failed))
        host.exit = NOT_STARTED


# A stop while it installs leaves it there: what was installed never runs.
async def _install_then_run(host: _Host, launch: Launch, environment: Mapping[str, str]) -> None:
    lent = {name: os.environ[name] for name in LENT if name in os.environ}
    release = host.folder / RELEASE
    script = f"{DEPENDENCIES} && {install_cli(str(host.folder / CLI))}"
    install = await _spawn(host, ["sh", "-c", script], release, lent)
    try:
        code = await asyncio.wait_for(_follow(install, host), INSTALL_WITHIN_S)
    except TimeoutError:
        await _end(install, 0)
        host.lines.append(INSTALL_TIMED_OUT)
        code = 1
    if code != 0 or host.stopping:
        host.exit = code
        return
    command = [str(host.folder / CLI / "bin" / "pinecall"), *launch.arguments]
    process = await _spawn(host, command, release, {**lent, "NO_COLOR": "1", **environment})
    host.running, host.started_at = True, time.time()
    await asyncio.to_thread((host.folder / PID).write_text, f"{process.pid} {_start_of(process.pid) or ''}")
    host.exit = await _follow(process, host)


# Its own session, so a signal reaches every process it starts (the CLI starts the agent's).
async def _spawn(host: _Host, command: list[str], cwd: Path, environment: dict[str, str]) -> asyncio.subprocess.Process:
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


async def _follow(child: asyncio.subprocess.Process, host: _Host) -> int:
    if child.stdout is not None:
        async for line in child.stdout:
            host.lines.append(line.decode(errors="replace").rstrip("\n"))
    return await child.wait()


async def _end(child: asyncio.subprocess.Process, grace_s: int) -> None:
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
def _lay_down(source: bytes, folder: Path) -> None:
    shutil.rmtree(folder, ignore_errors=True)
    (folder / RELEASE).mkdir(parents=True)
    with tarfile.open(fileobj=io.BytesIO(source), mode="r:gz") as tarball:
        tarball.extractall(folder / RELEASE, filter="data")


# What a runner that died left: every process told to stop at once, one drain waited for all of
# them, then what is left killed and the folders removed. Until 2026-11 each was waited for in turn,
# up to a drain apiece. A number in `host.pid` is signalled only while the machine says the process
# under it started when the host's did: after a restart of the machine it may be anybody's.
def _sweep(home: Path) -> None:
    if not home.is_dir():
        return
    folders = list(home.iterdir())
    left = [pid for folder in folders if (pid := _find_leftover(folder)) is not None]
    for pid in left:
        _signal(pid, signal.SIGTERM)
    deadline = time.monotonic() + DRAIN_S
    while any(_alive(pid) for pid in left) and time.monotonic() < deadline:
        time.sleep(LEFT_EVERY_S)
    for pid in left:
        _signal(pid, signal.SIGKILL)
    for folder in folders:
        shutil.rmtree(folder, ignore_errors=True)


# The process a dead runner left in a host's folder, when it is still that process.
def _find_leftover(folder: Path) -> int | None:
    named = folder / PID
    if not named.is_file():
        return None
    number, _, started = named.read_text().partition(" ")
    pid = int(number) if number.strip().isdigit() else 0
    if pid <= 0 or (started.strip() and _start_of(pid) != started.strip()):
        return None
    return pid


# Linux alone says it (`/proc/<pid>/stat`, after the command's closing parenthesis); elsewhere
# nothing is recorded and the number is taken as it is, as before.
def _start_of(pid: int) -> str | None:
    try:
        return Path(f"/proc/{pid}/stat").read_text().rpartition(")")[2].split()[STARTED_FIELD]
    except (OSError, IndexError):
        return None


# A process that ended and nobody reaped yet still answers a signal: on Linux its state says so.
def _alive(pid: int) -> bool:
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    try:
        state = Path(f"/proc/{pid}/stat").read_text().rpartition(")")[2].split()[0]
    except (OSError, IndexError):
        return True
    return state != ZOMBIE
