"""`box`: the vendor keys it lends, the Twilio account it buys numbers on, and what a newborn org is given."""

from typing import Annotated

import typer

from pinecall_runtime.billing import service as billing
from pinecall_runtime.cli.command import OK, context_of, verb
from pinecall_runtime.cli.limits import lends_of
from pinecall_runtime.cli.orgs import read_secret_line
from pinecall_runtime.enums import Env
from pinecall_runtime.exceptions import NotFound, ServiceUnavailable
from pinecall_runtime.providers import service as providers
from pinecall_runtime.telephony import schemas as telephony_schemas
from pinecall_runtime.telephony import service as telephony

app = typer.Typer(help="its keys, its Twilio, what a new org gets", no_args_is_help=True)
keys_app = typer.Typer(help="the vendor keys the box holds; never shown", no_args_is_help=True)
account_app = typer.Typer(help="the Twilio account the box buys numbers on for its orgs", no_args_is_help=True)
admission_app = typer.Typer(help="what a newborn org is given, per env", no_args_is_help=True)
app.add_typer(keys_app, name="keys")
app.add_typer(account_app, name="numbers-account")
app.add_typer(admission_app, name="admission")

# The account the box buys numbers on is sealed beside the keys and is no vendor of a call.
NUMBERS_ACCOUNT = "twilio"
NO_NUMBERS_ACCOUNT = "this box holds no Twilio account to buy numbers on: `box numbers-account set` keeps one"

Limit = Annotated[int | None, typer.Option()]


@keys_app.command("list")
@verb
async def box_keys_list(ctx: typer.Context) -> int:
    """Every vendor the box holds a key for, one per line; never the key."""
    context = context_of(ctx)
    async with context.sessions() as session:
        held = await providers.box_credentials(session, context.vault)
    context.out.lines(sorted(set(held) - {NUMBERS_ACCOUNT}))
    return OK


# Offering a vendor is holding its key; read from stdin, since argv is what `ps` shows.
@keys_app.command("set")
@verb
async def box_key_set(ctx: typer.Context, vendor: str) -> int:
    """Keep the box's key for the vendor, read from stdin; orgs it lends to run on it from the next call."""
    context = context_of(ctx)
    named = providers.installed_vendor(vendor)
    credentials = read_secret_line()
    async with context.sessions.begin() as session:
        await providers.put_box_credentials(session, context.vault, named, credentials)
    context.out.line(f"the box holds a key for {named}: orgs it lends it to run on it from now on")
    return OK


@keys_app.command("rm")
@verb
async def box_key_rm(ctx: typer.Context, vendor: str) -> int:
    """Forget the box's key for the vendor."""
    context = context_of(ctx)
    named = providers.installed_vendor(vendor)
    async with context.sessions.begin() as session:
        if not await providers.drop_box_credentials(session, context.vault, named):
            raise NotFound(f"this box holds no key for {named}")
    context.out.line(f"the box holds no key for {named}: an org without its own is refused it")
    return OK


@account_app.command("show")
@verb
async def numbers_account_show(ctx: typer.Context) -> int:
    """The account the box buys numbers on: its SID and label, never its secret."""
    context = context_of(ctx)
    async with context.sessions() as session:
        try:
            account = await telephony.box_twilio(session, context.vault)
        except ServiceUnavailable:
            raise NotFound(NO_NUMBERS_ACCOUNT) from None
    shown = telephony_schemas.NumbersAccount(account_sid=account.account_sid, label=account.label)
    if context.out.as_json:
        context.out.data(shown)
    else:
        context.out.line(" · ".join(part for part in (shown.account_sid, shown.label) if part))
    return OK


# Tried against Twilio before it is kept, as an org's account is: a pair Twilio refuses is never
# the account a purchase fails on later.
@account_app.command("set")
@verb
async def numbers_account_set(
    ctx: typer.Context,
    account_sid: Annotated[str, typer.Option("--account-sid", metavar="<AC…>")],
    user: Annotated[str | None, typer.Option("--user", metavar="<SK… or the account SID>")] = None,
    label: Annotated[str, typer.Option("--label")] = "",
) -> int:
    """Keep the account the box buys numbers on; the secret (the API key's, or the auth token) on stdin."""
    context = context_of(ctx)
    account = telephony.TwilioAccount(
        account_sid=account_sid, user=user or account_sid, secret=read_secret_line(), label=label
    )
    await telephony.verify_account(await context.http(), account)
    async with context.sessions.begin() as session:
        await telephony.put_box_twilio(session, context.vault, account)
    context.out.line(f"the box buys numbers on {account.account_sid} from now on")
    return OK


@account_app.command("rm")
@verb
async def numbers_account_rm(ctx: typer.Context) -> int:
    """Forget the account: the box sells no numbers, and the ones it bought keep ringing."""
    context = context_of(ctx)
    async with context.sessions.begin() as session:
        if not await telephony.drop_box_twilio(session, context.vault):
            raise NotFound(NO_NUMBERS_ACCOUNT)
    context.out.line("the box buys no numbers now; the ones it bought keep ringing")
    return OK


@admission_app.command("show")
@verb
async def admission_show(ctx: typer.Context) -> int:
    """What a newborn org is given in each env, whole."""
    context = context_of(ctx)
    async with context.sessions() as session:
        context.out.data(await billing.get_admission(session))
    return OK


# Read at the moment an org is made: the orgs already made keep their quotas.
@admission_app.command("set")
@verb
async def admission_set(
    ctx: typer.Context,
    env: Annotated[Env, typer.Option("--env")],
    later: Annotated[bool, typer.Option("--later", help="A person's later orgs, not their first.")] = False,
    minutes: Limit = None,
    messages: Limit = None,
    agents: Limit = None,
    concurrent_calls: Limit = None,
    memory_facts: Limit = None,
    knowledge_chunks: Limit = None,
    numbers: Limit = None,
    seats: Limit = None,
    llm_tokens: Limit = None,
    hosted_apps: Limit = None,
    evals: Limit = None,
    simulations: Limit = None,
    budget_usd: Limit = None,
    lends: Annotated[str, typer.Option("--lends", metavar="<vendor[/model],…|all|none>")] = "all",
) -> int:
    """One env's limits for a new org, replaced whole; the rest of the row as it stands."""
    context = context_of(ctx)
    lent = lends_of(lends)
    quotas = billing.Quotas(
        minutes=minutes,
        messages=messages,
        agents=agents,
        concurrent_calls=concurrent_calls,
        memory_facts=memory_facts,
        knowledge_chunks=knowledge_chunks,
        numbers=numbers,
        seats=seats,
        llm_tokens=llm_tokens,
        hosted_apps=hosted_apps,
        evals=evals,
        simulations=simulations,
        budget_usd=budget_usd,
        lends=None if lent is None else providers.parse_lending(lent),
    )
    async with context.sessions.begin() as session:
        row = await billing.get_admission(session)
        changed = (
            row.model_copy(update={"later": {**(row.later or {}), env: quotas}})
            if later
            else row.model_copy(update={"first": {**row.first, env: quotas}})
        )
        await billing.set_admission(session, changed)
    context.out.data(changed)
    return OK
