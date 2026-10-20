"""`setup`: a runtime in one verb, on this machine or a server (--domain): keys found, open models, its admin."""

import logging
import os
import subprocess
import sys
from pathlib import Path
from typing import Annotated

import typer
from typer.core import TyperOption

from pinecall_runtime.cli import local, processes
from pinecall_runtime.cli import orgs as orgs_cli
from pinecall_runtime.cli import setup_ask as ask
from pinecall_runtime.cli import setup_models as models_
from pinecall_runtime.cli import setup_person as person_
from pinecall_runtime.cli import setup_server as server_
from pinecall_runtime.cli import setup_servers as servers
from pinecall_runtime.cli.command import OK, Context, context_of, verb
from pinecall_runtime.cli.output import Printer
from pinecall_runtime.exceptions import UpstreamError, ValidationError
from pinecall_runtime.providers import service as providers

NO_COMPOSE = "docker compose did not answer: start Docker and run this again"
FIRST_RUN = "  starting  the first run downloads the services and the models: some minutes"
NEXT_HERE = """  ✓ ready   {gateway}/sandbox/
  ✓ this machine is signed in — no `pinecall login` needed

  Next, in another terminal:
    npm i -g pinecall
    pinecall new acme --agent front-desk && cd acme && npm install
    pinecall start       # the agent, held here: leave it running
    pinecall chat        # in a third terminal: talk to it
"""
NEXT_SERVER = """  ✓ ready   https://{name}
  ✓ {email} runs this runtime and is admin of org default

  From your laptop:
    npm i -g pinecall
    pinecall login https://{name}
    pinecall new acme --agent front-desk && cd acme && npm install
    pinecall start       # the agent, held here: leave it running
    pinecall chat        # in another terminal: talk to it

  More orgs: the console → Box → Organizations · logs: pinecall-runtime local logs
"""
WEBHOOK = """
  One step in your LiveKit → Settings → Webhooks, signed with {key}:
    https://{name}/v1/livekit/webhook
"""
# A script's flags: every answer setup would ask, and the knobs a person never needs. `--help-all` shows them.
SCRIPT = "For a script (every answer setup would ask, and every knob)"


def _help_all(ctx: typer.Context, value: bool) -> None:
    """The person's help, then the script's flags under a heading of their own; nothing is set up."""
    if not value or ctx.resilient_parsing:
        return
    formatter = ctx.make_formatter()
    scripted = [param for param in ctx.command.params if isinstance(param, TyperOption) and param.hidden]
    with formatter.section(SCRIPT):
        formatter.write_dl([(_spelled(param, ctx), param.help or "") for param in scripted])
    typer.echo(ctx.get_help() + "\n" + formatter.getvalue().rstrip())
    raise typer.Exit


def _spelled(param: TyperOption, ctx: typer.Context) -> str:
    """`--email <str>` or `-y, --yes`, as the person's block spells its own."""
    names = ", ".join(sorted(param.opts, key=len))
    return names if param.is_flag else f"{names} {param.make_metavar(ctx)}"


@verb
async def setup(
    ctx: typer.Context,
    domain: Annotated[
        str | None, typer.Option("--domain", help="A server: this name points at this machine; https by Caddy.")
    ] = None,
    livekit: Annotated[
        str | None,
        typer.Option("--livekit", help="Your own LiveKit (wss://…), not one started here; `here` puts setup's back."),
    ] = None,
    phone: Annotated[bool, typer.Option("--phone", help="Phone calls: LiveKit's SIP on :5060 (a server).")] = False,
    _help: Annotated[
        bool,
        typer.Option(
            "--help-all", help="Every flag, for a script.", is_eager=True, expose_value=False, callback=_help_all
        ),
    ] = False,
    where: Annotated[Path, typer.Option("--dir", help="Where the runtime's files are kept.", hidden=True)] = (
        local.DEFAULT_DIR
    ),
    livekit_key: Annotated[
        str | None, typer.Option("--livekit-key", help="Your LiveKit's API key; asked when not given.", hidden=True)
    ] = None,
    livekit_secret_stdin: Annotated[
        bool, typer.Option("--livekit-secret-stdin", help="Your LiveKit's API secret, one line of stdin.", hidden=True)
    ] = False,
    wheel: Annotated[
        Path | None,
        typer.Option("--from", help="A server's processes installed from this wheel, not PyPI.", hidden=True),
    ] = None,
    email: Annotated[
        str | None, typer.Option("--email", help="Who signs in to the console; asked when not given.", hidden=True)
    ] = None,
    person: Annotated[
        str | None, typer.Option("--person", help="Their name; the address's first part.", hidden=True)
    ] = None,
    password_stdin: Annotated[
        bool, typer.Option("--password-stdin", help="The console person's password, one line of stdin.", hidden=True)
    ] = False,
    yes: Annotated[
        bool, typer.Option("--yes", "-y", help="Ask nothing: a key missing refuses, and no password.", hidden=True)
    ] = False,
    models: Annotated[
        str | None,
        typer.Option(
            "--models",
            help="local: every stage on this machine · keys: deepgram, anthropic, cartesia · none: the row is yours.",
            hidden=True,
        ),
    ] = None,
    stt: Annotated[
        str | None,
        typer.Option("--stt", help="The ears of an agent naming none: local[/<model>] or a vendor.", hidden=True),
    ] = None,
    turn: Annotated[
        str | None, typer.Option("--turn", help="The end of turn: stt, smart-turn or livekit.", hidden=True)
    ] = None,
    llm: Annotated[
        str | None,
        typer.Option("--llm", help="The thinking of an agent naming none: local[/<model>] or a vendor.", hidden=True),
    ] = None,
    judge: Annotated[
        str | None, typer.Option("--judge", help="Who judges a finished call: as --llm.", hidden=True)
    ] = None,
    caller: Annotated[
        str | None, typer.Option("--caller", help="Who plays the simulated caller: as --llm.", hidden=True)
    ] = None,
    tts: Annotated[
        str | None, typer.Option("--tts", help="The voice of an agent naming none: local or a vendor.", hidden=True)
    ] = None,
    chat_only: Annotated[
        bool, typer.Option("--chat-only", help="Written calls alone: no LiveKit, no worker, no voice.", hidden=True)
    ] = False,
    services_only: Annotated[
        bool, typer.Option("--services-only", help="Everything but running the gateway and the worker.", hidden=True)
    ] = False,
    recommend: Annotated[
        bool,
        typer.Option("--recommend", help="The stack that fits this machine, as JSON; nothing set up.", hidden=True),
    ] = False,
) -> int:
    """A runtime on this machine, or on a server with --domain. Run it again any time: what is done is skipped."""
    context = context_of(ctx)
    out = context.out
    if recommend:
        out.data(providers.recommendation(os.environ))
        return OK
    local.docker_or_refuse()
    _compose_or_refuse()
    env = where / "env"
    first_run = not env.is_file()
    before = local.read_env(env) if not first_run else {}
    asking = sys.stdin.isatty() and not yes
    server = await server_for(domain, livekit, livekit_key, livekit_secret_stdin, phone, before, asking=asking)
    out.line(f"\n  Pinecall runtime · {server.name if server else 'on this machine'}\n")
    if server is not None:
        server_.linux_or_refuse()
        out.line(server_.check_name(server.name))
        out.line("  https     certificate from Let's Encrypt, renews itself")
        if server.livekit is not None:
            out.line(f"  livekit   {server.livekit.url} ✓")
    # Decided before anything is brought up: the keys found, the open models, a key missing.
    choices = models_.choices_of(models, stt, turn, llm, tts, judge, caller, chat_only=chat_only)
    card = servers.a_card_for_docker() if choices else False
    keys = _keys(choices, asking=asking, out=out, server=server is not None, card=card) if choices else {}
    answers = person_.ask_person(
        email, person, before, asking=asking, password_stdin=password_stdin, server=server is not None
    )
    if first_run:
        out.line(f"\n{FIRST_RUN}")
    compose = local.write_shipped(where)
    started = ("postgres", "redis") if chat_only or server else local.SERVICES
    local.services_up(compose, started)
    if server is None:
        out.line(
            "  services  "
            + " · ".join(name for name, (_, svc) in local.PORTS.items() if svc in started)
            + " — this machine only"
        )
    values = local.read_env(env)
    if server is not None:
        values = local.set_values(env, server_.settings_of(server, values))
    # The schema's revisions, one INFO line each, are the operator's to read in `migrate up`, not a setup's.
    logging.getLogger("alembic").setLevel(logging.WARNING)
    await local.prepare_database(values, env, production_fleet=server is not None)
    runtime = Context(local.settings_of(values), out)
    async with runtime.stack:
        said, member = await person_.the_person(runtime, answers, env)
        if said:
            out.line(said)
        if server is None:
            await person_.this_machines_key(runtime, values, env, member)
        if choices is not None:
            await servers.models(runtime, where, choices, keys, card=card)
    if server is not None:
        return _serve(where, server, local.read_env(env), wheel, answers.email, out)
    out.line("\n" + NEXT_HERE.format(gateway=local.GATEWAY_URL))
    if services_only:
        return OK
    return (
        processes.run_both(out, values, ["gateway"])
        if chat_only
        else processes.run_both(out, values, ["gateway"], ["worker", "start"])
    )


async def server_for(
    domain: str | None,
    livekit: str | None,
    key: str | None,
    secret_stdin: bool,
    phone: bool,
    before: dict[str, str],
    *,
    asking: bool,
) -> server_.Server | None:
    """The server this run makes: the name given or already served, their LiveKit given or kept; None on a laptop."""
    kept = server_.from_the_env(before)
    name = domain or (kept.name if kept else None)
    if name is None:
        if livekit is not None:
            raise ValidationError(server_.LIVEKIT_ON_A_LAPTOP)
        if phone:
            raise ValidationError("--phone is a server's: --domain <name> --phone")
        return None
    theirs = kept.livekit if kept and livekit is None else None
    if livekit is not None and livekit != server_.HERE:
        if key is None and not asking:
            raise ValidationError("--livekit needs --livekit-key and --livekit-secret-stdin with --yes")
        typed_key = key or ask.livekit_key()
        typed_secret = orgs_cli.read_secret_line() if secret_stdin else ask.livekit_secret()
        theirs = server_.TheirLiveKit(livekit, typed_key, typed_secret)
    with_phone = phone or (kept.phone if kept else False)
    if theirs is not None and with_phone:
        raise ValidationError(server_.PHONE_ON_THEIR_LIVEKIT)
    if theirs is not None:
        # Tried every run, a kept pair too: the ✓ setup prints says the pair works today.
        await server_.check_their_livekit(theirs)
    return server_.Server(name, theirs, phone=with_phone)


def _serve(
    where: Path, server: server_.Server, values: dict[str, str], wheel: Path | None, email: str, out: Printer
) -> int:
    services = "Postgres · Redis" + (" · LiveKit" if server.livekit is None else " — LiveKit is yours")
    out.line(f"  services  {services}")
    if server.livekit is not None:
        out.line("  phone     through your LiveKit's own SIP")
    else:
        out.line("  phone     on: SIP on :5060" if server.phone else "  phone     off — `--phone` turns it on")
    server_.write_files(where, server, values, wheel)
    server_.bring_up(where, server, values, wheel)
    server_.wait_for_https(server.name)
    out.line("\n" + NEXT_SERVER.format(name=server.name, email=email))
    if server.livekit is not None:
        out.line(WEBHOOK.format(key=server.livekit.key, name=server.name))
    return OK


# Every key found is loaded, so an agent may name any vendor of yours with nothing to add; a key
# the defaults need and found nowhere is asked for at a terminal, else refused.
def _keys(choices: models_.Choices, *, asking: bool, out: Printer, server: bool, card: bool) -> dict[str, str]:
    loaded, places = models_.keys_found()
    out.line(models_.said_keys(loaded, places, server=server))
    out.line(models_.said_models(choices, card=card))
    keys, _ = models_.keys_for(choices, ask=ask.secret if asking else None)
    # A real key wins over the word the embedder's plugin is given when none is.
    return {**keys, **loaded}


def _compose_or_refuse() -> None:
    version = subprocess.run(["docker", "compose", "version", "--short"], capture_output=True, text=True, check=False)
    if version.returncode != 0:
        raise UpstreamError(NO_COMPOSE)
