"""`facts`, `drift`, `usage`: the read models folded again from the log, which is the record."""

from datetime import UTC, datetime
from typing import Annotated

import typer

from pinecall_runtime.billing import service as billing
from pinecall_runtime.calls import service as calls
from pinecall_runtime.cli.command import OK, context_of, verb
from pinecall_runtime.exceptions import ValidationError

facts_app = typer.Typer(help="each call's facts, folded from its log", no_args_is_help=True)
drift_app = typer.Typer(help="each day's drift, counted at the seal", no_args_is_help=True)
usage_app = typer.Typer(help="each org's usage totals, from its log", no_args_is_help=True)

NOT_A_DAY = "--since {since}: a day, like 2026-09-01"
FACTS_REBUILT = (
    "{calls} calls refolded, {rewritten} facts rows rewritten, {left} left as they were:"
    " their log holds an entry this release cannot read"
)

Org = Annotated[str | None, typer.Option("--org", help="An org's calls, by its id.")]
Since = Annotated[str | None, typer.Option("--since", help="A day, YYYY-MM-DD.")]


@facts_app.command("rebuild")
@verb
async def facts_rebuild(
    ctx: typer.Context,
    call: Annotated[str | None, typer.Option("--call", help="One call.")] = None,
    org: Org = None,
    since: Since = None,
) -> int:
    """Refold the facts of the calls the flags name, every call's when none; say what changed."""
    context = context_of(ctx)
    refolding = calls.Refolding(call=call, org=org, since=day_of(since))
    async with context.sessions.begin() as session:
        done = await calls.refold_facts(session, refolding)
    if context.out.as_json:
        context.out.data(done)
    else:
        context.out.line(FACTS_REBUILT.format(calls=done.calls, rewritten=done.rewritten, left=done.left))
    return OK


@drift_app.command("rebuild")
@verb
async def drift_rebuild(ctx: typer.Context, org: Org = None, since: Since = None) -> int:
    """Forget the drift the flags name, every org's and day's when none, and count it again."""
    context = context_of(ctx)
    async with context.sessions.begin() as session:
        done = await calls.rebuild_drift(session, org=org, since=day_of(since))
    if context.out.as_json:
        context.out.data(done)
    else:
        context.out.line(f"{done.calls} sealed calls read, {done.folded} counted into their day's drift")
    return OK


@usage_app.command("rebuild")
@verb
async def usage_rebuild(ctx: typer.Context) -> int:
    """Count every org's totals again from the log, as the database's triggers count them."""
    context = context_of(ctx)
    async with context.sessions.begin() as session:
        rows = await billing.rebuild_usage_totals(session)
    context.out.line(f"usage_totals rewritten: {rows} rows of org, env and month")
    return OK


def day_of(day: str | None) -> float | None:
    """The start of a day given as YYYY-MM-DD, in UTC; None when none was given."""
    if day is None:
        return None
    try:
        return datetime.strptime(day, "%Y-%m-%d").replace(tzinfo=UTC).timestamp()
    except ValueError:
        raise ValidationError(NOT_A_DAY.format(since=day)) from None
