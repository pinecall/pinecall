"""The flows' rules: an event kept until heard, a run started once, its journal written in order, what wakes it."""

import asyncio
from collections.abc import Mapping
from datetime import datetime, timedelta
from typing import Any, cast

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from pinecall_runtime.calls import service as calls
from pinecall_runtime.exceptions import Conflict, NotFound, PinecallError, ValidationError
from pinecall_runtime.flows.models import AppEvent, FlowRun, FlowStep
from pinecall_runtime.flows.repository import OVER, EventRepository, RunRepository, StepRepository
from pinecall_runtime.flows.schemas import StepRequest
from pinecall_runtime.kit.auth import Scope
from pinecall_runtime.kit.crypto import random_id
from pinecall_runtime.kit.text import JsonObject
from pinecall_runtime.kit.time import now, today_in

# A process that took work and died gives it back after this long; one that lives asks again sooner.
LEASED_FOR = timedelta(seconds=60)
# How often a process waiting for work is looked for again, within the wait it asked for.
LOOKED_EVERY_S = 1.0
# What one answer of the work endpoint hands out, and what the loops move in one pass.
MOST_AT_ONCE = 50
# The runs of one org that may wait for a clock, an event or a call at once.
MOST_PARKED = 10000
# The longest a run sleeps or waits.
LONGEST_WAIT = timedelta(days=90)
# The call ends a dial placed that reached nobody.
UNANSWERED = frozenset({"no_answer", "busy", "dial_failed"})

NO_SUCH_RUN = "no run {run} of the app {app}"
NOT_ITS_TURN = "run {run} is {status}: a step is written by the process that holds a ready run"
OUT_OF_ORDER = "run {run} has {have} steps and step {seq} was sent: the journal is written in order"
ANOTHER_STEP = (
    "step {seq} of run {run} was written as a {was}, and a {now} was sent: the flow's code changed under a run"
)
TOO_MANY_PARKED = f"this org has {MOST_PARKED} runs waiting already: let some end, or cancel them"
NOT_A_TIME = "{field} is a time, ISO 8601 with its zone: 2026-11-12T09:30:00-08:00"
TOO_FAR = f"a run sleeps or waits {LONGEST_WAIT.days} days at most"
A_CALL_TAKES = "a call step asks {agent, to}: the agent that calls, and the number in +E.164"


# ── events ──


async def send_event(session: AsyncSession, scope: Scope, app: str, name: str, data: JsonObject) -> AppEvent:
    """Keep an event for the app, and wake the runs that were waiting for one like it."""
    event = await EventRepository(session).add(AppEvent(org=scope.org, env=scope.env, app=app, name=name, data=data))
    steps = StepRepository(session)
    for run in await RunRepository(session).waiting_on(scope, app, name):
        if _matches(run.waits_match or {}, data):
            await _wake(steps, run, data)
    return event


async def hear_event(session: AsyncSession, scope: Scope, app: str, event_id: int) -> None:
    """The app's process handled the event: it is owed no more."""
    if not await EventRepository(session).mark_heard(scope, app, event_id, now()):
        raise NotFound(f"no event {event_id} owed to the app {app}")


# ── work ──


async def take_work(
    session: AsyncSession, scope: Scope, app: str
) -> tuple[list[AppEvent], list[tuple[FlowRun, list[FlowStep]]]]:
    """What the app's process is owed now, held for it: the events it has not heard, the runs ready to go on."""
    at = now()
    events = await EventRepository(session).lease_owed(scope, app, at, at + LEASED_FOR, MOST_AT_ONCE)
    ready = await RunRepository(session).lease_ready(scope, app, at, at + LEASED_FOR, MOST_AT_ONCE)
    journals: dict[str, list[FlowStep]] = {run.id: [] for run in ready}
    for step in await StepRepository(session).of_runs(list(journals)):
        journals[step.run].append(step)
    return list(events), [(run, journals[run.id]) for run in ready]


# A transaction of its own each look, so what one look took is another process's to see at once.
async def wait_for_work(
    sessions: async_sessionmaker[AsyncSession], scope: Scope, app: str, wait_s: float
) -> tuple[list[AppEvent], list[tuple[FlowRun, list[FlowStep]]]]:
    """What the app's process is owed, waited for up to `wait_s` seconds."""
    give_up = now() + timedelta(seconds=wait_s)
    while True:
        async with sessions() as session, session.begin():
            events, runs = await take_work(session, scope, app)
        if events or runs or now() >= give_up:
            return events, runs
        await asyncio.sleep(LOOKED_EVERY_S)


# ── runs ──


async def start_run(session: AsyncSession, scope: Scope, app: str, flow: str, key: str, given: JsonObject) -> FlowRun:
    """Start the flow with this input; the same key is the same run."""
    runs = RunRepository(session)
    started = await runs.by_key(scope, app, flow, key)
    if started is not None:
        return started
    run = FlowRun(id=random_id("run_", 8), org=scope.org, env=scope.env, app=app, flow=flow, key=key, input=given)
    return await runs.add(run)


async def run_of(session: AsyncSession, scope: Scope, app: str, run: str) -> tuple[FlowRun, list[FlowStep]]:
    """The run and its journal."""
    found = await _the_run(session, scope, app, run)
    return found, list(await StepRepository(session).of_run(found.id))


async def list_runs(
    session: AsyncSession, scope: Scope, app: str, flow: str | None, status: str | None
) -> list[FlowRun]:
    """The app's runs, newest first."""
    return list(await RunRepository(session).listed(scope, app, flow, status, 200))


async def end_run(session: AsyncSession, scope: Scope, app: str, run: str, status: str, error: str | None) -> FlowRun:
    """The flow returned or threw: the run is over."""
    found = await _the_run(session, scope, app, run, locked=True)
    if found.status not in OVER:
        found.status, found.error, found.leased_until, found.moved_at = status, error, None, now()
    return found


# A call the run placed goes on: it is a conversation somebody is having, and it ends as any other does.
async def cancel_run(session: AsyncSession, scope: Scope, app: str, run: str) -> FlowRun:
    """Stop a run where it stands; one that is over stays as it ended."""
    found = await _the_run(session, scope, app, run, locked=True)
    if found.status not in OVER:
        found.status, found.wake_at, found.waits_for, found.waits_match = "cancelled", None, None, None
        found.leased_until, found.moved_at = None, now()
    return found


# ── a step ──


async def write_step(
    session: AsyncSession, serving: calls.Serving, scope: Scope, app: str, run: str, asked_by: str, step: StepRequest
) -> tuple[FlowRun, FlowStep]:
    """Write the run's next step. One sent again is the one already written, so a retry writes nothing twice."""
    found = await _the_run(session, scope, app, run, locked=True)
    steps = StepRepository(session)
    written = await steps.at(found.id, step.seq)
    if written is not None:
        if written.kind != step.kind:
            raise Conflict(ANOTHER_STEP.format(seq=step.seq, run=run, was=written.kind, now=step.kind))
        return found, written
    if found.status != "ready":
        raise Conflict(NOT_ITS_TURN.format(run=run, status=found.status))
    have = len(await steps.of_run(found.id))
    if step.seq != have + 1:
        raise Conflict(OUT_OF_ORDER.format(run=run, have=have, seq=step.seq))
    row = FlowStep(run=found.id, seq=step.seq, org=found.org, kind=step.kind, asked=dict(step.asked))
    match step.kind:
        case "run":
            row.result = {"value": step.result}
        case "emit":
            await send_event(session, scope, app, _name_of(step.asked), _data_of(step.asked))
            row.result = {"value": None}
        case "sleep":
            await _park(session, found, "sleeping", wake_at=_time_of(step.asked, "until", required=True))
        case "wait":
            found.waits_for, found.waits_match = _name_of(step.asked, "event"), _data_of(step.asked, "match")
            await _park(session, found, "waiting", wake_at=_time_of(step.asked, "until", required=False))
        case "call":
            await _call(session, serving, scope, found, row, asked_by)
    found.moved_at = now()
    return found, await steps.add(row)


# A dial the guards refuse is the step's answer, never an error: the flow reads which guard and goes on.
async def _call(
    session: AsyncSession, serving: calls.Serving, scope: Scope, run: FlowRun, row: FlowStep, asked_by: str
) -> None:
    asked = row.asked
    agent, to = asked.get("agent"), asked.get("to")
    if not isinstance(agent, str) or not isinstance(to, str):
        raise ValidationError(A_CALL_TAKES)
    if serving.registry.serving(scope, agent, None) is None:
        row.result = {"value": {"answered": False, "refused": "no_app", "message": f"nobody holds {agent}"}}
        return
    placement = calls.Placement(
        scope=scope,
        agent=agent,
        to=to,
        shown=_text(asked, "from"),
        asked_by=asked_by,
        today=today_in(serving.handles.settings.timezone),
        at=now(),
        state=_data_of(asked, "state"),
        metadata=_data_of(asked, "metadata") | {"flow_run": run.id},
        greeting=_text(asked, "greeting"),
        instruction=_text(asked, "instruction"),
    )
    try:
        placed = await calls.place_call(session, serving, placement)
    except PinecallError as refused:
        row.result = {"value": {"answered": False, "refused": type(refused).__name__, "message": refused.message}}
        return
    run.call = placed.call
    await _park(session, run, "calling", wake_at=None)


async def _park(session: AsyncSession, run: FlowRun, status: str, *, wake_at: datetime | None) -> None:
    if await RunRepository(session).parked_count(run.org) >= MOST_PARKED:
        raise Conflict(TOO_MANY_PARKED)
    if wake_at is not None and wake_at - now() > LONGEST_WAIT:
        raise ValidationError(TOO_FAR)
    run.status, run.wake_at, run.leased_until = status, wake_at, None


# ── what wakes a run ──


async def wake_due(session: AsyncSession) -> int:
    """Wake the runs whose sleep is over and the waits that gave up; how many."""
    steps = StepRepository(session)
    due = await RunRepository(session).due(now(), MOST_AT_ONCE)
    for run in due:
        await _wake(steps, run, None)
    return len(due)


async def wake_called(session: AsyncSession) -> int:
    """Wake the runs whose call ended, with how it ended; how many."""
    steps = StepRepository(session)
    calling = [run for run in await RunRepository(session).calling(MOST_AT_ONCE) if run.call is not None]
    facts = await calls.facts_of_calls(session, [run.call for run in calling if run.call is not None])
    woken = 0
    for run in calling:
        ended = facts.get(run.call or "")
        if ended is None or ended.ended_at is None:
            continue
        reason = ended.end_reason or ""
        await _wake(steps, run, {"answered": reason not in UNANSWERED, "reason": reason, "call": run.call})
        woken += 1
    return woken


async def _wake(steps: StepRepository, run: FlowRun, value: Any) -> None:
    opened = await steps.open_of(run.id)
    if opened is not None:
        opened.result = {"value": value}
    run.status, run.wake_at, run.waits_for, run.waits_match = "ready", None, None, None
    run.leased_until, run.moved_at = None, now()


# ── reading what was asked ──


async def _the_run(session: AsyncSession, scope: Scope, app: str, run: str, *, locked: bool = False) -> FlowRun:
    found = await RunRepository(session).by_id(scope, app, run, locked=locked)
    if found is None:
        raise NotFound(NO_SUCH_RUN.format(run=run, app=app))
    return found


# Every key the wait named is in the event, with the same value.
def _matches(wanted: Mapping[str, Any], data: Mapping[str, Any]) -> bool:
    return all(data.get(key) == value for key, value in wanted.items())


def _name_of(asked: Mapping[str, Any], field: str = "name") -> str:
    name = asked.get(field)
    if not isinstance(name, str) or not name.strip():
        raise ValidationError(f"the step names its {field}")
    return name


def _data_of(asked: Mapping[str, Any], field: str = "data") -> dict[str, Any]:
    data: object = asked.get(field) or {}
    if not isinstance(data, dict):
        raise ValidationError(f"{field} is an object")
    return {str(key): value for key, value in cast(dict[object, Any], data).items()}


def _text(asked: Mapping[str, Any], field: str) -> str | None:
    value = asked.get(field)
    return value if isinstance(value, str) and value.strip() else None


def _time_of(asked: Mapping[str, Any], field: str, *, required: bool) -> datetime | None:
    given = asked.get(field)
    if given is None and not required:
        return None
    try:
        at = datetime.fromisoformat(str(given))
    except ValueError:
        raise ValidationError(NOT_A_TIME.format(field=field)) from None
    if at.tzinfo is None:
        raise ValidationError(NOT_A_TIME.format(field=field))
    return at
