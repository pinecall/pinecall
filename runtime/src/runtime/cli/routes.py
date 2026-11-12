"""`routes`: which agent answers a number, in which env, on the services themselves."""

import json
from pathlib import Path
from typing import Annotated

import typer
from pydantic import TypeAdapter

from runtime import builders
from runtime.accounts.models import BOX_ORG
from runtime.accounts.service import orgs
from runtime.actor import Scope
from runtime.cli.command import OK, Context, context_of, verb
from runtime.cli.output import Column
from runtime.enums import Channel, Env
from runtime.scoping import box_wide
from runtime.telephony.schemas.ops import RouteRequest
from runtime.telephony.service import number_hook, numbers
from runtime.telephony.service.number_hook import NumberImport
from runtime.wire.worker import RouteRow

app = typer.Typer(help="which agent answers a number", no_args_is_help=True)

Org = Annotated[str, typer.Option("--org", help="The org, by slug or id.")]
EnvOption = Annotated[Env, typer.Option("--env")]

COLUMNS: tuple[Column[RouteRow], ...] = (
    ("number", lambda route: route.number),
    ("channel", lambda route: route.channel),
    ("agent", lambda route: route.agent),
    ("env", lambda route: route.env),
    ("managed", lambda route: route.managed),
)

_ROUTES: TypeAdapter[list[RouteRequest]] = TypeAdapter(list[RouteRequest])


@app.command("list")
@verb
async def routes_list(ctx: typer.Context, org: Org = BOX_ORG, env: EnvOption = Env.production) -> int:
    """The org's routes in an env."""
    context = context_of(ctx)
    async with context.sessions() as session:
        with box_wide():
            found = await orgs.get_org(session, org)
            routes = await numbers.list_routes_of(session, found.id, env)
    context.out.rows([RouteRow.model_validate(route, from_attributes=True) for route in routes], COLUMNS)
    return OK


@app.command("add")
@verb
async def routes_add(
    ctx: typer.Context,
    number: str,
    agent: str,
    channel: Annotated[Channel, typer.Option("--channel")] = Channel.phone,
    org: Org = BOX_ORG,
    env: EnvOption = Env.production,
) -> int:
    """Route a number the carrier already sends here; added again, it moves. A new number is the org's Numbers."""
    context = context_of(ctx)
    await _add(context, [RouteRequest(org=org, number=number, agent=agent, channel=channel, env=env)])
    return OK


@app.command("rm")
@verb
async def routes_rm(ctx: typer.Context, number: str, org: Org = BOX_ORG) -> int:
    """A route forgotten, and its admission on the SFU."""
    context = context_of(ctx)
    handles = await context.handles()
    async with handles.sessions.begin() as session:
        with box_wide():
            found = await orgs.get_org(session, org)
            await numbers.release_named(session, handles.servers, found.id, found.slug, number)
    context.out.line(f"{number} answers nowhere now")
    return OK


@app.command("seed")
@verb
async def routes_seed(ctx: typer.Context, file: Annotated[Path, typer.Argument(help="A JSON list of routes.")]) -> int:
    """A file of routes, each added: how a box comes up from a checkout."""
    context = context_of(ctx)
    await _add(context, _ROUTES.validate_python(json.loads(file.read_text(encoding="utf-8"))))
    return OK


# One row per number per org: a number added again moves. It is admitted on the SFU at once; the
# carrier is never touched, so it rings only where the carrier already points it here.
async def _add(context: Context, wanted: list[RouteRequest]) -> None:
    handles = await context.handles()
    names = builders.read_sip_names(context.settings)
    added: list[RouteRow] = []
    for route in wanted:
        async with handles.sessions.begin() as session:
            with box_wide():
                found = await orgs.get_org(session, route.org)
                asked = NumberImport(Scope(found.id, route.env), route.agent, route.number, channel=route.channel)
                typed = await number_hook.type_route(
                    session, handles.vault, handles.http, handles.servers, names, asked
                )
        added.append(RouteRow.model_validate(typed.route, from_attributes=True))
    context.out.rows(added, COLUMNS)
