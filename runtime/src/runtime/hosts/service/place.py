"""Where a runner runs its hosts, whatever runs them: a host as it stands, a launch, and what a place does."""

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Literal, Protocol

# What a drain needs: ten seconds for the gateway, thirty for the slowest tool.
DRAIN_S = 45
# The install runs the org's own scripts, on a clock.
INSTALL_WITHIN_S = 300

# How a host is, in the runner's own words: each place says its own (a pod's phase, a process's exit)
# as one of these. Until 2026-11 the words were a pod's, and this machine's processes spoke them.
type HostState = Literal["pending", "running", "exited"]


@dataclass(frozen=True, slots=True)
class Container:
    """A host the runner started: its name, its app and release, how it is."""

    name: str
    app: str
    release: int
    state: HostState
    started_at: float
    # The place is taking the host away (a node drained, `kubectl delete`): it exits by no fault of its own.
    deleting: bool = False
    # The place threw the host off (a pod evicted for memory or disk) and left it there, ended.
    evicted: bool = False
    # When the process this host continues exited on its own before it: what still counts towards giving up.
    exits: tuple[float, ...] = ()

    @property
    def has_exited(self) -> bool:
        """Whether its process ended; one still installing or starting has not."""
        return self.state == "exited"

    @property
    def crashed(self) -> bool:
        """Whether its process ended on its own: not taken, not evicted."""
        return self.has_exited and not self.deleting and not self.evicted


@dataclass(frozen=True, slots=True)
class Launch:
    """One host to start: whose, which release, its sources and their digest, what `pinecall` is run with."""

    env: str
    app: str
    host: str
    release: int
    sha256: str
    source: bytes
    arguments: Sequence[str]
    # The exits of the process this host continues, kept where the place keeps them for the next runner.
    exits: tuple[float, ...] = ()


class Hosts(Protocol):
    """Where an env's hosts run: the hosting cluster's pods, or this machine's processes."""

    async def list_running(self, env: str) -> list[Container]:
        """Every host of the env this runner started, running or not."""
        ...

    async def start(self, launch: Launch, environment: Mapping[str, str]) -> None:
        """Install the release and run the host, with this environment."""
        ...

    async def stop(self, name: str, grace_s: int = DRAIN_S) -> None:
        """SIGTERM, then grace_s before the kill."""
        ...

    async def read_logs(self, name: str, lines: int) -> str:
        """The last lines the host printed; its install's, when it never got to run."""
        ...

    async def close(self) -> None:
        """The runner leaves."""
        ...
