"""A call placed out: the number shown, the account, the guards, the minutes, its log, its dispatch."""

from collections.abc import Mapping
from dataclasses import dataclass, field
from datetime import datetime

from livekit import api
from sqlalchemy.ext.asyncio import AsyncSession

from runtime.actor import Actor, Scope
from runtime.calls import service as calls
from runtime.calls.context import new_call_id
from runtime.compliance import service as compliance
from runtime.enums import Channel, Direction
from runtime.exceptions import Conflict, NotFound, UpstreamError, ValidationError
from runtime.fleet import service as fleet
from runtime.kit.text import Json
from runtime.kit.time import now
from runtime.live.holders import NoApp
from runtime.live.parts import LiveParts
from runtime.live.service import openings, seal, tokens
from runtime.live.service.ending import End, Sealing
from runtime.telephony import service as telephony
from runtime.wire.dispatch import Dialling, Dispatch
from runtime.wire.events import CallDialing
from runtime.wire.parts import Projection

# The key of a call's metadata that says what the call is for.
INSTRUCTION = "instruction"
# Who an UpstreamError of this module names.
THE_MEDIA_PLANE = "livekit"
NOTHING_RANG = "nothing rang"
NOT_JUDGED_UNPLACED = "the media plane refused the call before anything rang: there was nothing to judge"


@dataclass(frozen=True, slots=True)
class Placement:
    """A call asked for: scope, agent, the far end, the number shown, who asked, when."""

    scope: Scope
    agent: str
    to: str
    shown: str | None
    asked_by: str
    at: datetime
    # The far end is the asker's own verified phone: a test, held to no caller's hours.
    own_phone: bool = False
    consent: compliance.Consent | None = None
    # What the call opens with: the agent's state, and what its `call.started` carries.
    state: Mapping[str, Json] = field(default_factory=dict[str, Json])
    metadata: Mapping[str, Json] = field(default_factory=dict[str, Json])
    # This call's own opening words, and what it is for.
    greeting: str | None = None
    instruction: str | None = None
    # The call's id, when the asker names it so a dial asked again is placed once: a call it names
    # that was placed already is answered, never dialled a second time.
    call: str | None = None


@dataclass(frozen=True, slots=True)
class PlacedCall:
    """The call a dial became, before the far end has heard anything ring."""

    call: str
    to: str
    shown: str


@dataclass(frozen=True, slots=True)
class Dial:
    """What a key asks a dial with: the far end, the number shown, the consent, and what the call opens with."""

    to: str
    shown: str | None = None
    consent: compliance.Consent | None = None
    state: Mapping[str, Json] = field(default_factory=dict[str, Json])
    metadata: Mapping[str, Json] = field(default_factory=dict[str, Json])
    greeting: str | None = None
    instruction: str | None = None
    # What the log token handed back reads the call through.
    log: Projection = "tenant"


@dataclass(frozen=True, slots=True)
class Dialled:
    """A dial a key asked for, placed: the call it became, and a token that reads its log."""

    placed: PlacedCall
    log_token: str


# Asked with a key, for one of its agents: refused while no app serves the agent, and held to no
# caller's hours when the far end is the asker's own phone.
async def dial_as_agent(
    session: AsyncSession, live: LiveParts, signer: tokens.Signer, actor: Actor, slug: str, dial: Dial
) -> Dialled:
    """Place a call as the agent for whoever holds the key, after its guards; the call it became."""
    if live.holders.find_serving(actor.scope, slug) is None:
        raise Conflict(f"{NoApp(slug)}: a phone would ring with no app to serve it")
    who = actor.asked_by
    placement = Placement(
        scope=actor.scope,
        agent=slug,
        to=dial.to,
        shown=dial.shown,
        asked_by=who,
        at=now(),
        own_phone=dial.to in live.holders.phones_of(actor.env, who),
        consent=dial.consent,
        state=dial.state,
        metadata=dial.metadata,
        greeting=dial.greeting,
        instruction=dial.instruction,
    )
    placed = await place_call(session, live, placement)
    return Dialled(placed, tokens.sign_log_token(signer, placed.call, dial.log))


# The log opens on call.dialing before anything rings: the one record of who placed the call,
# which is what audits dial spend. A media plane that refuses the room ends the call at once, by the
# one end every call has: until 2026-11 it wrote an end of its own, with no summary and no score.
async def place_call(session: AsyncSession, live: LiveParts, placement: Placement) -> PlacedCall:
    """Place the call: number shown, account, guards, minutes, the log, then the dispatch."""
    scope = placement.scope
    shown = await _find_number_shown(session, placement)
    if placement.call is not None and await calls.find_head(session, placement.call) is not None:
        return PlacedCall(call=placement.call, to=placement.to, shown=shown)
    carrier = await telephony.get_carrier_for_number(session, live.vault, scope, shown)
    call = placement.call or new_call_id()
    dial = compliance.DialAsk(
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

    async def has_reached(destination: str) -> bool:
        return await calls.has_reached(session, scope.org, scope.env, destination)

    guards = await compliance.guard_dial(session, live.sessions, dial, has_reached)
    await openings.admit(session, live, scope, placement.agent)
    # Claimed on its own, before the log's first entry: the worker that opens the room's call finds
    # the head in the scope the dial named, and opens it there or not at all.
    async with live.sessions.begin() as own:
        await calls.claim_call(own, call, placement.agent, calls.Claim(scope))
    log = live.logs.writing(call, placement.agent)
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
        state=dict(placement.state),
        # The app reads what the call is for off its metadata, where a class finds it for its prompt.
        metadata=dict(placement.metadata) | ({INSTRUCTION: placement.instruction} if placement.instruction else {}),
        greeting=placement.greeting,
        instruction=placement.instruction,
    )
    try:
        await live.offering.offer(call, fleet.fleet_of(await fleet.get_fleets(session), scope.env), carried)
    except api.TwirpError as refused:
        end = End("dial_failed", ended_at=live.store.clock(), duration_s=0.0, not_judged=NOT_JUDGED_UNPLACED)
        await seal.end_unserved(live, call, placement.agent, Sealing(outcome=NOTHING_RANG, end=end))
        raise UpstreamError(f"the media plane refused the call: {refused.message}", vendor=THE_MEDIA_PLANE) from refused
    return PlacedCall(call=call, to=placement.to, shown=shown)


# The number named, when the agent answers at it; else the first the agent answers at.
async def _find_number_shown(session: AsyncSession, placement: Placement) -> str:
    scope = placement.scope
    routes = await telephony.list_phone_routes(session, scope, agent=placement.agent)
    numbers = [route.number for route in routes]
    if not numbers:
        raise NotFound(f"agent {placement.agent} answers at no phone number in the {scope.env}: a call back shows one")
    shown = placement.shown or numbers[0]
    if shown not in numbers:
        raise ValidationError(f"{shown} is not a number agent {placement.agent} answers at in the {scope.env}")
    return shown
