"""The fleet endpoints: a worker's heartbeat, KEDA's demand, LiveKit's events, the operator's roster."""

import time
from typing import Annotated

from fastapi import APIRouter, Query, Request

from pinecall_runtime.calls import service as calls
from pinecall_runtime.enums import Env
from pinecall_runtime.exceptions import NotFound, Unauthorized
from pinecall_runtime.fleet import schemas
from pinecall_runtime.fleet.auth import FleetKey, TheOperator
from pinecall_runtime.fleet.service import arrivals, envs, rooms
from pinecall_runtime.fleet.service.demand import Line, wanted_scaled
from pinecall_runtime.fleet.service.offers import Offering
from pinecall_runtime.fleet.service.roster import STALE_AFTER_S, Roster
from pinecall_runtime.kit.handles import TheHandles
from pinecall_runtime.kit.http import capped_body
from pinecall_runtime.postgres import Session
from pinecall_runtime.telephony import service as telephony

router = APIRouter()

LARGEST_WEBHOOK = 4 * 1024 * 1024

NO_SUCH_WORKER = "no worker {worker} was heard from: the roster lists the ones that were"


# ── a worker's ──


@router.post("/v1/fleet/heartbeat")
async def report_heartbeat(
    body: schemas.HeartbeatRequest, _key: FleetKey, request: Request
) -> schemas.HeartbeatResponse:
    """A worker's report; the answer says whether it is cordoned and its fleet full."""
    return _roster(request).report_heartbeat(body, time.time())


# KEDA's metrics-api scaler reads `wanted` and keeps the scaled Deployment at it (infra/charts),
# asking with its env's fleet key, which names the fleet: one number needs no operator's key.
@router.get("/v1/fleet/wanted")
async def wanted_workers(
    key: FleetKey,
    request: Request,
    session: Session,
    scaled: Annotated[str, Query(min_length=1)],
    seats: Annotated[int, Query(gt=0)],
    most: Annotated[int, Query(gt=0)] = Line.at_most,
) -> schemas.FleetDemand:
    """How many workers whose names start with `scaled` the fleet wants, each of `seats` seats."""
    fleet = await envs.fleet_of_env(session, key.env)
    now = time.time()
    demand = wanted_scaled(
        _roster(request).workers_of(fleet, now), scaled, Line(at_most=most, seats_per_worker=seats), now
    )
    return schemas.FleetDemand(fleet=fleet, wanted=demand.wanted, active=demand.active, seats=demand.seats)


# livekit sends its token bare in Authorization, and every room event of the box: all but an
# agent lost mid-call are answered and let be. Each env's LiveKit names its env in the URL its
# config sends to, so the room is asked of the LiveKit it lives on.
@router.post("/v1/livekit/webhook", status_code=204)
async def receive_livekit_event(
    request: Request, handles: TheHandles, session: Session, env: Annotated[Env, Query()] = Env.production
) -> None:
    """A room event LiveKit signed: a caller alone is offered a worker; an agent lost, told."""
    token = request.headers.get("Authorization")
    if not token:
        raise Unauthorized("the event carries no Authorization: LiveKit signs every event it sends")
    settings = handles.settings
    body = (await capped_body(request, LARGEST_WEBHOOK, "a webhook's body")).decode()
    event = rooms.livekit_event(
        body,
        token,
        settings.livekit_api_key or "",
        settings.livekit_api_secret.get_secret_value() if settings.livekit_api_secret else "",
    )
    offering = _offering(request)
    # In this order: a worker gone sends the sentence, a caller alone is offered a worker, a room
    # an agent joined or that ended is let go, and a room a hand-over bridges goes with either of
    # its legs; each event moves one of the four.
    serving: calls.Serving = request.app.state.serving
    await calls.stranded(session, serving, offering, env, event)
    await arrivals.offer_arrival(offering, env, event)
    await arrivals.forget_settled(offering, event)
    await telephony.unbridged(handles.servers[env], event)


# ── the operator's ──


@router.get("/v1/ops/fleets")
async def get_fleets(_actor: TheOperator, session: Session) -> schemas.Fleets:
    """The fleet of workers each env's calls are dispatched to."""
    return await envs.fleets(session)


@router.put("/v1/ops/fleets")
async def put_fleets(body: schemas.Fleets, _actor: TheOperator, session: Session) -> schemas.Fleets:
    """The fleet of each env, replaced whole; the next dispatch reads it."""
    await envs.set_fleets(session, body)
    return body


@router.get("/v1/ops/fleet")
async def list_fleet(_actor: TheOperator, request: Request, session: Session) -> schemas.FleetListed:
    """Every worker heard from, of both fleets, and each fleet summed over the ones up."""
    now = time.time()
    named = await envs.fleets(session)
    both = list(dict.fromkeys((named.production, named.sandbox)))
    roster = _roster(request)
    waiting = await _offering(request).waiting(now)
    return schemas.FleetListed(
        now=now,
        stale_after_s=STALE_AFTER_S,
        workers=[seat for fleet in both for seat in roster.workers_of(fleet, now)],
        totals=[roster.totals_of(fleet, now).model_copy(update={"waiting": waiting.get(fleet, 0)}) for fleet in both],
    )


# A cordon is told on the worker's next heartbeat: it takes no new call, finishes, and leaves.
@router.post("/v1/ops/fleet/{worker}/cordon", status_code=204)
async def cordon_worker(
    worker: str, _actor: TheOperator, request: Request, fleet: Annotated[str | None, Query()] = None
) -> None:
    """Cordon a worker of a fleet; the fleet is found by the worker's name when not named."""
    roster = _roster(request)
    if not roster.cordon_worker(fleet or roster.fleet_of_worker(worker) or "", worker):
        raise NotFound(NO_SUCH_WORKER.format(worker=worker))


@router.delete("/v1/ops/fleet/{worker}/cordon", status_code=204)
async def uncordon_worker(
    worker: str, _actor: TheOperator, request: Request, fleet: Annotated[str | None, Query()] = None
) -> None:
    """Take a worker's cordon back, when it has not left yet."""
    roster = _roster(request)
    if not roster.cordon_worker(fleet or roster.fleet_of_worker(worker) or "", worker, on=False):
        raise NotFound(NO_SUCH_WORKER.format(worker=worker))


# ── private ──


def _roster(request: Request) -> Roster:
    roster: Roster = request.app.state.roster
    return roster


def _offering(request: Request) -> Offering:
    offering: Offering = request.app.state.offering
    return offering
