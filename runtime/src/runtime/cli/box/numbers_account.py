"""`box numbers-account`: the Twilio account the box buys numbers on for its orgs."""

from typing import Annotated

import typer

from runtime.cli.command import OK, context_of, verb
from runtime.cli.terminal import read_secret_line
from runtime.postgres import BoxSession
from runtime.scoping import box_wide
from runtime.telephony.schemas.ops import NumbersAccount
from runtime.telephony.service import accounts
from runtime.telephony.service.twilio import TwilioAccount

app = typer.Typer(help="the Twilio account the box buys numbers on for its orgs", no_args_is_help=True)


@app.command("show")
@verb
async def numbers_account_show(ctx: typer.Context) -> int:
    """The account the box buys numbers on: its SID and label, never its secret."""
    context = context_of(ctx)
    async with context.sessions() as session:
        with box_wide():
            shown = NumbersAccount.of(await accounts.get_numbers_account(session, context.vault))
    if context.out.as_json:
        context.out.data(shown)
    else:
        context.out.line(" · ".join(part for part in (shown.account_sid, shown.label) if part))
    return OK


# Tried against Twilio before it is kept, as an org's account is: a pair Twilio refuses is never
# the account a purchase fails on later.
@app.command("set")
@verb
async def numbers_account_set(
    ctx: typer.Context,
    account_sid: Annotated[str, typer.Option("--account-sid", metavar="<AC…>")],
    user: Annotated[str | None, typer.Option("--user", metavar="<SK… or the account SID>")] = None,
    label: Annotated[str, typer.Option("--label")] = "",
) -> int:
    """Keep the account the box buys numbers on; the secret (the API key's, or the auth token) on stdin."""
    context = context_of(ctx)
    account = TwilioAccount(account_sid, user or account_sid, read_secret_line(), label)
    handles = await context.handles()
    async with handles.sessions.begin() as session:
        with box_wide():
            kept = await accounts.put_box_twilio(BoxSession(session), handles.vault, handles.http, account)
    context.out.line(f"the box buys numbers on {kept.account_sid} from now on")
    return OK


@app.command("rm")
@verb
async def numbers_account_rm(ctx: typer.Context) -> int:
    """Forget the account: the box sells no numbers, and the ones it bought keep ringing."""
    context = context_of(ctx)
    async with context.sessions.begin() as session:
        with box_wide():
            await accounts.delete_box_twilio(BoxSession(session))
    context.out.line("the box buys no numbers now; the ones it bought keep ringing")
    return OK
