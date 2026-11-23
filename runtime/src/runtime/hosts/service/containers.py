"""This machine's containers as the runner drives them: a sandboxed container a host, for code not the owner's."""

import asyncio
import json
import os
import time
from collections.abc import Awaitable, Callable, Mapping, Sequence
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any

from runtime.exceptions import UpstreamError
from runtime.hosts.service.cluster import (
    A_VARIABLE,
    APP_ANNOTATION,
    ENV_LABEL,
    EXITS_ANNOTATION,
    RELEASE_LABEL,
    RESOLVERS,
)
from runtime.hosts.service.install import DEPENDENCIES, install_cli
from runtime.hosts.service.place import DRAIN_S, INSTALL_WITHIN_S, Container, HostState, Launch

# A host is two containers, as a pod's two are: the install, which runs the org's own scripts and
# ends, then the app. Both carry the host's name and which of the two they are.
HOST_LABEL = "pinecall.io/host"
STAGE_LABEL = "pinecall.io/stage"
INSTALL = "install"
APP = "app"
# What an app may take, as a pod's limits say it (cluster.py): its memory, the install's, its
# processes, the one writable place it has besides its install.
MEMORY = "256m"
INSTALL_MEMORY = "1g"
CPUS = "0.5"
PROCESSES = 512
SCRATCH = "/scratch"
SCRATCH_SIZE = "64m"
# The user every container of an org's code runs as: never root, the image's own `node`.
APP_USER = 1000
CLI_HOME = "/opt/pinecall"
INSTALL_HOME = "/home/app"
# A year no container started in: what Docker says of one it has not started yet.
NEVER_STARTED = "0001"
# The release arrives on the install's own input: no folder of this machine is an app's to read.
# One stream, so `logs` reads the lines in the order they were printed.
INSTALL_SCRIPT = f"{{ tar -xz -C /app && cd /app && {DEPENDENCIES} && {install_cli(CLI_HOME)}; }} 2>&1"
RUN_SCRIPT = 'exec "$@" 2>&1'
# Installs under way at once: each may take half a core, so two a core fill the machine and a
# third would only make all of them late. The rest wait their turn, and their clock with them.
INSTALLS_AT_ONCE = 2 * (os.cpu_count() or 1)
# The docker command is given this long past the install's own clock before it is taken away.
PAST_THE_INSTALL_S = 30
NO_SANDBOX = "this machine's Docker has no runtime named {runtime}: an app never runs here without its sandbox"
NO_NETWORK = "this machine's Docker has no network named {network}: an app never runs here outside its fence"
REFUSED = "docker {verb}: {said}"


@dataclass(frozen=True, slots=True)
class Ran:
    """What a `docker` command left: its exit, and what it printed on each stream."""

    code: int
    out: str
    err: str = ""


type Docker = Callable[[Sequence[str], bytes | None, Mapping[str, str] | None], Awaitable[Ran]]


# A value never rides the command line, where every user of the machine reads it: a variable is
# named with `-e NAME` and its value is in this command's own environment.
async def run_docker(
    arguments: Sequence[str], given: bytes | None = None, environment: Mapping[str, str] | None = None
) -> Ran:
    """`docker` run to its end, `given` on its input and `environment` added to its own."""
    try:
        child = await asyncio.create_subprocess_exec(
            "docker",
            *arguments,
            stdin=asyncio.subprocess.PIPE if given is not None else asyncio.subprocess.DEVNULL,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            env={**os.environ, **environment} if environment else None,
        )
    except OSError as failed:
        raise UpstreamError(f"docker could not be run on this machine: {failed}") from failed
    out, err = await child.communicate(given)
    return Ran(child.returncode or 0, out.decode(errors="replace"), err.decode(errors="replace"))


@dataclass
class _Install:
    """An install under way: its task, what it installs, and when it was asked for."""

    launch: Launch
    # When its turn came; until then it waits behind the installs that are under way.
    began_at: float | None = None
    # A host of this name was already installed, and well: its volumes are run as they are.
    is_installed: bool = False
    task: asyncio.Task[None] | None = None


# Nothing is held here but the installs under way: a host is what Docker says it is, so the apps
# outlive their runner, as a pod does, and the next runner finds them by their labels.
@dataclass
class Containers:
    """The hosts of this machine, a sandboxed container each: no root, no capability, its own network."""

    image: str
    # Docker's name for the sandbox every container runs under (gVisor's `runsc`, registered).
    runtime: str
    # The network the apps are on: fenced from this machine, its neighbours and one another.
    network: str
    # The public resolvers as a file of this runner's, read-only in every container: on a network
    # of its own Docker answers names itself, at an address gVisor's network never reaches.
    resolvers: Path
    cpus: str = CPUS
    docker: Docker = run_docker
    installing: dict[str, _Install] = field(default_factory=dict[str, _Install])
    turns: asyncio.Semaphore = field(default_factory=lambda: asyncio.Semaphore(INSTALLS_AT_ONCE))
    is_checked: bool = False

    # A host asked for a moment ago has no container yet (its volumes are being made): it is listed
    # as one that installs, or the next beat would take it for gone and start it again.
    async def list_running(self, env: str) -> list[Container]:
        """Every host of the env on this machine, running or not."""
        named = await self.docker(
            ["ps", "-a", "--filter", f"label={ENV_LABEL}={env}", "--format", "{{.Names}}"], None, None
        )
        if named.code != 0:
            raise UpstreamError(REFUSED.format(verb="ps", said=named.err.strip()[:500]))
        names = named.out.split()
        by_host: dict[str, list[dict[str, Any]]] = {}
        if names:
            # One that left between the two commands is an error on the other stream, and not in the list.
            read = await self.docker(["inspect", *names], None, None)
            for found in json.loads(read.out or "[]"):
                by_host.setdefault(found["Config"]["Labels"][HOST_LABEL], []).append(found)
        listed = [container_of(host, found, installing=host in self.installing) for host, found in by_host.items()]
        asked = [
            Container(
                name=host,
                app=held.launch.app,
                release=held.launch.release,
                state="pending",
                started_at=(held.began_at or time.time()) + INSTALL_WITHIN_S,
                exits=tuple(held.launch.exits),
            )
            for host, held in self.installing.items()
            if held.launch.env == env and host not in by_host
        ]
        return sorted([*listed, *asked], key=lambda each: each.name)

    async def start(self, launch: Launch, environment: Mapping[str, str]) -> None:
        """The host's volumes made, then its release installed and run on a task of its own."""
        await self._check_once()
        for name in environment:
            if not A_VARIABLE.match(name):
                raise UpstreamError(f"{name!r} is not an environment variable's name")
        held = _Install(launch)
        self.installing[launch.host] = held
        try:
            held.is_installed = await self._make_ready(launch.host)
        except UpstreamError:
            del self.installing[launch.host]
            raise
        held.task = asyncio.create_task(self._install_then_run(launch, dict(environment)))

    async def stop(self, name: str, grace_s: int = DRAIN_S) -> None:
        """SIGTERM, then grace_s before the kill; its containers and its volumes go with it."""
        held = self.installing.pop(name, None)
        if held is not None and held.task is not None:
            held.task.cancel()
            await asyncio.gather(held.task, return_exceptions=True)
        await self.docker(["stop", "-t", str(grace_s), name], None, None)
        await self._remove(name)

    async def read_logs(self, name: str, lines: int) -> str:
        """The last lines the host printed; its install's, when it never got to run."""
        for container in (name, _install_of(name)):
            read = await self.docker(["logs", "--tail", str(lines), container], None, None)
            if read.code == 0 and read.out:
                return read.out
        return ""

    async def close(self) -> None:
        """The runner leaves its hosts running; an install under way is left for the next to judge."""
        tasks = [held.task for held in self.installing.values() if held.task is not None]
        self.installing.clear()
        for task in tasks:
            task.cancel()
        await asyncio.gather(*tasks, return_exceptions=True)

    # Asked once: a machine whose Docker lacks the sandbox or the fence starts no app at all.
    async def _check_once(self) -> None:
        if self.is_checked:
            return
        known = await self.docker(["info", "--format", "{{json .Runtimes}}"], None, None)
        if known.code != 0 or self.runtime not in json.loads(known.out or "{}"):
            raise UpstreamError(NO_SANDBOX.format(runtime=self.runtime))
        if (await self.docker(["network", "inspect", self.network], None, None)).code != 0:
            raise UpstreamError(NO_NETWORK.format(network=self.network))
        await asyncio.to_thread(_write_resolvers, self.resolvers)
        self.is_checked = True

    # A host's name says its app and its release, so an install of that name that ended well is this
    # release installed: a runner started again runs it as it is, and installs nothing twice. A new
    # volume is root's: the image's own `chown` gives the three to the app's user, as root with that
    # one capability and no network, before any of the org's code has run.
    async def _make_ready(self, host: str) -> bool:
        before = await self.docker(
            ["inspect", "--format", "{{.State.Status}} {{.State.ExitCode}}", _install_of(host)], None, None
        )
        if before.code == 0 and before.out.split() == ["exited", "0"]:
            await self.docker(["rm", "-f", host], None, None)
            return True
        await self._remove(host)
        volumes = _volumes(host)
        for volume in volumes:
            await self._do("volume create", ["volume", "create", "--label", f"{HOST_LABEL}={host}", volume])
        await self._do(
            "run",
            [
                *("run", "--rm", "--runtime", self.runtime, "--network", "none", "--user", "0:0", "--read-only"),
                *("--cap-drop", "ALL", "--cap-add", "CHOWN", "--security-opt", "no-new-privileges"),
                *_mounts(volumes, read_only=False, home=True),
                *(self.image, "chown", f"{APP_USER}:{APP_USER}", "/app", CLI_HOME, INSTALL_HOME),
            ],
        )
        return False

    async def _do(self, verb: str, arguments: Sequence[str]) -> None:
        ran = await self.docker(arguments, None, None)
        if ran.code != 0:
            raise UpstreamError(REFUSED.format(verb=verb, said=(ran.err or ran.out).strip()[:500]))

    # Whatever a host of this name left: nothing of it is an error to find gone.
    async def _remove(self, host: str) -> None:
        await self.docker(["rm", "-f", host, _install_of(host)], None, None)
        await self.docker(["volume", "rm", "-f", *_volumes(host)], None, None)

    # A stop while it installs leaves it there: what was installed never runs. An app that Docker
    # would not start stays as its install alone, which the listing reads as a host that exited.
    async def _install_then_run(self, launch: Launch, environment: dict[str, str]) -> None:
        volumes = _volumes(launch.host)
        install = [
            *("run", "-i", "--name", _install_of(launch.host)),
            *self._fence(launch, INSTALL, INSTALL_MEMORY),
            *_mounts(volumes, read_only=False, home=True),
            *("-e", f"HOME={INSTALL_HOME}", "-e", f"TMPDIR={SCRATCH}"),
            *(self.image, "timeout", str(INSTALL_WITHIN_S), "sh", "-c", INSTALL_SCRIPT),
        ]
        held = self.installing.get(launch.host)
        try:
            if held is None or not held.is_installed:
                async with self.turns:
                    if held is not None:
                        held.began_at = time.time()
                    installed = await asyncio.wait_for(
                        self.docker(install, launch.source, None), INSTALL_WITHIN_S + PAST_THE_INSTALL_S
                    )
                if installed.code != 0:
                    return
            named = [word for name in sorted(environment) for word in ("-e", name)]
            await self.docker(
                [
                    *("run", "-d", "--name", launch.host, "--workdir", "/app"),
                    *self._fence(launch, APP, MEMORY),
                    *_mounts(volumes, read_only=True, home=False),
                    *("-e", f"HOME={SCRATCH}", "-e", f"TMPDIR={SCRATCH}", "-e", "NO_COLOR=1", *named),
                    *(self.image, "sh", "-c", RUN_SCRIPT, "sh", f"{CLI_HOME}/bin/pinecall", *launch.arguments),
                ],
                None,
                environment,
            )
        except TimeoutError:
            await self.docker(["kill", _install_of(launch.host)], None, None)
        finally:
            # Held no longer: what the listing says of this host is now Docker's alone to say.
            now = self.installing.get(launch.host)
            if now is not None and now.task is asyncio.current_task():
                del self.installing[launch.host]

    # What every container of an org's code is run with, the same words a pod's lock-down says: the
    # sandbox, no root, no capability, a root filesystem it cannot write, a ceiling on its memory,
    # its processors and its processes, the apps' own network and public resolvers alone.
    def _fence(self, launch: Launch, stage: str, memory: str) -> list[str]:
        labels = {
            ENV_LABEL: launch.env,
            HOST_LABEL: launch.host,
            STAGE_LABEL: stage,
            APP_ANNOTATION: launch.app,
            RELEASE_LABEL: str(launch.release),
            EXITS_ANNOTATION: ",".join(str(at) for at in launch.exits),
        }
        return [
            *("--runtime", self.runtime, "--user", f"{APP_USER}:{APP_USER}", "--read-only"),
            *("--cap-drop", "ALL", "--security-opt", "no-new-privileges", "--pids-limit", str(PROCESSES)),
            *("--memory", memory, "--memory-swap", memory, "--cpus", self.cpus),
            *("--network", self.network, "-v", f"{self.resolvers}:/etc/resolv.conf:ro"),
            *("--hostname", launch.host[:63], "--restart", "no", "--log-opt", "max-size=5m", "--log-opt", "max-file=2"),
            *("--tmpfs", f"{SCRATCH}:rw,exec,size={SCRATCH_SIZE},uid={APP_USER},gid={APP_USER},mode=0700"),
            *(word for name, value in labels.items() for word in ("--label", f"{name}={value}")),
        ]


def as_cpus(thousandths: str | None) -> str:
    """A pod's `250m` as Docker's `0.25`; unset, the half core an app may take."""
    return CPUS if thousandths is None else str(int(thousandths.removesuffix("m")) / 1000)


def container_of(host: str, found: Sequence[Mapping[str, Any]], *, installing: bool) -> Container:
    """One host's containers, as the runner's plan reads them."""
    by_stage = {each["Config"]["Labels"][STAGE_LABEL]: each for each in found}
    labels = found[0]["Config"]["Labels"]
    exits = tuple(float(at) for at in labels.get(EXITS_ANNOTATION, "").split(",") if at)
    state: HostState
    if APP in by_stage:
        status = by_stage[APP]["State"]["Status"]
        state = "running" if status == "running" else "pending" if status == "created" else "exited"
        started = _seconds(by_stage[APP]["State"]["StartedAt"])
    else:
        # Given the install's time before its registering is timed, as a pod not yet running is. An
        # install that ended well with no runner holding it is one whose runner died: it exited.
        install = by_stage[INSTALL]["State"]
        ended = install["Status"] in ("exited", "dead")
        state = "exited" if ended and (install["ExitCode"] != 0 or not installing) else "pending"
        started = _seconds(install["StartedAt"]) + INSTALL_WITHIN_S
    return Container(
        name=host,
        app=labels[APP_ANNOTATION],
        release=int(labels[RELEASE_LABEL]),
        state=state,
        started_at=started,
        exits=exits,
    )


# Public resolvers, and nothing of this machine's own: no search domain, no resolver of its network.
def _write_resolvers(named: Path) -> None:
    named.parent.mkdir(parents=True, exist_ok=True)
    named.write_text("".join(f"nameserver {resolver}\n" for resolver in RESOLVERS))
    named.chmod(0o644)


def _install_of(host: str) -> str:
    return f"{host}-install"


# The release and what it installed, the platform's CLI, and the install's home (its caches).
def _volumes(host: str) -> tuple[str, str, str]:
    return f"{host}-app", f"{host}-cli", f"{host}-home"


# The app reads what its install wrote and writes none of it; the install's home is the install's alone.
def _mounts(volumes: tuple[str, str, str], *, read_only: bool, home: bool) -> list[str]:
    suffix = ":ro" if read_only else ""
    mounts = ["-v", f"{volumes[0]}:/app{suffix}", "-v", f"{volumes[1]}:{CLI_HOME}{suffix}"]
    return [*mounts, "-v", f"{volumes[2]}:{INSTALL_HOME}"] if home else mounts


def _seconds(stamp: str) -> float:
    if not stamp or stamp.startswith(NEVER_STARTED):
        return time.time()
    return datetime.fromisoformat(stamp).timestamp()
