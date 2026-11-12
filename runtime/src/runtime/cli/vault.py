"""`vault`: every sealed value of the box re-sealed under the key PINECALL_VAULT_KEY names first."""

import typer

from runtime.cli.command import FOUND_WRONG, OK, context_of, verb
from runtime.platform.service.vault import reseal_everything
from runtime.scoping import box_wide

app = typer.Typer(help="the key every secret is sealed under", no_args_is_help=True)


# Nothing is re-sealed that no key opens: that row is named, and the old key stays until it is 0.
@app.command("rotate")
@verb
async def vault_rotate(ctx: typer.Context) -> int:
    """Every sealed value re-sealed under PINECALL_VAULT_KEY's first key; 1 while one opens not."""
    context = context_of(ctx)
    with box_wide():
        columns = await reseal_everything(context.sessions, context.vault)
    context.out.rows(
        columns,
        (
            ("column", lambda c: c.column.named),
            ("re-sealed", lambda c: c.resealed),
            ("under the first key", lambda c: c.current),
            ("opened by no key", lambda c: c.unopened),
            ("moved meanwhile", lambda c: c.moved),
        ),
    )
    return OK if all(column.unopened == 0 for column in columns) else FOUND_WRONG
