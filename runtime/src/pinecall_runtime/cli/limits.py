"""`orgs quota|lends|dialling|sso`: an org's limits, what the box lends it, its dial guards, its identity provider."""

import dataclasses
from collections.abc import Callable
from typing import Annotated

import typer

from pinecall_runtime.accounts.service import orgs, sso
from pinecall_runtime.billing import schemas as billing_schemas
from pinecall_runtime.billing import service as billing
from pinecall_runtime.cli.command import OK, context_of, verb
from pinecall_runtime.enums import Env
from pinecall_runtime.exceptions import NotFound
from pinecall_runtime.providers import service as providers
from pinecall_runtime.telephony import schemas as telephony_schemas
from pinecall_runtime.telephony import service as telephony

EnvOption = Annotated[Env, typer.Option("--env")]
Limit = Annotated[int | None, typer.Option()]
Lends = Annotated[str, typer.Argument(help="vendor[/model],… | all | none", metavar="<lends>")]
NO_SSO = "org {slug} signs in with no identity provider"


# What the box lends is `orgs lends`'s: a quota written without it would lend every key.
@verb
async def orgs_quota(
    ctx: typer.Context,
    org: str,
    env: EnvOption,
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
) -> int:
    """The org's limits in one env, replaced whole; what the box lends it is kept."""
    context = context_of(ctx)
    async with context.sessions.begin() as session:
        found = await orgs.get_org(session, org)
        current = await billing.get_quotas(session, found.id, env)
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
            lends=current.lends,
        )
        await billing.set_quotas(session, found.id, env, quotas)
    context.out.data(billing_schemas.OrgQuotas.of(quotas))
    return OK


@verb
async def orgs_lends(ctx: typer.Context, org: str, env: EnvOption, lends: Lends) -> int:
    """The vendors the box lends the org its keys for in one env; its limits are kept."""
    context = context_of(ctx)
    lent = lends_of(lends)
    async with context.sessions.begin() as session:
        found = await orgs.get_org(session, org)
        current = await billing.get_quotas(session, found.id, env)
        quotas = dataclasses.replace(current, lends=None if lent is None else providers.parse_lending(lent))
        await billing.set_quotas(session, found.id, env, quotas)
    context.out.data(billing_schemas.OrgQuotas.of(quotas))
    return OK


def lends_of(written: str) -> list[str] | None:
    """`all` lends every key the box holds, `none` none, else the vendor[/model] entries named."""
    if written == "all":
        return None
    if written == "none":
        return []
    return [entry.strip() for entry in written.split(",") if entry.strip()]


# The operator's: an org able to lift its own dial guards would have none.
@verb
async def orgs_dialling(
    ctx: typer.Context,
    org: str,
    dial_anywhere: Annotated[bool | None, typer.Option("--dial-anywhere/--no-dial-anywhere")] = None,
    per_minute: Limit = None,
    per_day: Limit = None,
    max_duration_s: Limit = None,
) -> int:
    """The org's dial guards, replaced whole; one left out is the default."""
    context = context_of(ctx)
    wanted = telephony_schemas.PutDialGuards(
        dial_anywhere=dial_anywhere, per_minute=per_minute, per_day=per_day, max_duration_s=max_duration_s
    )
    guards = telephony.Guards(**wanted.model_dump(exclude_none=True))
    async with context.sessions.begin() as session:
        found = await orgs.get_org(session, org)
        await telephony.put_guards(session, found.id, guards)
    context.out.data(telephony_schemas.DialGuards(**dataclasses.asdict(guards)))
    return OK


# The break-glass: `--off` lets a password open the org again while its provider is down. Never the
# other way: requiring the provider is the org's own call.
@verb
async def orgs_sso(ctx: typer.Context, org: str, off: Annotated[bool, typer.Option("--off")] = False) -> int:
    """Which provider the org signs in with; `--off` lets a password open it again."""
    context = context_of(ctx)
    async with context.sessions.begin() as session:
        found = await orgs.get_org(session, org)
        wired = await sso.get_provider(session, context.vault, found.id)
        if wired is not None and off:
            await sso.put_provider(session, context.vault, dataclasses.replace(wired, required=False))
            wired = dataclasses.replace(wired, required=False)
        elif wired is None and off:
            raise NotFound(NO_SSO.format(slug=found.slug))
        row = sso.sso_row(wired, context.base_url, await sso.proofs_of(session, found.id))
    if context.out.as_json:
        context.out.data(row)
    elif not row.configured:
        context.out.line(NO_SSO.format(slug=found.slug))
    else:
        required = "required" if row.required else "a password opens it too"
        context.out.line(f"{row.issuer}  client {row.client_id}  {required}")
    return OK


# Registered under `orgs` by the root app, so the group reads as one.
VERBS: dict[str, Callable[..., None]] = {
    "quota": orgs_quota,
    "lends": orgs_lends,
    "dialling": orgs_dialling,
    "sso": orgs_sso,
}
