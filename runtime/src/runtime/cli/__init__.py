"""pinecall-runtime: the operator's terminal, one Typer app of groups, each verb a typed function."""

import logging
from collections.abc import Sequence
from importlib.metadata import version
from typing import Annotated

import typer

from runtime.cli import doctor, migrate, processes
from runtime.cli.command import MISCONFIGURED, Context
from runtime.cli.output import Printer
from runtime.config import load_settings
from runtime.exceptions import ConfigurationError

DISTRIBUTION = "pinecall-runtime"

app = typer.Typer(
    name="pinecall-runtime",
    help="The operator's terminal: the processes, the database, the tenants and the fleet.",
    no_args_is_help=True,
    add_completion=True,
    rich_markup_mode=None,
    pretty_exceptions_enable=False,
)
# The groups, in the order `--help` lists them: the processes, the database, the box, the tenants,
# the fleet, the lab. The list is the index of `--help`: a group is named here, never found.
app.command("gateway")(processes.gateway)
app.add_typer(processes.worker_app, name="worker")
app.add_typer(processes.runner_app, name="runner")
app.add_typer(migrate.app, name="migrate")
app.command("doctor")(doctor.doctor)


def _show_version(shown: bool) -> None:
    if shown:
        typer.echo(version(DISTRIBUTION))
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
