"""`orgs provider-key`: an org's own key for a vendor, brought, taken back, listed; never shown."""

import typer

from runtime.accounts.service import orgs
from runtime.cli.command import OK, context_of, verb
from runtime.cli.terminal import read_secret_line
from runtime.providers.service import credentials, plugins, trials
from runtime.scoping import box_wide

app = typer.Typer(help="the org's own vendor keys", no_args_is_help=True)


# The key is read from stdin: argv is what `ps` shows. The vendor is asked first, as at the endpoint.
@app.command("set")
@verb
async def provider_key_set(ctx: typer.Context, org: str, vendor: str) -> int:
    """The org's own key for a vendor, read from stdin; its calls run on it from the next one."""
    context = context_of(ctx)
    key = read_secret_line()
    async with context.sessions.begin() as session:
        with box_wide():
            found = await orgs.get_org(session, org)
            await trials.bring_key(session, context.vault, found.id, vendor, key, None)
    context.out.line(f"{org} runs {plugins.parse_vendor(vendor)} on its own key from the next call")
    return OK


@app.command("rm")
@verb
async def provider_key_rm(ctx: typer.Context, org: str, vendor: str) -> int:
    """The org's key for a vendor taken back; its calls run on the runtime's from the next one."""
    context = context_of(ctx)
    named = plugins.parse_vendor(vendor)
    async with context.sessions.begin() as session:
        with box_wide():
            found = await orgs.get_org(session, org)
            await credentials.take_key_back(session, found.id, named, whose=f"org {found.slug}")
    context.out.line(f"{org} runs {named} on the runtime's key from the next call")
    return OK


@app.command("list")
@verb
async def provider_key_list(ctx: typer.Context, org: str) -> int:
    """The vendors the org brought its own key for, never the key."""
    context = context_of(ctx)
    async with context.sessions() as session:
        with box_wide():
            found = await orgs.get_org(session, org)
            context.out.lines(await credentials.list_own_vendors(session, found.id))
    return OK
