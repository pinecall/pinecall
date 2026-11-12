"""`orgs quota|lends|simulating|dialling|sso`: an org's limits, lends, simulations' shape, dial guards, provider."""

from typing import Annotated

import typer

from runtime.accounts.service import orgs
from runtime.billing import schemas as billing
from runtime.billing.service import quotas
from runtime.cli.command import OK, context_of, verb
from runtime.compliance import schemas as compliance
from runtime.compliance.service import dial_guards
from runtime.enums import Env
from runtime.providers.service.keyring import parse_lending
from runtime.scoping import box_wide
from runtime.signin import schemas as signin
from runtime.signin.service import sso
from runtime.wire.parts import QuotaName

EnvOption = Annotated[Env, typer.Option("--env")]
Limit = Annotated[int | None, typer.Option()]
Lends = Annotated[str, typer.Argument(help="vendor[/model],… | all | none", metavar="<lends>")]


# What the box lends is `orgs lends`'s: the quota written here keeps what it lends and its simulations' shape.
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
    """The org's limits in one env, replaced whole; what the box lends it and its simulations' shape are kept."""
    context = context_of(ctx)
    limits: dict[QuotaName, int | None] = {
        "minutes": minutes,
        "messages": messages,
        "agents": agents,
        "concurrent_calls": concurrent_calls,
        "memory_facts": memory_facts,
        "knowledge_chunks": knowledge_chunks,
        "numbers": numbers,
        "seats": seats,
        "llm_tokens": llm_tokens,
        "hosted_apps": hosted_apps,
        "evals": evals,
        "simulations": simulations,
        "budget_usd": budget_usd,
    }
    async with context.sessions.begin() as session:
        with box_wide():
            found = await orgs.get_org(session, org)
            current = await quotas.get_quotas(session, found.id, env)
            kept = await quotas.put_limits(session, found.id, env, limits, current.lends)
    context.out.data(billing.OrgQuotas.of(kept))
    return OK


# A shape, not a month's count: left out, each is the platform's own again.
@verb
async def orgs_simulating(
    ctx: typer.Context, org: str, env: EnvOption, at_once: Limit = None, comparison_calls: Limit = None
) -> int:
    """How the org's simulations are shaped in one env; its limits and what the box lends it are kept."""
    context = context_of(ctx)
    async with context.sessions.begin() as session:
        with box_wide():
            found = await orgs.get_org(session, org)
            kept = await quotas.put_simulating(
                session, found.id, env, simulations_at_once=at_once, comparison_calls=comparison_calls
            )
    context.out.data(billing.OrgQuotas.of(kept))
    return OK


@verb
async def orgs_lends(ctx: typer.Context, org: str, env: EnvOption, lends: Lends) -> int:
    """The vendors the box lends the org its keys for in one env; its limits are kept."""
    context = context_of(ctx)
    lent = lends_of(lends)
    async with context.sessions.begin() as session:
        with box_wide():
            found = await orgs.get_org(session, org)
            current = await quotas.get_quotas(session, found.id, env)
            limits: dict[QuotaName, int | None] = {**current.limits, "budget_usd": current.budget_usd}
            lending = None if lent is None else parse_lending(lent)
            kept = await quotas.put_limits(session, found.id, env, limits, lending)
    context.out.data(billing.OrgQuotas.of(kept))
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
    wanted = dial_guards.read_guards(dial_anywhere, per_minute, per_day, max_duration_s)
    async with context.sessions.begin() as session:
        with box_wide():
            found = await orgs.get_org(session, org)
            kept = await dial_guards.put_guards(session, found.id, wanted)
    context.out.data(compliance.DialGuards.of(kept))
    return OK


# The break-glass: `--off` lets a password open the org again while its provider is down. Never the
# other way: requiring the provider is the org's own call.
@verb
async def orgs_sso(ctx: typer.Context, org: str, off: Annotated[bool, typer.Option("--off")] = False) -> int:
    """Which provider the org signs in with; `--off` lets a password open it again."""
    context = context_of(ctx)
    callback = f"{context.settings.base_url}{signin.SSO_CALLBACK}"
    async with context.sessions.begin() as session:
        with box_wide():
            found = await orgs.get_org(session, org)
            if off:
                wiring = await sso.set_required(session, context.vault, found, required=False, redirect_uri=callback)
            else:
                wiring = await sso.wiring_of(session, context.vault, found.id, redirect_uri=callback)
    row = signin.SsoRow.of(wiring)
    if context.out.as_json:
        context.out.data(row)
    elif not row.configured:
        context.out.line(f"org {found.slug} signs in with no identity provider")
    else:
        required = "required" if row.required else "a password opens it too"
        context.out.line(f"{row.issuer}  client {row.client_id}  {required}")
    return OK
