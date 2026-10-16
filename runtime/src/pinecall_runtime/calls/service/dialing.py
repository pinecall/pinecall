"""A call placed out: the number shown, the account, the guards, the minutes, its log, its dispatch."""

import time
from dataclasses import dataclass
from datetime import date, datetime

from livekit import api
from sqlalchemy.ext.asyncio import AsyncSession

from pinecall_runtime.billing import service as billing
from pinecall_runtime.calls.context import new_call_id
from pinecall_runtime.calls.repository.heads import Claim
from pinecall_runtime.calls.service import lists
from pinecall_runtime.calls.service.serving import Serving
from pinecall_runtime.enums import Channel, Direction
from pinecall_runtime.exceptions import NotFound, UpstreamError, ValidationError
from pinecall_runtime.fleet import service as fleet
from pinecall_runtime.kit.auth import Scope
from pinecall_runtime.telephony import service as telephony
from pinecall_runtime.wire.dispatch import Dialling, Dispatch
from pinecall_runtime.wire.events import CallDialing, CallEnded


@dataclass(frozen=True, slots=True)
class Placement:
    """A call asked for: scope, agent, the far end, the number shown, who asked, when."""

    scope: Scope
    agent: str
    to: str
    shown: str | None
    asked_by: str
    today: date
    at: datetime
    # The far end is the asker's own verified phone: a test, held to no caller's hours.
    own_phone: bool = False
    consent: telephony.Consent | None = None


@dataclass(frozen=True, slots=True)
class PlacedCall:
    """The call a dial became, before the far end has heard anything ring."""

    call: str
    to: str
    shown: str


# The log opens on call.dialing before anything rings: the one record of who placed the call,
# which is what audits dial spend. A media plane that refuses the room ends the call at once.
async def place_call(session: AsyncSession, serving: Serving, placement: Placement) -> PlacedCall:
    """Place the call: number shown, account, guards, minutes, the log, then the dispatch."""
    scope = placement.scope
    shown = await _number_shown(session, placement)
    carrier = await telephony.carrier_for_number(session, serving.handles, scope, shown)
    call = new_call_id()
    dial = telephony.Dial(
        scope,
        placement.agent,
        placement.to,
        shown,
        placement.asked_by,
        call,
        placement.at,
        own_phone=placement.own_phone,
        consent=placement.consent,
    )

    async def reached(destination: str) -> bool:
        return await lists.ever_reached(session, scope.org, scope.env, destination)

    guards = await telephony.guard_dial(session, dial, reached)
    running = serving.live.running(scope.org, scope.env)
    await billing.admit_call(session, scope.org, scope.env, running=running, at=placement.at.timestamp())
    await serving.logs.store.claim(call, placement.agent, scope.org, Claim(scope))
    log = serving.logs.writing(call, placement.agent)
    dialing = CallDialing.parse(
        {
            "channel": Channel.phone,
            "from": shown,
            "to": placement.to,
            "run": None,
            "caller": None,
            "asked_by": placement.asked_by,
        },
        "call.dialing",
    )
    await log.append("call.dialing", dialing.dump())
    carried = Dispatch(
        agent=placement.agent,
        org=scope.org,
        env=scope.env,
        holder=scope.holder or None,
        direction=Direction.outbound,
        caller=placement.to,
        dial=Dialling(trunk=carrier.id, to=placement.to, shown=shown, max_duration_s=guards.max_duration_s),
    )
    try:
        await serving.offering.offer(call, fleet.fleet_of(await fleet.fleets(session), scope.env), carried)
    except api.TwirpError as refused:
        ended = CallEnded(reason="dial_failed", ended_by="platform", ended_at=time.time(), duration_s=0.0)
        await log.append("call.ended", ended.dump())
        await log.seal()
        serving.logs.forget(call)
        raise UpstreamError(f"the media plane refused the call: {refused.message}") from refused
    return PlacedCall(call=call, to=placement.to, shown=shown)


# The number named, when the agent answers at it; else the first the agent answers at.
async def _number_shown(session: AsyncSession, placement: Placement) -> str:
    scope = placement.scope
    numbers = [
        route.number for route in await telephony.phone_routes_of(session, scope) if route.agent == placement.agent
    ]
    if not numbers:
        raise NotFound(f"agent {placement.agent} answers at no phone number in the {scope.env}: a call back shows one")
    shown = placement.shown or numbers[0]
    if shown not in numbers:
        raise ValidationError(f"{shown} is not a number agent {placement.agent} answers at in the {scope.env}")
    return shown
