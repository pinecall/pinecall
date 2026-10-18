"""A hosted app's pod as the runner starts it: its install, run by sh over a release, its tools faked."""

import os
import stat
import subprocess
from pathlib import Path

import pytest

from pinecall_runtime.hosting.service.cluster import CLI_HOME, INSTALL
from pinecall_runtime.hosting.service.hosts import NO_UV

# Each tool the install calls says how it was called; `node` fetches nothing, and `tar` lays the
# release down where `-C` says, as the real pipe would.
FAKES = {
    "node": "exit 0",
    "tar": 'while [ "$1" != "-C" ]; do shift; done; cp -R "$RELEASE"/. "$2"/',
    "uv": 'echo "uv $*"',
    "npm": 'echo "npm $*"',
    "corepack": 'echo "corepack $*"',
}
CLI = f"npm install -g --prefix {CLI_HOME} --no-audit --no-fund pinecall@"


def _installed(tmp_path: Path, files: list[str], *, without: str | None = None) -> subprocess.CompletedProcess[str]:
    tools = tmp_path / "bin"
    tools.mkdir()
    for name, body in FAKES.items():
        if name == without:
            continue
        tool = tools / name
        tool.write_text(f"#!/bin/sh\n{body}\n")
        tool.chmod(tool.stat().st_mode | stat.S_IEXEC)
    release, app = tmp_path / "release", tmp_path / "app"
    for path in files:
        (release / path).parent.mkdir(parents=True, exist_ok=True)
        (release / path).touch()
    app.mkdir()
    script = INSTALL.replace(" /app", f" {app}")
    environment = {**os.environ, "PATH": f"{tools}:/usr/bin:/bin", "RELEASE": str(release)}
    return subprocess.run(["sh", "-c", script], capture_output=True, text=True, env=environment, check=False)


def test_a_python_release_is_synced_by_uv_from_its_lock_then_the_cli_installed(tmp_path: Path) -> None:
    done = _installed(tmp_path, ["agents/front/agent.py", "pyproject.toml", "uv.lock"])
    assert done.returncode == 0, done.stderr
    assert done.stdout.splitlines()[0] == "uv sync --frozen --no-dev"
    assert done.stdout.splitlines()[1].startswith(CLI)


def test_a_python_release_with_no_lock_is_resolved_from_its_pyproject(tmp_path: Path) -> None:
    done = _installed(tmp_path, ["agents/front/agent.py", "pyproject.toml"])
    assert done.stdout.splitlines()[0] == "uv sync --no-dev"


@pytest.mark.parametrize(
    ("lockfile", "installed"),
    [
        ("pnpm-lock.yaml", "corepack pnpm install --frozen-lockfile --prod"),
        ("package-lock.json", "npm ci --omit=dev --no-audit --no-fund"),
        ("package.json", "npm install --omit=dev --no-audit --no-fund"),
    ],
)
def test_a_typescript_release_is_installed_the_way_its_lockfile_says(
    tmp_path: Path, lockfile: str, installed: str
) -> None:
    done = _installed(tmp_path, ["agents/front/agent.tsx", lockfile])
    assert done.returncode == 0, done.stderr
    assert done.stdout.splitlines()[0] == installed


def test_a_python_release_on_an_image_with_no_uv_fails_its_install_and_says_why(tmp_path: Path) -> None:
    done = _installed(tmp_path, ["agents/front/agent.py", "pyproject.toml"], without="uv")
    assert done.returncode != 0
    assert NO_UV in done.stderr
    assert CLI not in done.stdout
