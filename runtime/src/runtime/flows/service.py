"""The flows' rules: an event kept until heard, a run started once, its journal written in order, what wakes it."""

from collections.abc import Awaitable, Callable, Mapping, Sequence
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Any, Protocol

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from runtime.actor import Scope
from runtime.calls import service as calls
from runtime.enums import OVER, PARKED, RunStatus
from runtime.exceptions import Conflict, NotFound, PinecallError, ValidationError
from runtime.flows.models import AppEvent, FlowRun, FlowStep
from runtime.flows.repository import App, CalledRun, EventRepository, RunRepository, StepRepository
from runtime.kit.crypto import random_id
from runtime.kit.retry import until
from runtime.kit.text import Json, JsonObject
from runtime.kit.time import now
from runtime.live import service as live
from runtime.scoping import box_wide
from runtime.wire.flows import CallStep, EmitStep, RunStep, SleepStep, StepSent, WaitStep

# A process that took work and died gives it back after this long; one that lives asks again sooner.
LEASED_FOR = timedelta(seconds=60)
# How often a process waiting for work is looked for again, within the wait it asked for.
LOOKED_EVERY_S = 1.0
# What one answer of the work endpoint hands out, and what the loops move in one pass.
MOST_AT_ONCE = 50
# The runs a list answers.
MOST_LISTED = 200
# The runs of one org that may wait for a clock, an event or a call at once.
MOST_PARKED = 10000
# The longest a run sleeps or waits.
LONGEST_WAIT = timedelta(days=90)
# The longest a run waits for the call it placed to end. A call is held to its ceiling and the reaper ends
# one nothing runs any more, so a call that shows no end after this lost it: the run goes on, told so.
# Until 2026-11 a run waited for its call with no hour at all, and one whose call never ended waited for good.
LONGEST_CALL = timedelta(days=1)
# The call ends a dial placed that reached nobody.
UNANSWERED = frozenset({"no_answer", "busy", "dial_failed"})
# What a call step comes to when its call showed no end within LONGEST_CALL.
NEVER_ENDED = "never_ended"

NO_SUCH_RUN = "no run {run} of the app {app}"
NOT_ITS_TURN = "run {run} is {status}: a step is written by the process that holds a ready run"
OUT_OF_ORDER = "run {run} has {have} steps and step {seq} was sent: the journal is written in order"
ANOTHER_STEP = (
    "step {seq} of run {run} was written as a {was}, and a {now} was sent: the flow's code changed under a run"
)
TOO_MANY_PARKED = f"this org has {MOST_PARKED} runs waiting already: let some end, or cancel them"
TOO_FAR = f"a run sleeps or waits {LONGEST_WAIT.days} days at most"
NOT_A_MOVE = "run {run} is {was} and cannot be {to}: a run is ended by the process that holds it ready"

# The refusal that is flows' own: no app holds the agent, so nothing was asked of the dial.
NO_APP = "no_app"


@dataclass(frozen=True, slots=True)
class RunWithSteps:
    """A run and its journal, as its app's process is handed it."""

    run: FlowRun
    steps: Sequence[FlowStep]


@dataclass(frozen=True, slots=True)
class Work:
    """What an app's process is owed: the events it has not heard, and the runs ready to go on."""

    events: Sequence[AppEvent]
    runs: Sequence[RunWithSteps]


# ── what a call step asks of the live side ──


# Both are handed in by name (`flows/auth.py`). The dial takes `LiveParts`, which never leaves the live
# side: the gateway hands flows the dial already bound to it.
class Holders(Protocol):
    """Who takes an agent's calls now."""

    def find_serving(self, scope: Scope, slug: str) -> object | None:
        """The socket a call opened in this scope goes to, or None when no app holds the agent."""
        ...


type Dial = Callable[[AsyncSession, live.Placement], Awaitable[live.PlacedCall]]


# ── a run's moves ──


# A run is ready in its process's hands, parked while it waits (for the clock, an event or a call) and
# over once. Only the process that holds it ready parks it or ends it; whatever it waited for wakes it;
# it is cancelled from wherever it stands; nothing moves a run that is over. Until 2026-11 four
# functions each set the status and their own subset of the columns beside it, and no table said which
# moves there are: a process could end a run that slept, and its row read `done` with its hour still set.
MOVES: Mapping[RunStatus, frozenset[RunStatus]] = {
    RunStatus.ready: PARKED | OVER,
    **{parked: frozenset({RunStatus.ready, RunStatus.cancelled}) for parked in PARKED},
}


@dataclass(frozen=True, slots=True)
class Clock:
    """A run sleeps until a time."""

    until: datetime


@dataclass(frozen=True, slots=True)
class Event:
    """A run waits for an event of a name whose data has what `match` names, until it gives up."""

    name: str
    match: JsonObject
    until: datetime | None


@dataclass(frozen=True, slots=True)
class Call:
    """A run waits for the call it placed to end, and no longer than until a time."""

    id: str
    until: datetime


type Waiting = Clock | Event | Call


# `park`, `wake` and `finish` are the only code that sets a run's status, and each writes every column
# of what it waits for and of its lease. The status is a cache of the journal's open step: a run is
# parked exactly while its last step has no result.
def park(run: FlowRun, on: Waiting) -> None:
    """The run waits: for the clock, for an event, or for the call it placed."""
    match on:
        case Clock(until=hour):
            _move(run, RunStatus.sleeping, wake_at=hour)
        case Event(name=name, match=wanted, until=hour):
            _move(run, RunStatus.waiting, wake_at=hour, waits_for=name, waits_match=wanted)
        case Call(id=call, until=hour):
            _move(run, RunStatus.calling, wake_at=hour, call=call)


async def wake(steps: StepRepository, run: FlowRun, value: Json) -> None:
    """What the run waited for came: its open step is over with that, and the run is ready to go on."""
    opened = await steps.find_open(run.id)
    if opened is not None:
        opened.result = {"value": value}
    _move(run, RunStatus.ready)


def finish(run: FlowRun, outcome: RunStatus, error: str | None) -> None:
    """The run is over, as it ended; one that was over stays as it ended."""
    if run.status in OVER:
        return
    _move(run, outcome)
    run.error = error


def _move(
    run: FlowRun,
    to: RunStatus,
    *,
    wake_at: datetime | None = None,
    waits_for: str | None = None,
    waits_match: JsonObject | None = None,
    call: str | None = None,
) -> None:
    if to not in MOVES.get(run.status, frozenset()):
        raise Conflict(NOT_A_MOVE.format(run=run.id, was=run.status, to=to))
    run.status, run.leased_until, run.moved_at = to, None, now()
    run.wake_at, run.waits_for, run.waits_match, run.call = wake_at, waits_for, waits_match, call


# ── events ──


# An event that lands between a flow deciding to wait and its wait step being written wakes nobody (the
# run is still ready), and a wait never looks at the events already kept: it is for the next one. A flow
# that must not miss one waits first and has the event sent after.
async def send_event(session: AsyncSession, app: App, name: str, data: JsonObject) -> AppEvent:
    """Keep an event for the app, and wake the runs that were waiting for one like it."""
    scope = app.scope
    event = await EventRepository(session).add(
        AppEvent(org=scope.org, env=scope.env, app=app.name, name=name, data=data)
    )
    steps = StepRepository(session)
    for run in await RunRepository(session).list_waiting_on(app, name):
        if _matches(run.waits_match or {}, data):
            await wake(steps, run, data)
    return event


async def hear_event(session: AsyncSession, app: App, event_id: int) -> None:
    """The app's process handled the event: it is owed no more."""
    if not await EventRepository(session).mark_heard(app, event_id, now()):
        raise NotFound(f"no event {event_id} owed to the app {app.name}")


# ── work ──


# The bounded wait of one request, never a loop of the box's: a transaction of its own each look, so
# what one look took is another process's to see at once.
async def wait_for_work(sessions: async_sessionmaker[AsyncSession], app: App, wait_s: float) -> Work:
    """What the app's process is owed, waited for up to `wait_s` seconds."""

    async def look() -> Work | None:
        async with sessions() as session, session.begin():
            owed = await _lease_work(session, app)
        return owed if owed.events or owed.runs else None

    return await until(look, every_s=LOOKED_EVERY_S, within_s=wait_s) or Work(events=(), runs=())


async def _lease_work(session: AsyncSession, app: App) -> Work:
    at = now()
    events = await EventRepository(session).lease_owed(app, at, at + LEASED_FOR, MOST_AT_ONCE)
    ready = await RunRepository(session).lease_ready(app, at, at + LEASED_FOR, MOST_AT_ONCE)
    journals: dict[str, list[FlowStep]] = {run.id: [] for run in ready}
    for step in await StepRepository(session).list_of_runs(list(journals)):
        journals[step.run].append(step)
    return Work(events=events, runs=[RunWithSteps(run, journals[run.id]) for run in ready])


# ── runs ──


async def start_run(session: AsyncSession, app: App, flow: str, key: str, given: JsonObject) -> FlowRun:
    """Start the flow with this input; the same key is the same run."""
    return await RunRepository(session).create_once(app, random_id("run_", 8), flow, key, given, now())


async def get_run(session: AsyncSession, app: App, run: str) -> RunWithSteps:
    """The run and its journal."""
    found = await _get(session, app, run)
    return RunWithSteps(found, await StepRepository(session).list_of_run(found.id))


# The filter takes any word, as it always did: one no run is ever in lists nothing.
async def list_runs(session: AsyncSession, app: App, flow: str | None, status: str | None) -> Sequence[FlowRun]:
    """The app's runs, newest first; of one flow, or in one status, when named."""
    if status is not None and status not in frozenset(RunStatus):
        return []
    named = None if status is None else RunStatus(status)
    return await RunRepository(session).list_newest(app, flow, named, MOST_LISTED)


async def end_run(session: AsyncSession, app: App, run: str, outcome: RunStatus, error: str | None) -> FlowRun:
    """The flow returned or threw: the run is over."""
    found = await _get(session, app, run, locked=True)
    finish(found, outcome, error)
    return found


# A call the run placed goes on: it is a conversation somebody is having, and it ends as any other does.
async def cancel_run(session: AsyncSession, app: App, run: str) -> FlowRun:
    """Stop a run where it stands; one that is over stays as it ended."""
    found = await _get(session, app, run, locked=True)
    finish(found, RunStatus.cancelled, None)
    return found


# ── a step ──


# A step that is over as it is written leaves the run in its process's hands, held a while longer: until
# 2026-11 no step renewed the lease, and of two processes of one app the second was handed a run the
# first was still writing once a stretch of it passed LEASED_FOR, so the flow's code ran twice.
async def write_step(
    session: AsyncSession, holders: Holders, dial: Dial, app: App, run: str, asked_by: str, sent: StepSent
) -> FlowRun:
    """Write the run's next step. One sent again is the one already written, so a retry writes nothing twice."""
    found = await _get(session, app, run, locked=True)
    steps = StepRepository(session)
    written = await steps.find_at(found.id, sent.seq)
    if written is not None:
        if written.kind != sent.kind:
            raise Conflict(ANOTHER_STEP.format(seq=sent.seq, run=run, was=written.kind, now=sent.kind))
        return found
    if found.status != RunStatus.ready:
        raise Conflict(NOT_ITS_TURN.format(run=run, status=found.status))
    have = await steps.count_of_run(found.id)
    if sent.seq != have + 1:
        raise Conflict(OUT_OF_ORDER.format(run=run, have=have, seq=sent.seq))
    row = FlowStep(run=found.id, seq=sent.seq, org=found.org, kind=sent.kind, asked=dict(sent.asked))
    match sent.read():
        case RunStep(result=result):
            row.result = {"value": result}
        case EmitStep(name=name, data=data):
            await send_event(session, app, name, data)
            row.result = {"value": None}
        case SleepStep(until=hour):
            await _park(session, found, Clock(hour))
        case WaitStep(event=event, match=wanted, until=hour):
            await _park(session, found, Event(event, wanted, hour))
        case CallStep() as asked:
            refused = await _call(session, holders, dial, app, found, sent.seq, asked, asked_by)
            if refused is not None:
                row.result = {"value": refused}
    if found.status == RunStatus.ready:
        found.leased_until, found.moved_at = now() + LEASED_FOR, now()
    await steps.add(row)
    return found


# A dial the guards refuse is the step's answer, never an error: the flow reads which guard and goes on.
# Every refusal of flows' own comes before the dial: until 2026-11 the call was placed and then the
# ceiling of parked runs could refuse the step, so the request rolled back with a phone ringing, the
# journal held no step, and the flow's next stretch placed the call again. What is left of that is the
# moment between the dial and this transaction's commit: the call's id is the run's and the step's, and
# a dial asked again for them finds the call it placed and places none.
async def _call(
    session: AsyncSession,
    holders: Holders,
    dial: Dial,
    app: App,
    run: FlowRun,
    seq: int,
    asked: CallStep,
    asked_by: str,
) -> JsonObject | None:
    if holders.find_serving(app.scope, asked.agent) is None:
        return {"answered": False, "refused": NO_APP, "message": f"nobody holds {asked.agent}"}
    at = now()
    await _check_can_park(session, run, at + LONGEST_CALL)
    placement = live.Placement(
        scope=app.scope,
        agent=asked.agent,
        to=asked.to,
        shown=asked.from_,
        asked_by=asked_by,
        at=at,
        state=asked.state,
        metadata=asked.metadata | {"flow_run": run.id, "flow_step": seq},
        greeting=asked.greeting,
        instruction=asked.instruction,
        call=calls.call_id_of(f"{run.id}/{seq}"),
    )
    # `refused` is the name of the class that was raised, as it always was, and a flow branches on it: an
    # exception renamed changes what every flow reads. Which words it should be instead is not decided.
    try:
        placed = await dial(session, placement)
    except PinecallError as refused:
        return {"answered": False, "refused": type(refused).__name__, "message": refused.message}
    park(run, Call(placed.call, at + LONGEST_CALL))
    return None


async def _park(session: AsyncSession, run: FlowRun, on: Clock | Event) -> None:
    await _check_can_park(session, run, on.until)
    park(run, on)


async def _check_can_park(session: AsyncSession, run: FlowRun, hour: datetime | None) -> None:
    if await RunRepository(session).count_parked(run.org) >= MOST_PARKED:
        raise Conflict(TOO_MANY_PARKED)
    if hour is not None and hour - now() > LONGEST_WAIT:
        raise ValidationError(TOO_FAR)


# ── what wakes a run ──


# Both read every org's runs, as the box: each is flushed before the block ends, so what it wrote is
# written as the box too, whoever calls it.
async def wake_due(session: AsyncSession) -> int:
    """Wake the runs whose sleep is over and the waits that gave up; how many."""
    steps = StepRepository(session)
    with box_wide():
        due = await RunRepository(session).list_due(now(), MOST_AT_ONCE)
        for run in due:
            await wake(steps, run, None)
        await session.flush()
    return len(due)


async def wake_called(session: AsyncSession) -> int:
    """Wake the runs whose call ended, with how it ended, and those that waited for one long enough; how many."""
    steps = StepRepository(session)
    with box_wide():
        called = await RunRepository(session).list_called_and_over(now(), MOST_AT_ONCE)
        for one in called:
            await wake(steps, one.run, _end_of(one))
        await session.flush()
    return len(called)


def _end_of(called: CalledRun) -> JsonObject:
    if not called.ended:
        return {"answered": False, "reason": NEVER_ENDED, "call": called.run.call}
    reason = called.end_reason or ""
    return {"answered": reason not in UNANSWERED, "reason": reason, "call": called.run.call}


# ── reading ──


async def _get(session: AsyncSession, app: App, run: str, *, locked: bool = False) -> FlowRun:
    found = await RunRepository(session).find(app, run, locked=locked)
    if found is None:
        raise NotFound(NO_SUCH_RUN.format(run=run, app=app.name))
    return found


# Every key the wait named is in the event, with the same value.
def _matches(wanted: Mapping[str, Any], data: Mapping[str, Any]) -> bool:
    return all(data.get(key) == value for key, value in wanted.items())
