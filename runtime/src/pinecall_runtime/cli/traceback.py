"""`traceback <number>`: every phone call with a number and every dial to it, for a carrier's question."""

from typing import Annotated

import typer

from pinecall_runtime.calls import service as calls
from pinecall_runtime.cli.command import OK, context_of, verb
from pinecall_runtime.cli.output import when
from pinecall_runtime.cli.rebuild import day_of
from pinecall_runtime.compliance import service as compliance
from pinecall_runtime.telephony import service as telephony

NOTHING = "no call with {number} and no dial to it since {since}"


@verb
async def traceback(
    ctx: typer.Context,
    number: str,
    since: Annotated[str | None, typer.Option("--since", help="A day, YYYY-MM-DD; 24 months back unset.")] = None,
) -> int:
    """Print the number's calls, kept or erased, and its dials, oldest first."""
    context = context_of(ctx)
    async with context.sessions.begin() as session:
        found = await calls.traceback_of(session, number, day_of(since), read_by=compliance.OPERATOR)
    if context.out.as_json:
        context.out.data(found)
    else:
        context.out.lines(lines_of(found))
    return OK


def lines_of(found: telephony.Traceback) -> list[str]:
    """The traceback as lines a person pastes into an answer to a carrier."""
    since = when(found.since, seconds=False)[:10]
    if not found.calls and not found.dials:
        return [NOTHING.format(number=found.number, since=since)]
    return [
        f"{found.number} since {since}",
        f"calls ({len(found.calls)})",
        *(_call_line(call) for call in found.calls),
        f"dials ({len(found.dials)})",
        *(_dial_line(dial) for dial in found.dials),
    ]


def _call_line(call: telephony.TracebackCall) -> str:
    lasted = "-"
    if call.started_at is not None and call.ended_at is not None:
        lasted = f"{round(call.ended_at - call.started_at)}s"
    kept = "erased, record kept" if call.erased else "kept"
    return (
        f"  {when(call.started_at, seconds=False)}  {call.direction or '-':8}  {call.from_number or '-'} -> "
        f"{call.to_number or '-'}  {lasted:>6}  {call.end_reason or '-'}  "
        f"org {call.org or '-'} {call.env or '-'}  {call.call}  {kept}"
    )


def _dial_line(dial: telephony.TracebackDial) -> str:
    outcome = f"refused: {dial.refused}" if dial.refused else f"placed {dial.call or '-'}"
    return (
        f"  {when(dial.at, seconds=False)}  shown {dial.shown or '-'}  org {dial.org} {dial.env}  "
        f"agent {dial.agent}  asked by {dial.asked_by}  {outcome}"
    )
