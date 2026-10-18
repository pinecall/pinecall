"""`setup`: this machine's runtime in one verb: Docker, the schema, its admin, this machine signed in, the models."""

import json
import os
import secrets
import subprocess
import sys
from collections.abc import Mapping
from pathlib import Path
from typing import Annotated

import typer

from pinecall_runtime.accounts.models import DEFAULT_ORG
from pinecall_runtime.accounts.service import keys, members, orgs
from pinecall_runtime.cli import local
from pinecall_runtime.cli import orgs as orgs_cli
from pinecall_runtime.cli import setup_models as models_
from pinecall_runtime.cli import setup_servers as servers
from pinecall_runtime.cli.command import OK, Context, context_of, verb
from pinecall_runtime.enums import Role
from pinecall_runtime.exceptions import UpstreamError, ValidationError
from pinecall_runtime.kit.text import a_mapping
from pinecall_runtime.providers import service as providers

# Where the CLI keeps this machine's sign-in (`PINECALL_HOME` moves it): setup signs the machine in
# to this runtime there, as `pinecall login` would, in the CLI's own file and format
# (cli/src/project/session.ts): one entry per gateway, its key and its org, and the last one.
CLI_HOME_VARIABLE = "PINECALL_HOME"
CLI_SESSION_FILE = "session.json"
# What setup wrote before the sign-in was the CLI's one way in: taken away when found.
CLI_OLD_FILE = "local.json"
DEV_KEY = "PINECALL_DEV_KEY"
# Whose key it is: the console's person, so what `pinecall start` holds is the copy their console shows.
DEV_KEY_OF = "PINECALL_DEV_KEY_OF"
DEV_KEY_LABEL = "this machine (pinecall-runtime setup)"

NO_COMPOSE = "docker compose did not answer: start Docker and run this again"
NEXT = """
  on this machine, with no login:
    npm i -g pinecall && pinecall new acme --agent front-desk && cd acme && npm install
    pinecall chat        # a written call, here, on this runtime
    pinecall start       # answer calls; pinecall test, pinecall simulate, pinecall console follow
  from another machine, signed in with that address and password:
    pinecall login http://<this machine>:8080
  more people: the console's Team, or pinecall-runtime orgs invite default <email>
"""
# Where nobody is asked: an address that reads as this machine's, and a password drawn and shown once.
NOBODY_ASKED = "admin@pinecall.local"
DRAWN_BYTES = 12
CHANGES_IT = "`pinecall-runtime orgs password default {email}` changes it"


@verb
async def setup(
    ctx: typer.Context,
    where: local.Dir = local.DEFAULT_DIR,
    models: Annotated[
        str | None,
        typer.Option(
            "--models",
            help="local: every stage on this machine · keys: deepgram, anthropic, cartesia · none: the row is yours.",
        ),
    ] = None,
    stt: Annotated[
        str | None,
        typer.Option("--stt", help="Who hears the caller: local, local/<whisper model>, or a vendor of yours."),
    ] = None,
    turn: Annotated[
        str | None, typer.Option("--turn", help="Who ends the caller's turn: stt, smart-turn or livekit.")
    ] = None,
    llm: Annotated[
        str | None, typer.Option("--llm", help="Who thinks: local, local/<ollama model>, or a vendor of yours.")
    ] = None,
    judge: Annotated[
        str | None,
        typer.Option("--judge", help="Who judges a finished call: as --llm; the thinking's model when not given."),
    ] = None,
    caller: Annotated[
        str | None,
        typer.Option("--caller", help="Who plays the simulated caller: as --llm; the thinking's model when not given."),
    ] = None,
    tts: Annotated[str | None, typer.Option("--tts", help="Who speaks: local, or a vendor of yours.")] = None,
    chat_only: Annotated[
        bool, typer.Option("--chat-only", help="Written calls alone: no LiveKit, no worker, no ears, no voice.")
    ] = False,
    password_stdin: Annotated[
        bool, typer.Option("--password-stdin", help="The console person's password read as one line of stdin.")
    ] = False,
    yes: Annotated[bool, typer.Option("--yes", "-y", help="Ask nothing: the stack that fits this machine.")] = False,
    services_only: Annotated[
        bool, typer.Option("--services-only", help="Everything but running the gateway and the worker.")
    ] = False,
    recommend: Annotated[
        bool,
        typer.Option(
            "--recommend", help="Read this machine and say the stack that fits it, as JSON; nothing is set up."
        ),
    ] = False,
    email: Annotated[
        str | None, typer.Option("--email", help="Who signs in to the console; asked when not given.")
    ] = None,
    person: Annotated[
        str | None, typer.Option("--person", help="Their name; the address's first part when not given.")
    ] = None,
) -> int:
    """This machine's runtime, from nothing to a class that answers, on the stack that fits it; safe to run again."""
    context = context_of(ctx)
    out = context.out
    if recommend:
        out.data(providers.recommendation(os.environ))
        return OK
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
        said, member = await _the_person(runtime, email, person, asking, password_stdin)
        out.line(said)
        handed = await _this_machines_key(runtime, values, env, member)
        out.line(f"signed in  this machine, in {handed}: the pinecall CLI here needs no login")
        choices = _choices(models, stt, turn, llm, tts, judge, caller, asking=asking, chat_only=chat_only)
        if choices is not None:
            await servers.models(runtime, where, choices, asking=asking, out=out)
    out.line(f"ready      console {local.GATEWAY_URL}/sandbox/")
    out.line(NEXT)
    if services_only:
        return OK
    return (
        local.run_both(context, values, ["gateway"])
        if chat_only
        else local.run_both(context, values, ["gateway"], ["worker", "start"])
    )


# What the flags say; else the stack that fits this machine, shown at a terminal, where a stage may
# be changed before it runs.
def _choices(
    models: str | None,
    stt: str | None,
    turn: str | None,
    llm: str | None,
    tts: str | None,
    judge: str | None,
    caller: str | None,
    *,
    asking: bool,
    chat_only: bool,
) -> models_.Choices | None:
    if models == "none":
        return None
    if models not in (None, "local", "keys"):
        raise ValidationError(f"--models is local, keys or none, not {models!r}")
    named = any((stt, turn, llm, tts, judge, caller))
    base = models_.ALL_KEYS if models == "keys" else models_.ALL_LOCAL if models == "local" else models_.recommended()
    if models is None and asking and not named:
        base = models_.confirmed(base)
    chosen = models_.Choices(
        stt=models_.local_or_vendor(stt or base.stt),
        turn=models_.turn_of(turn or base.turn),
        llm=models_.local_or_vendor(llm or base.llm),
        tts=models_.local_or_vendor(tts or base.tts),
        judge=models_.local_or_vendor(judge) if judge else base.judge,
        caller=models_.local_or_vendor(caller) if caller else base.caller,
    )
    if chat_only:
        chosen = models_.Choices(
            stt=models_.LOCAL,
            turn="smart-turn",
            llm=chosen.llm,
            tts=models_.LOCAL,
            judge=chosen.judge,
            caller=chosen.caller,
        )
    return models_.check_choices(chosen)


# ── this machine's key ──


# A person's key, not a server's: in the sandbox a person's console shows that person's own copy of
# the agents, and a server's key holds the org's, which nobody's console showed (2026-10-17).
async def _this_machines_key(runtime: Context, values: dict[str, str], env: Path, member: str) -> Path:
    """The console's person's key, drawn once into the env file, handed to the CLI every time."""
    if values.get(DEV_KEY_OF) != member or DEV_KEY not in values:
        async with runtime.sessions.begin() as session:
            found = await members.get_member(session, DEFAULT_ORG, member)
            _, values[DEV_KEY] = await keys.issue_person_key(session, found, label=DEV_KEY_LABEL)
        values[DEV_KEY_OF] = member
        kept = [
            line
            for line in env.read_text(encoding="utf-8").splitlines()
            if not line.startswith((f"{DEV_KEY}=", f"{DEV_KEY_OF}="))
        ]
        env.write_text(
            "\n".join([*kept, f"{DEV_KEY}={values[DEV_KEY]}", f"{DEV_KEY_OF}={member}"]) + "\n", encoding="utf-8"
        )
    return hand_to_cli(values[DEV_KEY], cli_home(os.environ))


def cli_home(environ: Mapping[str, str]) -> Path:
    """Where the CLI keeps this machine's sign-in: `PINECALL_HOME`, else `~/.pinecall`."""
    named = environ.get(CLI_HOME_VARIABLE)
    return Path(named) if named else Path.home() / ".pinecall"


def hand_to_cli(secret: str, home: Path) -> Path:
    """This machine signed in to this runtime, in the CLI's session file, owner-only; its other gateways kept."""
    home.mkdir(mode=0o700, parents=True, exist_ok=True)
    path = home / CLI_SESSION_FILE
    gateways = dict(_gateways_in(path))
    kept = gateways.get(local.GATEWAY_URL)
    # A new sign-in: the keys minted from an earlier one go, the phone it calls from stays.
    entry: dict[str, object] = {"key": secret, "org": DEFAULT_ORG}
    if a_mapping(kept) and "calling" in kept:
        entry["calling"] = kept["calling"]
    gateways[local.GATEWAY_URL] = entry
    if not path.exists():
        path.touch(mode=0o600)
    path.write_text(json.dumps({"gateways": gateways, "last": local.GATEWAY_URL}, indent=2) + "\n", encoding="utf-8")
    path.chmod(0o600)
    (home / CLI_OLD_FILE).unlink(missing_ok=True)
    return path


# The gateways the CLI's session already holds; none from a file that is not there or not its shape.
def _gateways_in(path: Path) -> Mapping[str, object]:
    try:
        read: object = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    gateways = read.get("gateways") if a_mapping(read) else None
    return gateways if a_mapping(gateways) else {}


# ── who signs in to the console ──


# The person the console signs in as, with a password and no link: asked at a terminal, drawn and
# shown once where nobody is. Run again, a person who has a password keeps it.
async def _the_person(
    runtime: Context, email: str | None, person: str | None, asking: bool, password_stdin: bool
) -> tuple[str, str]:
    address = email or (typer.prompt("console sign-in: your email") if asking else NOBODY_ASKED)
    name = person or address.split("@", 1)[0]
    shortest = runtime.settings.min_password
    async with runtime.sessions.begin() as session:
        org = await orgs.get_org(session, DEFAULT_ORG)
        kept = await members.memberships_of(session, address.strip().lower())
        found = next((one for one in kept if one.org == org.id), None)
        if found is not None and found.password_hash is not None:
            return f"console    {found.email} keeps their password: {CHANGES_IT.format(email=found.email)}", found.id
        if found is None:
            invitee = members.Invitee(address, name, Role.admin)
            await members.invite(session, org.id, invitee, seats=None, vouched=True)
            found = await members.member_by_email(session, org.id, address)
        drawn = None if asking or password_stdin else secrets.token_urlsafe(DRAWN_BYTES)
        password = drawn or (orgs_cli.read_secret_line() if password_stdin else orgs_cli.new_password(asking=True))
        await members.set_password(session, org.id, found.id, password, shortest)
        await members.set_operator(session, org.id, found.id, on=True)
    if drawn is None:
        return (
            f"console    {found.email} signs in with the password typed: {CHANGES_IT.format(email=found.email)}",
            found.id,
        )
    return (
        f"console    {found.email} · password {drawn} (shown this once: {CHANGES_IT.format(email=found.email)})",
        found.id,
    )


# ── docker ──


def _compose_version() -> str:
    version = subprocess.run(["docker", "compose", "version", "--short"], capture_output=True, text=True, check=False)
    if version.returncode != 0:
        raise UpstreamError(NO_COMPOSE)
    return f"compose {version.stdout.strip()}"
