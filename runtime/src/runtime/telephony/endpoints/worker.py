"""What a worker asks of telephony: a call's routes, a leg's trunk past its guards, and whose a ring is."""

from typing import Annotated

from fastapi import APIRouter, Query

from runtime.agents.auth import KnownAgent
from runtime.compliance.service import dial_guards
from runtime.handles import TheServers, TheSessions, TheVault
from runtime.kit.time import now
from runtime.postgres import Session
from runtime.telephony.auth import FleetKey, TheAgentsHeld, TheSipNames, WorkerKey
from runtime.telephony.service import hand_over, outbound, routes, test_line
from runtime.wire import worker

router = APIRouter()


@router.get("/v1/routes")
async def list_routes(
    actor: WorkerKey, session: Session, query: Annotated[worker.RouteQuery, Query()]
) -> list[worker.RouteRow]:
    """The routes of a scope; for the fleet's key and a number, the route that number rings."""
    found = await routes.list_for_worker(session, actor, number=query.number, channel=query.channel)
    return [worker.RouteRow.model_validate(route, from_attributes=True) for route in found]


# The worker's, for a leg into a live call and for the leg a dial placed.
@router.get("/v1/agents/{slug}/outbound-trunk")
async def get_leg_trunk(
    slug: KnownAgent,
    actor: WorkerKey,
    vault: TheVault,
    sessions: TheSessions,
    session: Session,
    query: Annotated[worker.LegTrunkQuery, Query()],
) -> worker.LegTrunkResponse:
    """The leg's trunk inline, after the shape and the pace; a dial's own first leg passes."""
    dial = dial_guards.DialAsk(actor.scope, slug, query.to, query.shown, actor.asked_by, query.call, now())
    return worker.LegTrunkResponse(trunk=await outbound.leg_trunk(session, sessions, vault, dial))


# The worker's, before it sends the caller on: a REFER dials nothing of the box's, but the carrier
# dials it on the org's bill, so it passes the same guards as a warm transfer's leg.
@router.post("/v1/agents/{slug}/cold-transfer", status_code=204)
async def judge_cold_transfer(
    slug: KnownAgent,
    actor: WorkerKey,
    sessions: TheSessions,
    session: Session,
    query: Annotated[worker.ColdTransferQuery, Query()],
) -> None:
    """A cold transfer's leg, past the shape and the pace, its ledger row written."""
    dial = dial_guards.DialAsk(actor.scope, slug, query.to, None, actor.asked_by, query.call, now())
    await dial_guards.guard_second_leg(session, sessions, dial)


@router.get("/v1/agents/{slug}/rings-for")
async def get_ring_for(
    slug: str,
    _actor: FleetKey,
    held: TheAgentsHeld,
    servers: TheServers,
    names: TheSipNames,
    session: Session,
    org: Annotated[str, Query()],
    caller: Annotated[str, Query()],
) -> worker.RingHandoff:
    """Where a production ring from this phone goes: a developer's scope and fleet, or nowhere."""
    return await hand_over.ring_for(session, held, servers, names, org=org, slug=slug, caller=caller)


@router.get("/v1/test-line/rings-for")
async def get_ring_at_test_line(
    _actor: FleetKey,
    held: TheAgentsHeld,
    session: Session,
    number: Annotated[str, Query()],
    caller: Annotated[str, Query()],
) -> worker.RingAtTestLine:
    """Whose sandbox agent a ring at the box's test line is for: the org, the agent and the copy, or nobody's."""
    return await test_line.ring_at(session, held, number=number, caller=caller)
