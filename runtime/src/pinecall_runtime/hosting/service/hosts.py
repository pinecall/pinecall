"""Where a runner runs its hosts, whatever runs them: a host, a launch, the install, and what each place does."""

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Protocol

# What a drain needs: ten seconds for the gateway, thirty for the slowest tool.
DRAIN_S = 45
# The install runs the org's own scripts, on a clock.
INSTALL_WITHIN_S = 300
# What a host whose process is over is in; one still installing or starting has not exited.
ENDED = frozenset({"Succeeded", "Failed"})
# The `pinecall` a hosted project is started with: the platform's own, never a dependency of the
# project. A range, so a CLI release reaches hosted projects on their next start with no runtime
# release; a CLI that breaks its contract bumps the minor, and this line with it.
CLI_VERSION = "^0.11.0"

# A Node project's dependencies, the way its lockfile says; npm resolves what package.json names
# when there is none.
NODE_DEPENDENCIES = (
    "if [ -f pnpm-lock.yaml ]; then corepack pnpm install --frozen-lockfile --prod; "
    "elif [ -f package-lock.json ]; then npm ci --omit=dev --no-audit --no-fund; "
    "else npm install --omit=dev --no-audit --no-fund; fi"
)
# Inside single quotes in the script: no apostrophe.
NO_UV = "a Python release is installed with uv, and the machine installing it has none (infra/images/app)"
# A Python project's into its own .venv, which `pinecall start` runs the agent with.
PYTHON_DEPENDENCIES = (
    f"{{ command -v uv >/dev/null || {{ echo '{NO_UV}' >&2; exit 1; }}; }} && "
    "if [ -f uv.lock ]; then uv sync --frozen --no-dev; else uv sync --no-dev; fi"
)
# Run in the release's folder: its dependencies in the language of its agents (the CLI uploads one).
DEPENDENCIES = f"if ls agents/*/agent.py >/dev/null 2>&1; then {PYTHON_DEPENDENCIES}; else {NODE_DEPENDENCIES}; fi"


@dataclass(frozen=True, slots=True)
class Container:
    """A host the runner started: its name, its app and release, how it is."""

    name: str
    app: str
    release: int
    state: str
    started_at: float

    @property
    def has_exited(self) -> bool:
        """Whether its process ended; one still installing or starting has not."""
        return self.state in ENDED


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


class Hosts(Protocol):
    """Where an env's hosts run: the hosting cluster's pods, or this machine's processes."""

    async def running(self, env: str) -> list[Container]:
        """Every host of the env this runner started, running or not."""
        ...

    async def start(self, launch: Launch, environment: Mapping[str, str]) -> None:
        """Install the release and run the host, with this environment."""
        ...

    async def stop(self, name: str, grace_s: int = DRAIN_S) -> None:
        """SIGTERM, then grace_s before the kill."""
        ...

    async def logs(self, name: str, lines: int) -> str:
        """The last lines the host printed; its install's, when it never got to run."""
        ...

    async def close(self) -> None:
        """The runner leaves."""
        ...


def cli_installed(prefix: str) -> str:
    """The platform's own `pinecall`, installed under `prefix`."""
    return f"npm install -g --prefix {prefix} --no-audit --no-fund pinecall@{CLI_VERSION}"
