"""`retention`: the sealed calls past their org's days, shown or erased; a CronJob runs the erasure nightly."""

import time

import typer

from pinecall_runtime.alerts import service as alerts
from pinecall_runtime.calls import service as calls
from pinecall_runtime.cli.command import OK, context_of, verb
from pinecall_runtime.retention import service as retention

app = typer.Typer(help="the calls past their org's days", no_args_is_help=True)


@app.command("due")
@verb
async def retention_due(ctx: typer.Context) -> int:
    """The sealed calls the next run would erase, one line each, and how many."""
    context = context_of(ctx)
    async with context.sessions() as session:
        due = await retention.due_calls(session, time.time())
    context.out.rows(
        due,
        (("call", lambda item: item.call), ("org", lambda item: item.scope.org), ("env", lambda item: item.scope.env)),
    )
    context.out.line(f"{len(due)} calls past their org's days")
    return OK


@app.command("run")
@verb
async def retention_run(ctx: typer.Context) -> int:
    """Erase every sealed call past its org's days, forget what is kept for a time; how many of each."""
    context = context_of(ctx)
    recordings = calls.recordings_of(context.settings, await context.http())
    night = await retention.run_nightly(context.sessions, recordings, time.time())
    if context.out.as_json:
        context.out.data(night)
        return OK
    context.out.line(f"{len(night.erased)} calls erased past their org's days")
    context.out.line(f"{night.records} call records and {night.dials} dials forgotten past 24 months")
    context.out.line(f"{night.seen} WhatsApp message ids forgotten past Meta's 7 days of retries")
    context.out.line(f"{night.alerts} alerts forgotten past {alerts.KEPT_DAYS} days")
    context.out.line(
        f"days of the log: {len(night.days.made)} made ahead, {len(night.days.dropped)} dropped once empty"
    )
    for day in night.days.refused:
        context.out.line(f"{day} not made: the default partition holds rows of it")
    return OK
