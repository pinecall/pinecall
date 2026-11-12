"""`box admission`: what a newborn org is given in each env, its first org and a person's later ones."""

import dataclasses
from typing import Annotated

import typer

from runtime.billing.service import admission
from runtime.billing.service.quotas import Quotas
from runtime.cli.command import OK, context_of, verb
from runtime.cli.orgs.limits import lends_of
from runtime.enums import Env
from runtime.providers.service.keyring import parse_lending
from runtime.scoping import box_wide
from runtime.wire.parts import QuotaName

app = typer.Typer(help="what a newborn org is given, per env", no_args_is_help=True)

Limit = Annotated[int | None, typer.Option()]


@app.command("show")
@verb
async def admission_show(ctx: typer.Context) -> int:
    """What a newborn org is given in each env, whole."""
    context = context_of(ctx)
    async with context.sessions() as session:
        with box_wide():
            context.out.data(admission.dump_admission(await admission.get_admission(session)))
    return OK


# Read at the moment an org is made: the orgs already made keep their quotas.
@app.command("set")
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
    quotas = Quotas.of_limits(limits, lends=None if lent is None else parse_lending(lent))
    async with context.sessions.begin() as session:
        with box_wide():
            row = await admission.get_admission(session)
            if later:
                changed = dataclasses.replace(row, later={**(row.later or {}), env: quotas})
            else:
                changed = dataclasses.replace(row, first={**row.first, env: quotas})
            await admission.put_admission(session, changed)
    context.out.data(admission.dump_admission(changed))
    return OK
