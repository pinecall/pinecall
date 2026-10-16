"""What an org may dial, when and how often: shape, strangers, the callee's hours, the pace."""

from collections.abc import Awaitable, Callable, Sequence
from dataclasses import dataclass
from datetime import datetime
from zoneinfo import ZoneInfo

import phonenumbers
from phonenumbers import timezone
from sqlalchemy.ext.asyncio import AsyncSession

from pinecall_runtime.compliance import service as compliance
from pinecall_runtime.enums import ConsentKind, Env
from pinecall_runtime.exceptions import Forbidden, TooManyRequests, ValidationError
from pinecall_runtime.kit.auth import Scope
from pinecall_runtime.kit.text import parse_e164
from pinecall_runtime.telephony.models import Dial as DialRow
from pinecall_runtime.telephony.repository import DialPolicyRepository, DialRepository
from pinecall_runtime.telephony.schemas import Consent
from pinecall_runtime.telephony.service import consents
from pinecall_runtime.telephony.service.consents import Given
from pinecall_runtime.telephony.service.country_codes import (
    CALLING_CODES,
    NEVER_DIALLED,
    SHORTEST_NATIONAL,
)

# A call-back box, not a call centre: an operator raises them per org.
DIALS_A_MINUTE = 6
DIALS_A_DAY = 200
LONGEST_CALL_S = 600

# The guard that refused, written in the ledger and said in the sentence.
SHAPE = "shape"
STRANGER = "stranger"
TOO_FAST = "too_fast"
TOO_MANY = "too_many"
QUIET_HOURS = "quiet_hours"
TOO_OFTEN = "too_often"
DO_NOT_CALL = "do_not_call"
NO_CONSENT = "no_consent"

# The Telemarketing Sales Rule (16 CFR 310.4(c)): not before 8 a.m. or after 9 p.m. at the called
# person's location. It binds a call to the US; Canada's rules sit inside the same hours.
NORTH_AMERICA = "+1"
US_HOURS = (8, 21)
# Florida's "mini-TCPA" caps three calls in 24 hours to one person on one subject: the default for
# a +1 number, which the org may change. Elsewhere nothing, unless the org sets one.
US_PER_NUMBER_DAY = 3
NO_ZONE = "Etc/Unknown"
# How many of a number's zones a refusal names before it says "…".
ZONES_SAID = 3


# Whether a destination ever called or wrote to the org in the dial's env: the calls' to say, asked
# only when the org may not dial anywhere.
type Reached = Callable[[str], Awaitable[bool]]


@dataclass(frozen=True, slots=True)
class Guards:
    """The org's dial guards: what it may dial and how often."""

    dial_anywhere: bool = False
    per_minute: int = DIALS_A_MINUTE
    per_day: int = DIALS_A_DAY
    max_duration_s: int = LONGEST_CALL_S


@dataclass(frozen=True, slots=True)
class Dial:
    """One dial asked for: whose, to whom, shown as what, by whom, as which call, and when."""

    scope: Scope
    agent: str
    to: str
    shown: str | None
    asked_by: str
    call: str
    at: datetime
    # The number is a phone the person who asked verified as their own: testing, not calling out.
    own_phone: bool = False
    # The consent the call runs on, as the dial carried it; written down before anything rings.
    consent: Consent | None = None


@dataclass(frozen=True, slots=True)
class Rules:
    """What the called number's destination and the org's policy hold a dial to."""

    hours: tuple[int, int] | None
    per_number_day: int | None
    # Held to the do-not-call list at all: not in the sandbox, not the asker's own phone.
    listed: bool = False
    consent_required: bool = False


def destination_of(number: str) -> str:
    """The number a dial may reach, or ValidationError saying why not."""
    e164 = parse_e164(number)
    digits = e164.removeprefix("+")
    code = next((digits[:length] for length in (3, 2, 1) if digits[:length] in CALLING_CODES), None)
    if code is None:
        raise ValidationError(f"{e164} starts with no country calling code E.164 assigns")
    if code in NEVER_DIALLED:
        raise ValidationError(f"{e164} is +{code}, a satellite or global-service range this box never dials")
    national = digits[len(code) :]
    if len(national) < SHORTEST_NATIONAL:
        raise ValidationError(
            f"{e164} is shorter than a number anybody calls from: {len(national)} digits after +{code}"
        )
    return e164


async def guards_of(session: AsyncSession, org: str) -> Guards:
    """The org's guards; a column nobody set is the default."""
    row = await DialPolicyRepository(session).get(org)
    if row is None:
        return Guards()
    defaults = Guards()
    return Guards(
        dial_anywhere=defaults.dial_anywhere if row.dial_anywhere is None else row.dial_anywhere,
        per_minute=defaults.per_minute if row.per_minute is None else row.per_minute,
        per_day=defaults.per_day if row.per_day is None else row.per_day,
        max_duration_s=defaults.max_duration_s if row.max_duration_s is None else row.max_duration_s,
    )


async def put_guards(session: AsyncSession, org: str, guards: Guards) -> None:
    """Replace the org's guards whole."""
    for name in ("per_minute", "per_day", "max_duration_s"):
        if getattr(guards, name) < 0:
            raise ValidationError(f"{name} is never below zero")
    await DialPolicyRepository(session).put(
        org,
        dial_anywhere=guards.dial_anywhere,
        per_minute=guards.per_minute,
        per_day=guards.per_day,
        max_duration_s=guards.max_duration_s,
    )


async def guard_dial(session: AsyncSession, dial: Dial, reached: Reached) -> Guards:
    """Every guard on a call placed cold: shape, a stranger, hours, the pace; one ledger row."""
    destination = await _shaped(session, dial)
    guards = await guards_of(session, dial.scope.org)
    if not (guards.dial_anywhere or await reached(destination)):
        await _refused(session, dial, STRANGER)
        raise Forbidden(
            f"{destination} never called or wrote to this org in the {dial.scope.env}: a call back goes back "
            f"to somebody "
            f"({STRANGER}); an operator lifts it with dial_anywhere"
        )
    rules = await _rules_for(session, dial, destination)
    await _consented(session, dial, destination, rules)
    if rules.hours is not None:
        await _in_hours(session, dial, destination, rules.hours)
    await _paced(session, dial, guards, rules.per_number_day)
    return guards


def zones_of(number: str) -> tuple[str, ...]:
    """Every time zone the number could be in; empty when none is known."""
    zones = timezone.time_zones_for_number(phonenumbers.parse(number))
    return tuple(zone for zone in zones if zone != NO_ZONE)


def within(zones: tuple[str, ...], at: datetime, hours: tuple[int, int]) -> bool:
    """Whether it is inside the hours in every zone: a number in two zones is held to both."""
    start, end = hours
    return all(start <= at.astimezone(ZoneInfo(zone)).hour < end for zone in zones)


# A transfer target need not have called: the stranger fence stays off, the pace caps a loop.
async def guard_second_leg(session: AsyncSession, dial: Dial) -> None:
    """The shape and the pace on a leg dialled into a live call; the call's own first leg passes."""
    if await DialRepository(session).was_placed(dial.scope.org, dial.call, dial.to):
        return
    await _shaped(session, dial)
    await _paced(session, dial, await guards_of(session, dial.scope.org), None)


async def _shaped(session: AsyncSession, dial: Dial) -> str:
    try:
        return destination_of(dial.to)
    except ValidationError as malformed:
        await _refused(session, dial, SHAPE)
        raise ValidationError(f"{malformed} ({SHAPE})") from None


async def _refused(session: AsyncSession, dial: Dial, guard: str) -> None:
    await DialRepository(session).refused(
        dial.scope.org, dial.scope.env, dial.agent, dial.to.strip(), dial.shown, dial.asked_by, guard
    )


# The rules bind a call out to a person. The sandbox is where an org tries its agent, and a
# person's own verified phone is them testing: neither is held to a caller's hours or count.
async def _rules_for(session: AsyncSession, dial: Dial, destination: str) -> Rules:
    if dial.scope.env is Env.sandbox or dial.own_phone:
        return Rules(hours=None, per_number_day=None)
    kept = (await compliance.policy_of(session, dial.scope.org)).policy
    hours = kept.calling_hours
    window = None if hours is None else (hours.from_, hours.until)
    if destination.startswith(NORTH_AMERICA):
        floor, top = US_HOURS
        start, end = window if window is not None else US_HOURS
        return Rules(
            hours=(max(floor, start), min(top, end)),
            per_number_day=kept.per_number_day or US_PER_NUMBER_DAY,
            listed=True,
            consent_required=True,
        )
    return Rules(
        hours=window, per_number_day=kept.per_number_day, listed=True, consent_required=kept.consent_everywhere
    )


# An opt-out outranks the consent a dial carries: an app may not lift the list by sending one. A
# dial the list does not bind (the sandbox, a developer's own phone) rings past it, and writes no
# consent over it either.
async def _consented(session: AsyncSession, dial: Dial, destination: str, rules: Rules) -> None:
    current = await consents.standing_of(session, dial.scope, destination)
    if current == "opted_out" and not rules.listed:
        return
    if current == "opted_out":
        await _refused(session, dial, DO_NOT_CALL)
        raise Forbidden(
            f"{destination} asked not to be called: it is on this org's do-not-call list ({DO_NOT_CALL}); only a "
            "consent recorded at POST /v1/org/consents lifts it, never one sent with a dial"
        )
    if dial.consent is not None:
        given = Given(
            kind=ConsentKind(dial.consent.kind),
            source=dial.consent.source,
            given_by=dial.asked_by,
            text=dial.consent.text,
            evidence=dial.consent.evidence,
            call=dial.call,
        )
        await consents.give_consent(session, dial.scope, destination, given)
        return
    if rules.consent_required and current != "consented":
        await _refused(session, dial, NO_CONSENT)
        raise Forbidden(
            f"{destination} has no consent on file ({NO_CONSENT}): an AI-voice call needs the person's prior express "
            "consent. Send it as `consent` with the dial, or record it at POST /v1/org/consents"
        )


async def _in_hours(session: AsyncSession, dial: Dial, destination: str, hours: tuple[int, int]) -> None:
    zones = zones_of(destination)
    if not zones:
        await _refused(session, dial, QUIET_HOURS)
        raise Forbidden(
            f"{destination} has no zone this box can place it in, so its hours cannot be kept ({QUIET_HOURS})"
        )
    if not within(zones, dial.at, hours):
        await _refused(session, dial, QUIET_HOURS)
        window = f"{hours[0]}:00 to {hours[1]}:00"
        named = ", ".join(zones[:ZONES_SAID]) + ("…" if len(zones) > ZONES_SAID else "")
        raise Forbidden(
            f"{destination} is outside the hours it may be rung ({window}) in {named} ({QUIET_HOURS}); "
            "the sandbox and your own phone are not held to them"
        )


async def _paced(session: AsyncSession, dial: Dial, guards: Guards, per_number_day: int | None) -> None:
    guard, minute, day, number_day = await DialRepository(session).paced(
        dial.scope.org,
        dial.scope.env,
        dial.agent,
        dial.call,
        dial.to.strip(),
        dial.shown,
        dial.asked_by,
        per_minute=guards.per_minute,
        per_day=guards.per_day,
        per_number_day=per_number_day,
    )
    if guard is None:
        return
    if guard == TOO_FAST:
        sentence = f"the org dialled {minute} numbers in the last minute of its {guards.per_minute} ({TOO_FAST})"
    elif guard == TOO_OFTEN:
        sentence = f"{dial.to} was rung {number_day} times in the last day, of {per_number_day} ({TOO_OFTEN})"
    else:
        sentence = f"the org dialled {day} numbers today of its {guards.per_day} ({TOO_MANY})"
    raise TooManyRequests(sentence, retry_after_s=60)


async def dials_to(session: AsyncSession, number: str, since: datetime) -> Sequence[DialRow]:
    """Every dial to the number since then, placed or refused, oldest first, in every org."""
    return await DialRepository(session).to_number_since(number, since)
