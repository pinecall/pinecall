"""`box test-line`: the sandbox number a person calls to reach their own agent."""

from typing import Annotated

import typer

from runtime.cli.command import OK, context_of, verb
from runtime.scoping import box_wide
from runtime.telephony.service import test_line

app = typer.Typer(help="the sandbox number a person calls to reach their own agent", no_args_is_help=True)


@app.command("show")
@verb
async def test_line_show(ctx: typer.Context) -> int:
    """The box's test line, or that it has none."""
    context = context_of(ctx)
    async with context.sessions() as session:
        with box_wide():
            number = await test_line.find_test_line(session)
    context.out.line(number or "the box has no test line: `box test-line set <number>` makes a sandbox number it")
    return OK


# One of the box's own numbers, routed in the sandbox to the agent that answers a phone nobody said was theirs.
@app.command("set")
@verb
async def test_line_set(ctx: typer.Context, number: Annotated[str, typer.Argument(metavar="<+E.164>")]) -> int:
    """Make this sandbox number the test line."""
    context = context_of(ctx)
    async with context.sessions.begin() as session:
        with box_wide():
            kept = await test_line.put_test_line(session, number)
    context.out.line(f"a call to {kept} from a phone a person said was theirs reaches their sandbox agent")
    return OK


@app.command("rm")
@verb
async def test_line_rm(ctx: typer.Context) -> int:
    """Forget the test line; the number keeps ringing its own agent."""
    context = context_of(ctx)
    async with context.sessions.begin() as session:
        with box_wide():
            await test_line.put_test_line(session, None)
    context.out.line("the box has no test line now")
    return OK
