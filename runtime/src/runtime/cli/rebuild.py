"""`facts`, `drift`, `usage`: the read models folded again from the log, which is the record."""

from typing import Annotated

import typer

from runtime.billing.service import usage
from runtime.calls.repository.rebuild import Refolding
from runtime.calls.service import refold
from runtime.cli.command import OK, context_of, verb
from runtime.cli.terminal import day_of
from runtime.insights.service import drift
from runtime.scoping import box_wide

facts_app = typer.Typer(help="each call's facts, folded from its log", no_args_is_help=True)
drift_app = typer.Typer(help="each day's drift, counted at the seal", no_args_is_help=True)
usage_app = typer.Typer(help="each org's usage totals, from its log", no_args_is_help=True)

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
    with box_wide():
        done = await refold.rebuild(context.sessions, Refolding(call=call, org=org, since=day_of(since)))
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
        with box_wide():
            done = await drift.rebuild(session, org=org, since=day_of(since))
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
        with box_wide():
            rows = await usage.rebuild_usage_totals(session)
    context.out.line(f"usage_totals rewritten: {rows} rows of org, env and month")
    return OK
