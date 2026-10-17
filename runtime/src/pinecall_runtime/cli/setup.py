"""`setup`: this machine's runtime in one verb: Docker, the schema, a key the CLI finds by itself, the models."""

import json
import os
import subprocess
import sys
from collections.abc import Mapping
from pathlib import Path
from typing import Annotated

import typer

from pinecall_runtime.accounts.models import DEFAULT_ORG
from pinecall_runtime.accounts.service import keys
from pinecall_runtime.cli import local
from pinecall_runtime.cli import orgs as orgs_cli
from pinecall_runtime.cli import setup_models as models_
from pinecall_runtime.cli.command import OK, Context, context_of, verb
from pinecall_runtime.enums import Env
from pinecall_runtime.exceptions import UpstreamError, ValidationError

# Where the CLI keeps this machine's sign-in (`PINECALL_HOME` moves it); the key setup makes is
# handed to it there, in a file of its own, read by the CLI when a project has no key of its own.
CLI_HOME_VARIABLE = "PINECALL_HOME"
CLI_LOCAL_FILE = "local.json"
DEV_KEY = "PINECALL_DEV_KEY"
DEV_KEY_LABEL = "this machine (pinecall-runtime setup)"

NO_COMPOSE = "docker compose did not answer: start Docker and run this again"
NEXT = """
  in an agent's folder:
    npm i -g pinecall && pinecall new acme --agent front-desk && cd acme && npm install
    pinecall chat        # a written call, here, on this runtime
    pinecall start       # answer calls; pinecall test, pinecall simulate, pinecall console follow
"""
NEXT_ORG = (
    "\n  open the invitation link above to set a password; then, in an agent's folder:\n"
    "    pinecall login {url}\n    pinecall link\n"
)


@verb
async def setup(
    ctx: typer.Context,
    where: local.Dir = local.DEFAULT_DIR,
    org_mode: Annotated[
        bool,
        typer.Option(
            "--org",
            help="A team's runtime: the first org and person, as `init` makes them, instead of this machine's key.",
        ),
    ] = False,
    models: Annotated[
        models_.Models | None, typer.Option("--models", help="local · keys · none; asked when a terminal is there.")
    ] = None,
    chat_only: Annotated[
        bool, typer.Option("--chat-only", help="Written calls alone: no LiveKit, no worker, no ears, no voice.")
    ] = False,
    llm: Annotated[str, typer.Option("--llm", help="The Ollama model `local` thinks with.")] = models_.LOCAL_LLM,
    yes: Annotated[bool, typer.Option("--yes", "-y", help="Ask nothing: local models, this machine's key.")] = False,
    services_only: Annotated[
        bool, typer.Option("--services-only", help="Everything but running the gateway and the worker.")
    ] = False,
    email: Annotated[str | None, typer.Option("--email", help="With --org: the first person's address.")] = None,
    person: Annotated[str | None, typer.Option("--person", help="With --org: the first person's name.")] = None,
) -> int:
    """This machine's runtime, from nothing to a class that answers: run once, safe to run again."""
    context = context_of(ctx)
    out = context.out
    asking = sys.stdin.isatty() and not yes
    local.docker_or_refuse()
    out.line(f"docker     {_compose_version()}")
    compose = local.write_shipped(where)
    services = ("postgres", "redis") if chat_only else local.SERVICES
    local.services_up(compose, services)
    out.line(
        "services   "
        + " · ".join(f"{name} :{port}" for name, (port, service) in local.PORTS.items() if service in services)
    )
    env = where / "env"
    values = local.read_env(env)
    await local.prepare_database(values, env)
    out.line("schema     at this release")
    runtime = Context(local.settings_of(values), out)
    async with runtime.stack:
        if org_mode:
            await _the_first_person(runtime, email, person, asking)
        else:
            handed = await _this_machines_key(runtime, values, env)
            out.line(f"key        this machine's, in {handed}: the CLI finds this runtime by itself")
        chosen = models if models is not None else (models_.ask_models() if asking else models_.Models.local)
        if chosen is models_.Models.local:
            await models_.local_models(runtime, where, llm, chat_only, out)
        elif chosen is models_.Models.keys:
            await models_.vendor_keys(runtime, asking, out)
    out.line(f"ready      console {local.GATEWAY_URL}/sandbox/")
    out.line(NEXT_ORG.format(url=local.GATEWAY_URL) if org_mode else NEXT)
    if services_only:
        return OK
    return (
        local.run_both(context, values, ["gateway"])
        if chat_only
        else local.run_both(context, values, ["gateway"], ["worker", "start"])
    )


# ── this machine's key ──


async def _this_machines_key(runtime: Context, values: dict[str, str], env: Path) -> Path:
    """A key of `default`'s in the sandbox, drawn once into the env file, handed to the CLI every time."""
    if DEV_KEY not in values:
        issue = keys.Issue(org=DEFAULT_ORG, env=Env.sandbox, scopes=keys.KEY_SCOPES, label=DEV_KEY_LABEL)
        async with runtime.sessions.begin() as session:
            _, values[DEV_KEY] = await keys.issue_key(session, issue)
        with env.open("a", encoding="utf-8") as out:
            out.write(f"{DEV_KEY}={values[DEV_KEY]}\n")
    return hand_to_cli(values[DEV_KEY], cli_home(os.environ))


def cli_home(environ: Mapping[str, str]) -> Path:
    """Where the CLI keeps this machine's sign-in: `PINECALL_HOME`, else `~/.pinecall`."""
    named = environ.get(CLI_HOME_VARIABLE)
    return Path(named) if named else Path.home() / ".pinecall"


def hand_to_cli(secret: str, home: Path) -> Path:
    """Write the key where the CLI reads it, owner-only; the path written."""
    home.mkdir(mode=0o700, parents=True, exist_ok=True)
    path = home / CLI_LOCAL_FILE
    handed = {"url": local.GATEWAY_URL, "key": secret, "org": DEFAULT_ORG, "written_by": "pinecall-runtime setup"}
    if not path.exists():
        path.touch(mode=0o600)
    path.write_text(json.dumps(handed, indent=2) + "\n", encoding="utf-8")
    path.chmod(0o600)
    return path


# ── a team's runtime ──


async def _the_first_person(runtime: Context, email: str | None, person: str | None, asking: bool) -> None:
    if email is None and asking:
        email = typer.prompt("the first person's email")
    if person is None and asking:
        person = typer.prompt("their name")
    if email is None or person is None:
        raise ValidationError("--org needs --email and --person, or a terminal to ask them in")
    await orgs_cli.initialize(
        runtime, org=DEFAULT_ORG, name=None, email=email, person=person, role=orgs_cli.THE_FIRST_ROLE
    )


# ── docker ──


def _compose_version() -> str:
    version = subprocess.run(["docker", "compose", "version", "--short"], capture_output=True, text=True, check=False)
    if version.returncode != 0:
        raise UpstreamError(NO_COMPOSE)
    return f"compose {version.stdout.strip()}"
