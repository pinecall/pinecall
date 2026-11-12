"""`box keys`: the vendor keys the box holds and lends its orgs; never shown."""

import typer

from runtime.cli.command import OK, context_of, verb
from runtime.cli.terminal import read_secret_line
from runtime.postgres import BoxSession
from runtime.providers.service import credentials, plugins, trials
from runtime.scoping import box_wide

app = typer.Typer(help="the vendor keys the box holds; never shown", no_args_is_help=True)


@app.command("list")
@verb
async def box_keys_list(ctx: typer.Context) -> int:
    """Every vendor the box holds a key for, one per line; never the key."""
    context = context_of(ctx)
    async with context.sessions() as session:
        with box_wide():
            context.out.lines(await credentials.list_box_vendors(session, context.vault))
    return OK


# Offering a vendor is holding its key; read from stdin, since argv is what `ps` shows. The vendor is
# asked first, as at the operator's endpoint.
@app.command("set")
@verb
async def box_key_set(ctx: typer.Context, vendor: str) -> int:
    """Keep the box's key for the vendor, read from stdin; orgs it lends to run on it from the next call."""
    context = context_of(ctx)
    key = read_secret_line()
    async with context.sessions.begin() as session:
        with box_wide():
            await trials.bring_box_key(BoxSession(session), context.vault, vendor, key, None)
    context.out.line(
        f"the box holds a key for {plugins.parse_vendor(vendor)}: orgs it lends it to run on it from now on"
    )
    return OK


@app.command("rm")
@verb
async def box_key_rm(ctx: typer.Context, vendor: str) -> int:
    """Forget the box's key for the vendor."""
    context = context_of(ctx)
    named = plugins.parse_vendor(vendor)
    async with context.sessions.begin() as session:
        with box_wide():
            await credentials.drop_box_key(BoxSession(session), context.vault, named)
    context.out.line(f"the box holds no key for {named}: an org without its own is refused it")
    return OK
