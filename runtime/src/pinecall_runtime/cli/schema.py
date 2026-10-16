"""`migrate`: the schema brought up to this release, where it stands, and the steps a run applies."""

import typer

from pinecall_runtime.cli.command import FOUND_WRONG, OK, context_of, verb
from pinecall_runtime.platform import service as platform

app = typer.Typer(help="the schema", no_args_is_help=True)


@app.command("up")
@verb
async def migrate_up(ctx: typer.Context) -> int:
    """Apply what the database lacks: the SQL history on a new one, then every revision; and say which."""
    context = context_of(ctx)
    history, standing = await platform.migrate_database(context.engine)
    ran = ", ".join(history.applied) or "nothing of the history: it was there"
    context.out.line(f"history: {ran}")
    context.out.line(f"revision: {standing.current or '-'}")
    role = context.settings.db_app_role
    if role:
        await platform.grant_rows(context.engine, role)
        context.out.line(f"{role}: every table's rows, no table's shape")
    return OK


@app.command("status")
@verb
async def migrate_status(ctx: typer.Context) -> int:
    """What the database has not run yet; the exit is 1 while it is behind."""
    context = context_of(ctx)
    standing = await platform.schema_standing(context.engine)
    if context.out.as_json:
        context.out.data(standing)
    elif not standing.behind:
        context.out.line(f"up to date at {standing.head}")
    else:
        pending = ", ".join(standing.history_pending) or "none"
        context.out.line(f"history pending: {pending}")
        context.out.line(f"revision: {standing.current or 'untracked'} (head {standing.head})")
    return FOUND_WRONG if standing.behind else OK


@app.command("plan")
@verb
async def migrate_plan(ctx: typer.Context) -> int:
    """Every step a run applies to an empty database, in order; no database asked."""
    context_of(ctx).out.lines(platform.planned_steps())
    return OK
