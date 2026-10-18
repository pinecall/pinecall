"""`setup`: this machine's runtime in one verb: Docker, the stack that fits it, its admin, its sign-in, the models."""

import os
import subprocess
import sys
from typing import Annotated

import typer

from pinecall_runtime.cli import local
from pinecall_runtime.cli import setup_ask as ask
from pinecall_runtime.cli import setup_models as models_
from pinecall_runtime.cli import setup_person as person_
from pinecall_runtime.cli import setup_servers as servers
from pinecall_runtime.cli.command import OK, Context, context_of, verb
from pinecall_runtime.exceptions import UpstreamError, ValidationError
from pinecall_runtime.providers import service as providers

NO_COMPOSE = "docker compose did not answer: start Docker and run this again"
NEXT = """
  on this machine, with no login:
    npm i -g pinecall && pinecall new acme --agent front-desk && cd acme && npm install
    pinecall chat        # a written call, here, on this runtime
    pinecall start       # answer calls; pinecall test, pinecall simulate, pinecall console follow
  more people: the console's Team, or pinecall-runtime orgs invite default <email>
"""


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
    yes: Annotated[
        bool, typer.Option("--yes", "-y", help="Ask nothing: the stack that fits this machine, and no password.")
    ] = False,
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
    # Decided before anything is brought up: a stage picked, a key missing, both say so here.
    choices, typed = _choices(models, stt, turn, llm, tts, judge, caller, asking=asking, chat_only=chat_only)
    keys, found = models_.keys_for(choices, ask=_asked(typed, asking)) if choices else ({}, {})
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
        said, member = await person_.the_person(runtime, email, person, asking, password_stdin)
        out.line(said)
        handed = await person_.this_machines_key(runtime, values, env, member)
        out.line(f"signed in  this machine, in {handed}: the pinecall CLI here needs no login")
        if choices is not None:
            await servers.models(runtime, where, choices, keys, found, out=out)
    out.line(f"ready      console {local.GATEWAY_URL}/sandbox/")
    out.line(NEXT)
    if services_only:
        return OK
    return (
        local.run_both(context, values, ["gateway"])
        if chat_only
        else local.run_both(context, values, ["gateway"], ["worker", "start"])
    )


# What the flags say; else the stack that fits this machine — shown at a terminal, where a stage
# may be changed before it runs.
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
) -> tuple[models_.Choices | None, dict[str, str]]:
    typed: dict[str, str] = {}
    if models == "none":
        return None, typed
    if models not in (None, "local", "keys"):
        raise ValidationError(f"--models is local, keys or none, not {models!r}")
    named = any((stt, turn, llm, tts, judge, caller))
    if models == "keys":
        base = models_.ALL_KEYS
    elif models == "local":
        base = models_.ALL_LOCAL
    else:
        machine = providers.detect(os.environ)
        fits = providers.recommend(machine)
        base = models_.recommended(fits)
        if asking and not named:
            base, typed = ask.chosen(machine, fits, base)
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
    return models_.check_choices(chosen), typed


# A key typed as its vendor was picked is not asked again; one still missing is, at a terminal.
def _asked(typed: dict[str, str], asking: bool) -> models_.Ask | None:
    if not typed and not asking:
        return None
    return lambda variable: typed.get(variable) or (ask.secret(variable) if asking else "")


def _compose_version() -> str:
    version = subprocess.run(["docker", "compose", "version", "--short"], capture_output=True, text=True, check=False)
    if version.returncode != 0:
        raise UpstreamError(NO_COMPOSE)
    return f"compose {version.stdout.strip()}"
