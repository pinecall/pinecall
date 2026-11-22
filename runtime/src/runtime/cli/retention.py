"""`retention`: the sealed calls past their org's days, shown or erased; a CronJob or `nightly` runs the erasure."""

import asyncio
import time
from contextlib import AsyncExitStack
from datetime import UTC, datetime, timedelta
from typing import Annotated

import httpx
import typer

from runtime import builders
from runtime.alerts.service.alerts import KEPT_DAYS
from runtime.cli.command import OK, Context, context_of, verb
from runtime.cli.output import Printer
from runtime.redis import open_signal
from runtime.retention.service import nightly
from runtime.retention.service.erasure import Erasing
from runtime.scoping import box_wide

app = typer.Typer(help="the calls past their org's days", no_args_is_help=True)

# The hour of UTC a server's night runs at: the hour of the cluster's CronJob.
NIGHTLY_AT = "04:00"


@app.command("due")
@verb
async def retention_due(ctx: typer.Context) -> int:
    """The sealed calls the next run would erase, one line each, and how many."""
    context = context_of(ctx)
    async with context.sessions() as session:
        with box_wide():
            due = await nightly.list_due(session, time.time())
    context.out.rows(
        due, (("call", lambda item: item.call), ("org", lambda item: item.org), ("env", lambda item: item.env))
    )
    context.out.line(f"{len(due)} calls past their org's days")
    return OK


@app.command("run")
@verb
async def retention_run(ctx: typer.Context) -> int:
    """Erase every sealed call past its org's days, forget what is kept for a time; how many of each."""
    context = context_of(ctx)
    night = await _run_the_night(context)
    if context.out.as_json:
        context.out.data(night)
        return OK
    _say_the_night(context.out, night)
    return OK


# A server has no CronJob: this is its night, a service that Docker keeps up. A night that fails ends
# the process, Docker starts it again, and it waits for the next: what was due is still due then.
@app.command("nightly")
@verb
async def retention_nightly(
    ctx: typer.Context,
    at: Annotated[str, typer.Option("--at", help="The hour of UTC the night runs at, as HH:MM.")] = NIGHTLY_AT,
) -> int:
    """`run`, once a day at an hour of UTC, until told to stop: a server's night."""
    context = context_of(ctx)
    while True:
        await asyncio.sleep(seconds_until(at, time.time()))
        _say_the_night(context.out, await _run_the_night(context))


def seconds_until(at: str, now: float) -> float:
    """How long from `now` until it is next `HH:MM` in UTC: a whole day when it is that minute now."""
    hour, minute = (int(part) for part in at.split(":"))
    today = datetime.fromtimestamp(now, UTC).replace(hour=hour, minute=minute, second=0, microsecond=0)
    following = today if today.timestamp() > now else today + timedelta(days=1)
    return following.timestamp() - now


async def _run_the_night(context: Context) -> nightly.Nightly:
    # The night reaches the database and the recordings' store, and its CronJob is handed neither the
    # SFU's pair nor Redis (charts/pinecall, `retentionEnv`): it opens that much and no more. Until
    # 2026-11-17 it opened the process's whole state, which asks for the pair, and every night since the
    # cutover of 2026-11-12 ended on "LIVEKIT_API_KEY and LIVEKIT_API_SECRET are unset": nothing was
    # forgotten, and no day of the log was made ahead. What it opens it closes when the night is over:
    # `nightly` runs one after another in one process.
    async with AsyncExitStack() as stack:
        http = await stack.enter_async_context(httpx.AsyncClient())
        signal = await stack.enter_async_context(open_signal(context.settings))
        *_, logs = builders.build_log_engine(context.settings, context.sessions, signal, stack)
        erasing = Erasing(builders.build_recordings(context.settings, http), logs)
        return await nightly.run_nightly(context.sessions, erasing, time.time())


def _say_the_night(out: Printer, night: nightly.Nightly) -> None:
    out.line(f"{len(night.erased)} calls erased past their org's days")
    out.line(f"{night.records} call records and {night.dials} dials forgotten past 24 months")
    out.line(f"{night.seen} WhatsApp message ids forgotten past Meta's 7 days of retries")
    out.line(f"{night.alerts} alerts forgotten past {KEPT_DAYS} days")
    out.line(f"days of the log: {len(night.days.made)} made ahead, {len(night.days.dropped)} dropped once empty")
    for day in night.days.refused:
        out.line(f"{day} not made: the default partition holds rows of it")
