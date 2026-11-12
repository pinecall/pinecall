"""What an org may dial, when and how often: shape, strangers, consent, the callee's hours, the pace, and the ledger."""

import logging
from collections.abc import Awaitable, Callable, Sequence
from dataclasses import dataclass
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

import phonenumbers
from phonenumbers import timezone
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from runtime.actor import Scope
from runtime.compliance.models import Dial
from runtime.compliance.repository.dials import DialPolicyRepository, DialRepository
from runtime.compliance.service import consents, policy
from runtime.compliance.service.country_codes import CALLING_CODES, NEVER_DIALLED, SHORTEST_NATIONAL
from runtime.compliance.service.policy import Hours
from runtime.enums import ConsentKind, Env
from runtime.exceptions import Forbidden, TooManyRequests, ValidationError
from runtime.kit.text import parse_e164
from runtime.kit.time import A_MINUTE_S, now
from runtime.scoping import box_wide

logger = logging.getLogger(__name__)

# A call-back box, not a call centre: an operator raises them per org.
DIALS_A_MINUTE = 6
DIALS_A_DAY = 200
LONGEST_CALL_S = 600
# The windows the pace counts in.
A_MINUTE = timedelta(minutes=1)
A_DAY = timedelta(days=1)

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
US_HOURS = Hours(8, 21)
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
class Consent:
    """The consent a dial carries: express or written, where it came from, the words, a proof."""

    kind: ConsentKind
    source: str
    text: str | None = None
    evidence: str | None = None


@dataclass(frozen=True, slots=True)
class DialAsk:
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

    hours: Hours | None
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


# ── the org's guards ──


# The one place a guard nobody named becomes its default: a column of the row, a field of the operator's body.
def read_guards(
    dial_anywhere: bool | None, per_minute: int | None, per_day: int | None, max_duration_s: int | None
) -> Guards:
    """The guards as they were named; one left out is the default."""
    defaults = Guards()
    return Guards(
        dial_anywhere=defaults.dial_anywhere if dial_anywhere is None else dial_anywhere,
        per_minute=defaults.per_minute if per_minute is None else per_minute,
        per_day=defaults.per_day if per_day is None else per_day,
        max_duration_s=defaults.max_duration_s if max_duration_s is None else max_duration_s,
    )


async def guards_of(session: AsyncSession, org: str) -> Guards:
    """The org's guards; a column nobody set is the default."""
    row = await DialPolicyRepository(session).find(org)
    if row is None:
        return Guards()
    return read_guards(row.dial_anywhere, row.per_minute, row.per_day, row.max_duration_s)


# The operator's, at its endpoint and at its terminal: an org able to lift its own dial guards would have none.
async def put_guards(session: AsyncSession, org: str, guards: Guards) -> Guards:
    """Replace the org's guards whole; the guards as they now stand."""
    paces = (("per_minute", guards.per_minute), ("per_day", guards.per_day), ("max_duration_s", guards.max_duration_s))
    for name, value in paces:
        if value < 0:
            raise ValidationError(f"{name} is never below zero")
    await DialPolicyRepository(session).put(
        org,
        {
            "dial_anywhere": guards.dial_anywhere,
            "per_minute": guards.per_minute,
            "per_day": guards.per_day,
            "max_duration_s": guards.max_duration_s,
        },
    )
    return guards


# ── a dial, guarded ──


# `session` is the request's: what a dial that passes writes (its ledger row) commits with the call it
# becomes. `sessions` makes the transaction of its own that a refusal's row, and the consent a dial
# carried, are written in: see `_refuse`.
async def guard_dial(
    session: AsyncSession, sessions: async_sessionmaker[AsyncSession], dial: DialAsk, reached: Reached
) -> Guards:
    """Every guard on a call placed cold: shape, a stranger, consent, hours, the pace; one ledger row."""
    destination = await _check_shape(sessions, dial)
    guards = await guards_of(session, dial.scope.org)
    if not (guards.dial_anywhere or await reached(destination)):
        await _refuse(sessions, dial, STRANGER)
        raise Forbidden(
            f"{destination} never called or wrote to this org in the {dial.scope.env}: a call back goes back "
            f"to somebody ({STRANGER}); an operator lifts it with dial_anywhere"
        )
    rules = await _rules_for(session, dial, destination)
    await _check_consent(session, sessions, dial, destination, rules)
    if rules.hours is not None:
        await _check_hours(sessions, dial, destination, rules.hours)
    await _pace(session, sessions, dial, guards, rules.per_number_day)
    return guards


def zones_of(number: str) -> tuple[str, ...]:
    """Every time zone the number could be in; empty when none is known."""
    zones = timezone.time_zones_for_number(phonenumbers.parse(number))
    return tuple(zone for zone in zones if zone != NO_ZONE)


def is_within(zones: tuple[str, ...], at: datetime, hours: Hours) -> bool:
    """Whether it is inside the hours in every zone: a number in two zones is held to both."""
    return all(hours.from_ <= at.astimezone(ZoneInfo(zone)).hour < hours.until for zone in zones)


# A transfer target need not have called: the stranger fence stays off, the pace caps a loop.
async def guard_second_leg(session: AsyncSession, sessions: async_sessionmaker[AsyncSession], dial: DialAsk) -> None:
    """The shape and the pace on a leg dialled into a live call; the call's own first leg passes."""
    if await DialRepository(session).is_placed(dial.scope.org, dial.call, dial.to):
        return
    await _check_shape(sessions, dial)
    await _pace(session, sessions, dial, await guards_of(session, dial.scope.org), None)


# ── the ledger ──


async def list_dials_to(session: AsyncSession, number: str, since: datetime) -> Sequence[Dial]:
    """Every dial to the number since then, placed or refused, oldest first, in every org."""
    with box_wide():
        return await DialRepository(session).list_to_number_since(number, since)


# The ledger outlives the call, the agent and the org it names; the calendar alone takes a row, and
# how old a row it takes is retention's to say.
async def forget_dials(session: AsyncSession, before: datetime) -> int:
    """Forget the dials placed or refused before the moment, in every org; how many."""
    with box_wide():
        return await DialRepository(session).delete_before(before)


# ── private ──


async def _check_shape(sessions: async_sessionmaker[AsyncSession], dial: DialAsk) -> str:
    try:
        return destination_of(dial.to)
    except ValidationError as malformed:
        await _refuse(sessions, dial, SHAPE)
        raise ValidationError(f"{malformed} ({SHAPE})") from None


# A refusal raises, and the request's transaction is rolled back with it. Until 2026-11 the refused
# row was written in that transaction: over HTTP no refused dial ever reached the ledger, and a
# carrier's traceback showed none. It is written in a transaction of its own, as an attempt is counted
# (`platform/service/attempts.py`). A row that cannot be written is said in the log and the refusal
# still reaches whoever asked: the ledger failing must not turn a refusal into an error.
async def _refuse(sessions: async_sessionmaker[AsyncSession], dial: DialAsk, guard: str) -> None:
    try:
        async with sessions.begin() as ledger:
            await DialRepository(ledger).add(_row_of(dial, refused=guard))
    except SQLAlchemyError:
        logger.warning(
            "the dial to %s that %s refused went unwritten; the refusal goes on", dial.to, guard, exc_info=True
        )


# A row a guard refused does not name the call: the call never was.
def _row_of(dial: DialAsk, *, refused: str | None, at: datetime | None = None) -> Dial:
    return Dial(
        org=dial.scope.org,
        env=dial.scope.env,
        agent=dial.agent,
        call=dial.call if refused is None else None,
        dialled=dial.to.strip(),
        shown=dial.shown,
        asked_by=dial.asked_by,
        refused=refused,
        at=at or now(),
    )


# The rules bind a call out to a person. The sandbox is where an org tries its agent, and a
# person's own verified phone is them testing: neither is held to a caller's hours or count.
async def _rules_for(session: AsyncSession, dial: DialAsk, destination: str) -> Rules:
    if dial.scope.env is Env.sandbox or dial.own_phone:
        return Rules(hours=None, per_number_day=None)
    kept = await policy.policy_of(session, dial.scope.org)
    window = kept.calling_hours
    if destination.startswith(NORTH_AMERICA):
        asked = US_HOURS if window is None else window
        return Rules(
            hours=Hours(max(US_HOURS.from_, asked.from_), min(US_HOURS.until, asked.until)),
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
async def _check_consent(
    session: AsyncSession, sessions: async_sessionmaker[AsyncSession], dial: DialAsk, destination: str, rules: Rules
) -> None:
    current = await consents.standing_of(session, dial.scope, destination)
    if current == "opted_out" and not rules.listed:
        return
    if current == "opted_out":
        await _refuse(sessions, dial, DO_NOT_CALL)
        raise Forbidden(
            f"{destination} asked not to be called: it is on this org's do-not-call list ({DO_NOT_CALL}); only a "
            "consent recorded at POST /v1/org/consents lifts it, never one sent with a dial"
        )
    if dial.consent is not None:
        await _keep_consent(sessions, dial, destination, dial.consent)
        return
    if rules.consent_required and current != "consented":
        await _refuse(sessions, dial, NO_CONSENT)
        raise Forbidden(
            f"{destination} has no consent on file ({NO_CONSENT}): an AI-voice call needs the person's prior express "
            "consent. Send it as `consent` with the dial, or record it at POST /v1/org/consents"
        )


# A fact about the number, true whatever becomes of the dial: written in a transaction of its own, or a
# dial refused after it (its hours, the pace) would take the consent it came with in its rollback.
async def _keep_consent(
    sessions: async_sessionmaker[AsyncSession], dial: DialAsk, destination: str, carried: Consent
) -> None:
    given = consents.Given(
        kind=carried.kind,
        source=carried.source,
        given_by=dial.asked_by,
        text=carried.text,
        evidence=carried.evidence,
        call=dial.call,
    )
    async with sessions.begin() as kept:
        await consents.give_consent(kept, dial.scope, destination, given)


async def _check_hours(
    sessions: async_sessionmaker[AsyncSession], dial: DialAsk, destination: str, hours: Hours
) -> None:
    zones = zones_of(destination)
    if not zones:
        await _refuse(sessions, dial, QUIET_HOURS)
        raise Forbidden(
            f"{destination} has no zone this box can place it in, so its hours cannot be kept ({QUIET_HOURS})"
        )
    if not is_within(zones, dial.at, hours):
        await _refuse(sessions, dial, QUIET_HOURS)
        window = f"{hours.from_}:00 to {hours.until}:00"
        named = ", ".join(zones[:ZONES_SAID]) + ("…" if len(zones) > ZONES_SAID else "")
        raise Forbidden(
            f"{destination} is outside the hours it may be rung ({window}) in {named} ({QUIET_HOURS}); "
            "the sandbox and your own phone are not held to them"
        )


# Under the org's lock, held by the request's transaction until it ends: the counts and the row are one
# decision, so two dials of one org cannot both take the last slot. The guards are tried in this order,
# and the first that refuses is the one written and said.
async def _pace(
    session: AsyncSession,
    sessions: async_sessionmaker[AsyncSession],
    dial: DialAsk,
    guards: Guards,
    per_number_day: int | None,
) -> None:
    repository = DialRepository(session)
    await repository.lock(dial.scope.org)
    at = now()
    counts = await repository.count_since(dial.scope.org, dial.to.strip(), minute=at - A_MINUTE, day=at - A_DAY)
    if counts.minute >= guards.per_minute:
        guard = TOO_FAST
        sentence = f"the org dialled {counts.minute} numbers in the last minute of its {guards.per_minute} ({TOO_FAST})"
    elif counts.day >= guards.per_day:
        guard = TOO_MANY
        sentence = f"the org dialled {counts.day} numbers today of its {guards.per_day} ({TOO_MANY})"
    elif per_number_day is not None and counts.to_number_placed >= per_number_day:
        guard = TOO_OFTEN
        sentence = (
            f"{dial.to} was rung {counts.to_number_placed} times in the last day, of {per_number_day} ({TOO_OFTEN})"
        )
    else:
        await repository.add(_row_of(dial, refused=None, at=at))
        return
    await _refuse(sessions, dial, guard)
    raise TooManyRequests(sentence, retry_after_s=A_MINUTE_S)
