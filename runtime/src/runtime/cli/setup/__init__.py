"""`setup`: a runtime in one verb, on this machine or a server (--domain): keys found, open models, its admin."""

import os
import sys
from pathlib import Path
from typing import Annotated

import typer
from typer.core import TyperOption

from runtime.cli.command import OK, context_of, verb
from runtime.cli.setup.choices import read_measured
from runtime.cli.setup.compose import docker_or_refuse
from runtime.cli.setup.files import DEFAULT_DIR
from runtime.cli.setup.plan import Flags, carry_out
from runtime.providers.service import machine

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
        DEFAULT_DIR
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
    if recommend:
        context.out.data(machine.recommendation(read_measured(), os.environ))
        return OK
    docker_or_refuse()
    flags = Flags(
        where=where,
        domain=domain,
        livekit=livekit,
        phone=phone,
        livekit_key=livekit_key,
        livekit_secret_stdin=livekit_secret_stdin,
        wheel=wheel,
        email=email,
        person=person,
        password_stdin=password_stdin,
        asking=sys.stdin.isatty() and not yes,
        models=models,
        stt=stt,
        turn=turn,
        llm=llm,
        tts=tts,
        judge=judge,
        caller=caller,
        chat_only=chat_only,
        services_only=services_only,
    )
    return await carry_out(flags, context.out)
