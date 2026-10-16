"""`routes`: which agent answers a number, in which env, on the services themselves."""

import json
from pathlib import Path
from typing import Annotated

import typer
from pydantic import TypeAdapter

from pinecall_runtime.accounts.models import DEFAULT_ORG
from pinecall_runtime.accounts.service import orgs
from pinecall_runtime.channels import schemas
from pinecall_runtime.channels import service as channels
from pinecall_runtime.cli.command import OK, Context, context_of, verb
from pinecall_runtime.cli.output import Column
from pinecall_runtime.enums import Channel, Env
from pinecall_runtime.exceptions import NotFound
from pinecall_runtime.kit.auth import Scope
from pinecall_runtime.kit.text import parse_e164
from pinecall_runtime.telephony import service as telephony

app = typer.Typer(help="which agent answers a number", no_args_is_help=True)

Org = Annotated[str, typer.Option("--org", help="The org, by slug or id.")]
EnvOption = Annotated[Env, typer.Option("--env")]

COLUMNS: tuple[Column[schemas.RouteRow], ...] = (
    ("number", lambda route: route.number),
    ("channel", lambda route: route.channel),
    ("agent", lambda route: route.agent),
    ("env", lambda route: route.env),
    ("managed", lambda route: route.managed),
)

_ROUTES: TypeAdapter[list[schemas.RouteRequest]] = TypeAdapter(list[schemas.RouteRequest])


@app.command("list")
@verb
async def routes_list(ctx: typer.Context, org: Org = DEFAULT_ORG, env: EnvOption = Env.production) -> int:
    """The org's routes in an env."""
    context = context_of(ctx)
    async with context.sessions() as session:
        found = await orgs.get_org(session, org)
        routes = await channels.routes_of_org(session, found.id, env)
    context.out.rows([schemas.RouteRow.model_validate(route, from_attributes=True) for route in routes], COLUMNS)
    return OK


@app.command("add")
@verb
async def routes_add(
    ctx: typer.Context,
    number: str,
    agent: str,
    channel: Annotated[Channel, typer.Option("--channel")] = Channel.phone,
    org: Org = DEFAULT_ORG,
    env: EnvOption = Env.production,
) -> int:
    """Route a number the carrier already sends here; added again, it moves. A new number is the org's Numbers."""
    context = context_of(ctx)
    wanted = schemas.RouteRequest(org=org, number=number, agent=agent, channel=channel, env=env)
    await _added(context, [wanted])
    return OK


@app.command("rm")
@verb
async def routes_rm(ctx: typer.Context, number: str, org: Org = DEFAULT_ORG) -> int:
    """A route forgotten."""
    context = context_of(ctx)
    handles = await context.handles()
    async with context.sessions.begin() as session:
        found = await orgs.get_org(session, org)
        route = await channels.get_route(session, found.id, parse_e164(number))
        if route is None:
            raise NotFound(f"no route for {number} in org {org}")
        await telephony.release_number(session, handles, found.id, route.number, route.env)
    context.out.line(f"{number} answers nowhere now")
    return OK


@app.command("seed")
@verb
async def routes_seed(ctx: typer.Context, file: Annotated[Path, typer.Argument(help="A JSON list of routes.")]) -> int:
    """A file of routes, each added: how a box comes up from a checkout."""
    context = context_of(ctx)
    await _added(context, _ROUTES.validate_python(json.loads(file.read_text(encoding="utf-8"))))
    return OK


# One row per number per org: a number added again moves. It is admitted on the SFU at once; the
# carrier is never touched, so it rings only where the carrier already points it here.
async def _added(context: Context, wanted: list[schemas.RouteRequest]) -> None:
    handles = await context.handles()
    added: list[schemas.RouteRow] = []
    for route in wanted:
        async with context.sessions.begin() as session:
            found = await orgs.get_org(session, route.org)
            asked = telephony.NumberImport(Scope(found.id, route.env), route.agent, route.number, channel=route.channel)
            typed = await telephony.type_route(session, handles, asked)
        added.append(schemas.RouteRow.model_validate(typed.route, from_attributes=True))
    context.out.rows(added, COLUMNS)
