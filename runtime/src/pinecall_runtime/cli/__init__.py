"""pinecall-runtime: the operator's terminal, one Typer app of groups, each verb a typed function."""

import logging
from collections.abc import Sequence
from typing import Annotated

import typer

from pinecall_runtime import __version__
from pinecall_runtime.cli import (
    box,
    doctor,
    fleet,
    keys,
    limits,
    load,
    local,
    orgs,
    processes,
    providers,
    rebuild,
    retention,
    routes,
    schema,
    sessions,
    setup,
    traceback,
)
from pinecall_runtime.cli.command import MISCONFIGURED, Context
from pinecall_runtime.cli.output import Printer
from pinecall_runtime.config import load_settings
from pinecall_runtime.exceptions import ConfigurationError

app = typer.Typer(
    name="pinecall-runtime",
    help="The operator's terminal: the processes, the database, the tenants and the fleet.",
    no_args_is_help=True,
    add_completion=True,
    rich_markup_mode=None,
    pretty_exceptions_enable=False,
)
# The groups, in the order `--help` lists them: the processes, the database, the box, the tenants,
# the fleet, the lab.
app.command("gateway")(processes.gateway)
app.add_typer(processes.worker_app, name="worker")
app.add_typer(processes.runner_app, name="runner")
app.add_typer(schema.app, name="migrate")
app.command("doctor")(doctor.doctor)
app.add_typer(providers.app, name="providers")
app.add_typer(providers.memory_app, name="memory")
app.add_typer(providers.vault_app, name="vault")
app.add_typer(retention.app, name="retention")
app.add_typer(sessions.app, name="sessions")
app.add_typer(rebuild.facts_app, name="facts")
app.add_typer(rebuild.drift_app, name="drift")
app.add_typer(rebuild.usage_app, name="usage")
app.command("traceback")(traceback.traceback)
app.command("setup")(setup.setup)
app.command("init")(orgs.init)
app.add_typer(orgs.app, name="orgs")
for name, limit in limits.VERBS.items():
    orgs.app.command(name)(limit)
app.add_typer(keys.app, name="keys")
app.add_typer(box.app, name="box")
app.add_typer(routes.app, name="routes")
app.add_typer(fleet.app, name="fleet")
app.add_typer(fleet.fence_app, name="fence")
app.add_typer(fleet.sip_app, name="sip")
app.command("load")(load.load)
app.add_typer(local.app, name="local")


def _show_version(shown: bool) -> None:
    if shown:
        typer.echo(__version__)
        raise typer.Exit()


# Runs before every verb: the settings are read once, and every verb prints through one printer.
@app.callback()
def root(
    ctx: typer.Context,
    as_json: Annotated[bool, typer.Option("--json", help="Answer as one JSON document, for a script.")] = False,
    _version: Annotated[
        bool, typer.Option("--version", callback=_show_version, is_eager=True, help="Print the version and exit.")
    ] = False,
) -> None:
    """Load the settings, set up logging, and hand every verb its context."""
    try:
        settings = load_settings()
    except ConfigurationError as refused:
        typer.echo(f"pinecall-runtime: {refused}", err=True)
        raise typer.Exit(code=MISCONFIGURED) from None
    logging.basicConfig(level=settings.log_level.upper(), format="%(levelname)s %(name)s: %(message)s")
    # A verb's own lines say what it did; httpx's line per request says nothing an operator needs.
    logging.getLogger("httpx").setLevel(logging.WARNING)
    ctx.obj = Context(settings, Printer(as_json=as_json))


def main(argv: Sequence[str] | None = None) -> None:
    """The console script: parse the verb and run it; its exit is the process's."""
    app(args=None if argv is None else list(argv), prog_name="pinecall-runtime")
