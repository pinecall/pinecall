"""`fleet`, `fence`, `sip`: the workers heard from, the networks 5060 opens to, where carriers send each env."""

from typing import Annotated

import typer

from pinecall_runtime.cli.command import OK, context_of, verb
from pinecall_runtime.enums import Env
from pinecall_runtime.exceptions import ValidationError
from pinecall_runtime.fleet import schemas
from pinecall_runtime.fleet import service as fleet
from pinecall_runtime.telephony import service as telephony_service

app = typer.Typer(help="the workers heard from, and a cordon", no_args_is_help=True)
fence_app = typer.Typer(help="the networks 5060 opens to", no_args_is_help=True)
sip_app = typer.Typer(help="where the carriers send each env's calls", no_args_is_help=True)

FLEET = "/v1/ops/fleet"
NOT_AN_ENV_NAME = "--from takes ENV=NAME, like production=box.example.com; {given!r} is not"


# The roster and its cordons live in the gateways' memory, said between them every heartbeat: these
# three verbs ask a gateway, the one place that knows.
@app.command("list")
@verb
async def fleet_list(
    ctx: typer.Context, named: Annotated[str | None, typer.Option("--fleet", help="One fleet's workers.")] = None
) -> int:
    """The roster the gateway hears, one line per worker, and each fleet's totals."""
    context = context_of(ctx)
    listed = await (await context.ops()).read("GET", FLEET, schemas.FleetListed)
    workers = [seat for seat in listed.workers if named is None or seat.fleet == named]
    if context.out.as_json:
        context.out.data(listed)
        return OK

    def standing(seat: schemas.WorkerStatus) -> str:
        return fleet.worker_state(seat, [other for other in listed.workers if other.fleet == seat.fleet], listed.now)

    context.out.rows(
        workers,
        (
            ("fleet", lambda seat: seat.fleet),
            ("worker", lambda seat: seat.worker),
            ("held", lambda seat: seat.active),
            ("seats", lambda seat: "cpu" if seat.max_jobs is None else seat.max_jobs),
            ("load", lambda seat: seat.load),
            ("standing", standing),
            ("heard", lambda seat: f"{listed.now - seat.seen_at:.0f}s ago"),
        ),
    )
    for summed in listed.totals:
        if named is not None and summed.fleet != named:
            continue
        full = "  FULL" if summed.full else ""
        waiting = f" · {summed.waiting} waiting for a worker" if summed.waiting else ""
        context.out.line(
            f"\n{summed.fleet}: {summed.workers} up · {summed.active} calls · {summed.free} seats free · "
            f"{summed.accepting} accepting{waiting}{full}"
        )
    return OK


@app.command("cordon")
@verb
async def fleet_cordon(ctx: typer.Context, worker: str) -> int:
    """A worker told, on its next heartbeat, to take no new call and leave."""
    context = context_of(ctx)
    await (await context.ops()).send("POST", f"{FLEET}/{worker}/cordon")
    context.out.line(f"{worker} is cordoned: it finishes what it holds and leaves")
    return OK


@app.command("uncordon")
@verb
async def fleet_uncordon(ctx: typer.Context, worker: str) -> int:
    """A worker's cordon taken back."""
    context = context_of(ctx)
    await (await context.ops()).send("DELETE", f"{FLEET}/{worker}/cordon")
    context.out.line(f"{worker} takes calls again")
    return OK


# The orgs' addresses: written to an ignored tfvars file, never committed (infra/README.md).
@fence_app.command("export")
@verb
async def fence_export(ctx: typer.Context) -> int:
    """Every network 5060 opens to, the carriers' first, as Terraform's `sip_sources`."""
    context = context_of(ctx)
    async with context.sessions() as session:
        found = await telephony_service.openings(session)
    context.out.data({"sip_sources": telephony_service.every_network(found)})
    return OK


@sip_app.command("repoint")
@verb
async def sip_repoint(
    ctx: typer.Context,
    former: Annotated[
        list[str] | None,
        typer.Option("--from", help="ENV=NAME: a name the env was reached at before, its trunks sent on too."),
    ] = None,
) -> int:
    """Every carrier trunk at an env's name sent on to its SIP name, once; each trunk a line."""
    context = context_of(ctx)
    before: dict[Env, list[str]] = {}
    for given in former or []:
        env, equals, name = given.partition("=")
        if not equals or env not in Env.__members__.values() or not name:
            raise ValidationError(NOT_AN_ENV_NAME.format(given=given))
        before.setdefault(Env(env), []).append(name)
    handles = await context.handles()
    async with context.sessions.begin() as session:
        moved = await telephony_service.repointed(session, handles, before)
    context.out.rows(
        moved,
        (
            ("account", lambda item: item.account),
            ("trunk", lambda item: item.trunk),
            ("env", lambda item: item.world),
            ("was", lambda item: item.was),
            ("now", lambda item: item.now),
        ),
    )
    context.out.line(f"{len(moved)} trunks sent on")
    return OK
