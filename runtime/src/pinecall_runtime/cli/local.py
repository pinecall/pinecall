"""`local`: the runtime whole on one machine: the services in Docker, the schema, the gateway and a worker."""

import asyncio
import base64
import os
import secrets
import socket
import subprocess
import sys
import time
from collections.abc import Sequence
from importlib.resources import files
from pathlib import Path
from shutil import which
from typing import Annotated

import typer

from pinecall_runtime.accounts.models import DEFAULT_ORG
from pinecall_runtime.accounts.service import keys
from pinecall_runtime.cli import orgs, processes
from pinecall_runtime.cli import setup_server as server_
from pinecall_runtime.cli.command import OK, Context, context_of, verb
from pinecall_runtime.config import Settings
from pinecall_runtime.enums import Env, KeyScope, Role
from pinecall_runtime.exceptions import ConfigurationError, UpstreamError
from pinecall_runtime.platform import service as platform
from pinecall_runtime.postgres import create_engine, session_maker

app = typer.Typer(help="the runtime whole on this machine, for developing an agent", no_args_is_help=True)

# Where one machine keeps its local runtime: the compose files, the database's name, the secrets.
DEFAULT_DIR = Path.home() / ".pinecall-runtime" / "local"
# What the package ships for Docker, written into that directory as they are here. Read as files of
# the `cli` package under `local/`: `cli.local` is this module to importlib (found on a clean machine, 2026-10-17).
SHIPPED = (
    "compose.yaml",
    "livekit.yaml",
    "sip.yaml",
    "postgres/Dockerfile",
    "postgres/extensions.sql",
    "models.yaml",
    "models.gpu.yaml",
    "providers.local.json",
    "prices.csv",
    "prices.LICENSE",
    "models.csv",
)
SERVICES = ("postgres", "redis", "livekit")
GATEWAY_URL = "http://127.0.0.1:8080"
# The ports the compose publishes on loopback, as the settings name them, by the service's name.
PORTS: dict[str, tuple[int, str]] = {
    "Postgres": (55433, "postgres"),
    "Redis": (56380, "redis"),
    "LiveKit": (7880, "livekit"),
}
# Docker says a container is healthy before the host's side of its port answers: a moment, on a Mac.
PORTS_WITHIN_S = 60.0
NO_DOCKER = (
    "Docker is not here: install Docker Desktop (macOS, Windows) or Docker Engine with the compose "
    "plugin, start it, and run this again"
)
COMPOSE_FAILED = "docker compose could not bring the services up:\n{output}"
NOT_ANSWERING = "{service} did not answer on 127.0.0.1:{port} within {seconds:.0f} s: `docker compose ps`"

# The settings the gateway and the worker run on here: the services on loopback, a dev LiveKit pair, secrets drawn once.
SETTINGS = """DATABASE_URL=postgresql://pinecall:pinecall@127.0.0.1:55433/pinecall
PINECALL_REDIS_URL=redis://127.0.0.1:56380/0
LIVEKIT_URL=ws://127.0.0.1:7880
LIVEKIT_API_KEY=devkey
LIVEKIT_API_SECRET=a-laptop-only-livekit-secret-0123456789
PINECALL_GATEWAY_URL={gateway}
PINECALL_RECORDINGS={recordings}
PINECALL_FLEET=pinecall-sandbox
PINECALL_MAX_JOBS=4
PINECALL_WORKER_HTTP_PORT=8182
PINECALL_VAULT_KEY={vault}
PINECALL_OPS_KEY=pc_ops_{ops}
PINECALL_TOKEN_KEY={token}
{listen}"""
# On Linux, host.docker.internal is Docker's bridge, not loopback: LiveKit's webhooks need a gateway on every interface.
LISTEN_EVERYWHERE = "PINECALL_GATEWAY_LISTEN=0.0.0.0:8080\n" if sys.platform == "linux" else ""
UP = "local · Postgres :55433 · Redis :56380 · LiveKit :7880 · settings in {env}\nconsole   {gateway}/sandbox/"
FIRST = "  a runtime nobody set up yet: `pinecall-runtime setup` makes its admin and signs this machine in"
SERVING = "{name}: up, kept up by Docker across reboots · logs: pinecall-runtime local logs"
# Every profile the two compose files name, so `down` stops a server's services too.
ALL_PROFILES = ("phone", "server", "server-livekit", "server-phone")
DOWN = "local: the services stopped; the database and {env} are kept"
WIPED = "local: the services stopped and the database deleted; {env} is kept"

Dir = Annotated[Path, typer.Option("--dir", help="Where this machine keeps its local runtime.")]


# `local [--dir <path>] <verb>`: the directory stands before the verb, as the page says.
@app.callback()
def local_group(ctx: typer.Context, where: Dir = DEFAULT_DIR) -> None:
    """The runtime whole on this machine, for developing an agent."""
    ctx.meta["dir"] = where


def _where(ctx: typer.Context) -> Path:
    return Path(ctx.meta["dir"])


@app.command("up")
@verb
async def local_up(
    ctx: typer.Context,
    services_only: Annotated[bool, typer.Option("--services-only", help="The services and the schema alone.")] = False,
) -> int:
    """The services up, the schema at this release, the secrets drawn once, the gateway and a worker; a server's too."""
    context = context_of(ctx)
    where = _where(ctx)
    compose = write_shipped(where)
    docker_or_refuse()
    env = where / "env"
    values = read_env(env)
    server = server_.from_the_env(values)
    services_up(compose, ("postgres", "redis") if server else SERVICES)
    history = await prepare_database(values, env, production_fleet=server is not None)
    if server is not None:
        server_.bring_up(where, server, values, None, build=False)
        server_.wait_for_https(server.name)
        context.out.line(SERVING.format(name=f"https://{server.name}"))
        return OK
    context.out.line(UP.format(env=env, gateway=GATEWAY_URL))
    if history.applied:
        context.out.line(FIRST)
    if services_only:
        return OK
    return processes.run_both(context.out, values, ["gateway"], ["worker", "start"])


def services_up(compose: Path, services: Sequence[str]) -> None:
    """`docker compose up` of those services, waited for, and each one's loopback port answering."""
    up = subprocess.run(
        ["docker", "compose", "--progress", "quiet", "-f", str(compose), "up", "-d", "--build", "--wait", *services],
        capture_output=True,
        text=True,
        check=False,
    )
    if up.returncode != 0:
        raise UpstreamError(COMPOSE_FAILED.format(output=(up.stderr or up.stdout).strip()[-2000:]))
    for name, (port, service) in PORTS.items():
        if service in services:
            wait_for_port(name, port)


async def prepare_database(values: dict[str, str], env: Path, *, production_fleet: bool = False) -> platform.History:
    """The schema at this release; the sandbox fleet's key, and a server's production fleet's, drawn once into env."""
    # The revisions read the process's own settings (`migrations/env.py`, `load_settings`): the local settings
    # become the process's here, as they are the children's (a clean machine reached for localhost:5432, 2026-10-17).
    os.environ.update(values)
    engine = create_engine(settings_of(values), pool_size=3)
    try:
        history = await platform.apply_history(engine)
        await asyncio.to_thread(platform.upgrade_schema, tracked=history.tracked)
        fleets = [("PINECALL_WORKER_KEY", Env.sandbox, "the sandbox fleet")]
        if production_fleet:
            fleets.append(("PINECALL_PRODUCTION_WORKER_KEY", Env.production, "the production fleet"))
        for variable, fleet_env, label in fleets:
            if variable in values:
                continue
            issue = keys.Issue(org=DEFAULT_ORG, env=fleet_env, scopes=frozenset({KeyScope.fleet}), label=label)
            async with session_maker(engine).begin() as session:
                _, values[variable] = await keys.issue_key(session, issue)
            with env.open("a", encoding="utf-8") as out:
                out.write(f"{variable}={values[variable]}\n")
    finally:
        await engine.dispose()
    return history


@app.command("down")
@verb
async def local_down(
    ctx: typer.Context,
    volumes: Annotated[bool, typer.Option("--volumes", help="Delete the database too.")] = False,
) -> int:
    """Stop the services; the database's volume stays unless `--volumes`."""
    where = _where(ctx)
    docker_or_refuse()
    wiped = ["-v"] if volumes else []
    profiles = [option for profile in ALL_PROFILES for option in ("--profile", profile)]
    subprocess.run([*compose_files(where), *profiles, "down", *wiped], check=True)
    context_of(ctx).out.line((WIPED if volumes else DOWN).format(env=where / "env"))
    return OK


@app.command("logs")
@verb
async def local_logs(
    ctx: typer.Context,
    service: Annotated[str | None, typer.Argument(help="gateway, worker-sandbox, worker-production, caddy…")] = None,
) -> int:
    """Follow a server's logs, every service's or one's; a laptop's are in the terminal `setup` runs in."""
    where = _where(ctx)
    docker_or_refuse()
    profiles = [option for profile in ALL_PROFILES for option in ("--profile", profile)]
    named = [service] if service else []
    return subprocess.run(
        [*compose_files(where), *profiles, "logs", "--follow", "--tail", "100", *named], check=False
    ).returncode


@app.command("init")
@verb
async def local_init(
    ctx: typer.Context,
    email: Annotated[str, typer.Option("--email")],
    person: Annotated[str, typer.Option("--person", help="The person's name.")],
    org: Annotated[str, typer.Option("--org", help="The org's slug.")] = DEFAULT_ORG,
    name: Annotated[str | None, typer.Option("--name", help="What to call the org (default: the slug).")] = None,
    role: Annotated[Role, typer.Option("--role")] = orgs.THE_FIRST_ROLE,
) -> int:
    """The first org and person, on the local gateway: `init` on the local settings."""
    context = context_of(ctx)
    local = Context(settings_of(read_env(_where(ctx) / "env")), context.out)
    async with local.stack:
        return await orgs.initialize(local, org=org, name=name, email=email, person=person, role=role)


@app.command("env")
@verb
async def local_env(ctx: typer.Context) -> int:
    """Print the line a shell runs to use the local settings with any other verb."""
    context_of(ctx).out.secret(f"set -a; . {_where(ctx) / 'env'}; set +a")
    return OK


def compose_files(where: Path) -> list[str]:
    """`docker compose` on the services' file, and the server's laid over it where this machine is one."""
    server = where / "server.yaml"
    return ["docker", "compose", "-f", str(where / "compose.yaml"), *(["-f", str(server)] if server.is_file() else [])]


def set_values(env: Path, changes: dict[str, str | None]) -> dict[str, str]:
    """The env file with those names set (None: taken out), every other line kept; the pairs it now holds."""
    kept = [line for line in env.read_text(encoding="utf-8").splitlines() if line.partition("=")[0] not in changes]
    kept += [f"{name}={value}" for name, value in changes.items() if value is not None]
    env.write_text("\n".join(kept) + "\n", encoding="utf-8")
    return read_env(env)


def write_shipped(where: Path) -> Path:
    """Write the compose files the package ships and the settings once; the compose file's path."""
    shipped = files("pinecall_runtime.cli").joinpath("local")
    for name in SHIPPED:
        target = where / name
        target.parent.mkdir(parents=True, exist_ok=True)
        content = shipped.joinpath(name).read_text(encoding="utf-8")
        if not target.is_file() or target.read_text(encoding="utf-8") != content:
            target.write_text(content, encoding="utf-8")
    (where / "recordings").mkdir(exist_ok=True)
    env = where / "env"
    if not env.is_file():
        env.touch(mode=0o600)
        env.write_text(
            SETTINGS.format(
                gateway=GATEWAY_URL,
                recordings=where / "recordings",
                vault=base64.urlsafe_b64encode(secrets.token_bytes(32)).decode(),
                ops=secrets.token_hex(24),
                token=secrets.token_hex(32),
                listen=LISTEN_EVERYWHERE,
            ),
            encoding="utf-8",
        )
    return where / "compose.yaml"


def wait_for_port(service: str, port: int, within_s: float = PORTS_WITHIN_S) -> None:
    """Wait until the service accepts a connection on its loopback port, or say that it did not."""
    deadline = time.monotonic() + within_s
    while True:
        try:
            with socket.create_connection(("127.0.0.1", port), timeout=1.0):
                return
        except OSError:
            if time.monotonic() > deadline:
                raise UpstreamError(NOT_ANSWERING.format(service=service, port=port, seconds=within_s)) from None
            time.sleep(0.5)


def read_env(env: Path) -> dict[str, str]:
    """The settings file as `NAME=value` pairs."""
    pairs = (line.partition("=") for line in env.read_text(encoding="utf-8").splitlines())
    return {name: value for name, _, value in pairs if name and not name.startswith("#")}


def settings_of(values: dict[str, str]) -> Settings:
    """The runtime's settings from those pairs, over the process's own environment."""
    variables = {**os.environ, **values}
    return Settings.model_validate({**variables, "variables": variables})


def docker_or_refuse() -> None:
    """Docker on PATH, or the sentence that says what to install."""
    if which("docker") is None:
        raise ConfigurationError(NO_DOCKER)
