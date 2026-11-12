"""The fleet endpoints: a worker's heartbeat, KEDA's demand, and the operator's fleets, floors, roster and cordons."""

import time
from typing import Annotated

from fastapi import APIRouter, Query

from runtime.auth import TheOperator
from runtime.fleet import schemas
from runtime.fleet.auth import FleetKey, TheRoster
from runtime.fleet.service import demand, envs, totals
from runtime.postgres import Session
from runtime.wire.worker import HeartbeatRequest, HeartbeatResponse

router = APIRouter()


# ── a worker's ──


@router.post("/v1/fleet/heartbeat")
async def report_heartbeat(body: HeartbeatRequest, _key: FleetKey, roster: TheRoster) -> HeartbeatResponse:
    """A worker's report; the answer says whether it is cordoned."""
    return roster.report_heartbeat(body, time.time())


# KEDA's metrics-api scaler reads `wanted` and keeps the scaled Deployment at it (infra/charts),
# asking with its env's fleet key, which names the fleet: one number needs no operator's key. The
# query says `seats=` for a worker's slots: the chart of the release that runs today sends that word.
@router.get("/v1/fleet/wanted")
async def get_demand(
    key: FleetKey,
    roster: TheRoster,
    session: Session,
    scaled: Annotated[str, Query(min_length=1)],
    slots: Annotated[int, Query(gt=0, alias="seats")],
    most: Annotated[int, Query(gt=0)] = demand.AT_MOST,
) -> schemas.FleetDemand:
    """How many workers whose names start with `scaled` the fleet wants, each of `seats` slots."""
    line = demand.Line(at_most=most, slots_per_worker=slots)
    return schemas.FleetDemand.of(await demand.demand_of_env(session, roster, key.env, scaled, line, time.time()))


# ── the operator's ──


@router.get("/v1/ops/fleets")
async def get_fleets(_actor: TheOperator, session: Session) -> schemas.Fleets:
    """The fleet of workers each env's calls are dispatched to."""
    named = await envs.get_fleets(session)
    return schemas.Fleets(production=named.production, sandbox=named.sandbox)


@router.put("/v1/ops/fleets")
async def put_fleets(body: schemas.Fleets, _actor: TheOperator, session: Session) -> schemas.Fleets:
    """The fleet of each env, replaced whole; the next dispatch reads it."""
    await envs.put_fleets(session, envs.Fleets(production=body.production, sandbox=body.sandbox))
    return body


@router.get("/v1/ops/fleets/floors")
async def get_floors(_actor: TheOperator, session: Session) -> schemas.Floors:
    """The scaled workers each env's fleet keeps warm whatever its calls."""
    floors = await demand.get_floors(session)
    return schemas.Floors(production=floors.production, sandbox=floors.sandbox)


# The floor is counted in `wanted`, so the autoscaler holds it from its next ask: no chart is released.
@router.put("/v1/ops/fleets/floors")
async def put_floors(body: schemas.Floors, actor: TheOperator, session: Session) -> schemas.Floors:
    """Each env's floor of warm workers, replaced whole."""
    floors = demand.Floors(production=body.production, sandbox=body.sandbox)
    await demand.put_floors(session, floors, by=actor.name)
    return body


@router.get("/v1/ops/fleet")
async def list_fleet(_actor: TheOperator, roster: TheRoster, session: Session) -> schemas.FleetListed:
    """Every worker heard from, of both fleets, and each fleet summed over the ones up."""
    return schemas.FleetListed.of(await totals.list_fleets(session, roster, time.time()))


# A cordon is told on the worker's next heartbeat: it takes no new call, finishes, and leaves.
@router.post("/v1/ops/fleet/{worker}/cordon", status_code=204)
async def cordon_worker(
    worker: str, _actor: TheOperator, roster: TheRoster, fleet: Annotated[str | None, Query()] = None
) -> None:
    """Cordon a worker of a fleet; the fleet is found by the worker's name when not named."""
    roster.cordon(worker, fleet)


@router.delete("/v1/ops/fleet/{worker}/cordon", status_code=204)
async def uncordon_worker(
    worker: str, _actor: TheOperator, roster: TheRoster, fleet: Annotated[str | None, Query()] = None
) -> None:
    """Take a worker's cordon back, when it has not left yet."""
    roster.uncordon(worker, fleet)
