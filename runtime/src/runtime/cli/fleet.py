"""`fleet`: the workers the gateways hear, each fleet's totals, and a cordon; asked of a gateway."""

from typing import Annotated

import typer

from runtime.cli.command import OK, context_of, verb
from runtime.fleet import schemas
from runtime.fleet.service import slots
from runtime.wire.signal import WorkerStatus

app = typer.Typer(help="the workers heard from, and a cordon", no_args_is_help=True)

FLEET = "/v1/ops/fleet"


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

    def standing(seat: WorkerStatus) -> str:
        return slots.state_of(seat, [other for other in listed.workers if other.fleet == seat.fleet], listed.now)

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
