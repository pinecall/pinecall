"""The load lab: synthetic calls held against a gateway exactly as workers hold them, and measured."""

import asyncio
import json
import re
import time
from collections import Counter
from collections.abc import Callable, Sequence
from dataclasses import dataclass, field
from datetime import UTC, datetime
from functools import partial
from itertools import pairwise
from pathlib import Path

import httpx

from runtime.calls.context import CallContext, Route, dump_context, new_call_id
from runtime.enums import Channel, Direction, Env
from runtime.exceptions import UpstreamError, ValidationError
from runtime.jobs.service.call_client import A_SEAL_S, CallClient, open_call
from runtime.jobs.service.client import TIMEOUT_S, GatewayClient
from runtime.jobs.service.measures import nearest_rank
from runtime.kit.text import a_list
from runtime.session import service as session
from runtime.wire.base import BatchedEntry, Entry, WireModel
from runtime.wire.events import GATEWAY_WRITES, CallEnded, event_of
from runtime.wire.worker import CallOpened, OpenCallRequest

# What the replayer never sends: the gateway's own kinds, and a tool's round trip, which the
# gateway writes too (the one the worker writes itself, end_call's, is skipped with them).
GATEWAY_KINDS = GATEWAY_WRITES | {"tool.call", "tool.result"}
ENDED = "call.ended"
# The channel needs no number: the load names no carrier.
CHANNEL = Channel.web
CALLER = "load"
OUTCOME = "load"
# Between a refusal and the next call, so a gateway that refuses every open is not hammered.
REFUSED_PAUSE_S = 1.0
LAG_EVERY_S = 0.1
# Over this, the generator measures its own loop and not the gateway.
LAG_WARNING_MS = 50.0
# Past the run's end, what a call still writing and sealing is given before it is cut.
GRACE_S = 2 * A_SEAL_S
# A call's writer, once everything it queued was answered or the grace cut the call, stops this
# soon; nothing is left to send but what a cut call never will.
LET_GO_S = 0.1
UNREACHABLE = "unreachable"
A_CALL_IN_A_PATH = re.compile(r"call_[0-9a-f]+")

type Connect = Callable[[], GatewayClient]


@dataclass(frozen=True)
class Step:
    """One entry of the script: how long after the call opened it is written, and what it is."""

    at_s: float
    type: str
    event: WireModel
    ephemeral: bool


@dataclass(frozen=True)
class Script:
    """What one synthetic call writes: the worker's entries in order, then its call.ended."""

    steps: tuple[Step, ...]
    ending: Step


@dataclass(frozen=True)
class Plan:
    """A run: the org and agent the calls are opened for, the script, and the curve."""

    org: str
    agent: str
    script: Script
    calls: int
    ramp_s: float
    hold_s: float


@dataclass(frozen=True)
class Window:
    """When a run reaches its top and when it ends, on the monotonic clock."""

    top_at: float
    ends_at: float


@dataclass
class Tally:
    """What a run counted while it ran: calls, entries, latencies, refusals, logs, the loop."""

    opened: int = 0
    sealed: int = 0
    held: int = 0
    most_held: int = 0
    sent: int = 0
    durable: int = 0
    at_top: int = 0
    # From an entry queued to the log holding it: what the call waits, as a worker's does.
    append_ms: list[float] = field(default_factory=list[float])
    batches: list[int] = field(default_factory=list[int])
    seal_ms: list[float] = field(default_factory=list[float])
    refusals: Counter[str] = field(default_factory=Counter[str])
    verified: int = 0
    wrong: int = 0
    unread: Counter[str] = field(default_factory=Counter[str])
    lag_ms: list[float] = field(default_factory=list[float])


@dataclass(frozen=True)
class Run:
    """What every call of a run shares: how a slot connects, the plan, the tally and the window."""

    connect: Connect
    plan: Plan
    tally: Tally
    window: Window


def read_script(path: Path) -> Script:
    """A call's log as JSON, read as the script every synthetic call replays."""
    try:
        read: object = json.loads(path.read_bytes())
        entries = [Entry.model_validate(one) for one in (read if a_list(read) else [])]
    except (OSError, ValueError) as unread:
        raise ValidationError(f"--script {path}: {unread}") from None
    if not entries:
        raise ValidationError(f"--script {path}: the log holds no entry")
    return script_of(entries)


# ts may step back between two entries of a real log: a step is never earlier than the last.
def script_of(entries: Sequence[Entry]) -> Script:
    """The worker's entries of a call's log, timed and read as the wire's; call.ended if absent."""
    first = entries[0].ts
    steps: list[Step] = []
    ending: Step | None = None
    at_s = 0.0
    for entry in entries:
        at_s = max(at_s, entry.ts - first)
        if entry.type in GATEWAY_KINDS:
            continue
        step = Step(at_s, entry.type, event_of(entry), entry.ephemeral)
        if entry.type == ENDED:
            ending = step
        else:
            steps.append(step)
    if ending is None:
        over = CallEnded(reason="caller_hung_up", ended_by="caller", ended_at=first + at_s, duration_s=at_s)
        ending = Step(at_s, ENDED, over, ephemeral=False)
    return Script(tuple(steps), ending)


def starts_of(calls_: int, ramp_s: float) -> list[float]:
    """When each slot starts, in seconds from the run's start: evenly along the ramp."""
    return [ramp_s * slot / calls_ for slot in range(calls_)]


def percentile(samples: Sequence[float], share: float) -> float | None:
    """The nearest-rank percentile of the samples (share 0.99 for p99); None for no sample."""
    return nearest_rank(sorted(samples), share) if samples else None


def is_rising(sent: Sequence[Entry]) -> bool:
    """Whether the seqs the gateway gave a call's entries rise strictly, in the order sent."""
    return all(before.seq < after.seq for before, after in pairwise(sent))


# The kinds sent are compared: a duplicate from a retry is an entry of a sent kind at a new seq.
def log_holds(sent: Sequence[Entry], read: Sequence[Entry]) -> bool:
    """Whether a log read back holds every durable entry sent, once each, in order, and no other."""
    kinds = {entry.type for entry in sent}
    written = [(entry.seq, entry.type) for entry in sent if not entry.ephemeral]
    return [(entry.seq, entry.type) for entry in read if entry.type in kinds] == written


# A worker's job is a process with a client of its own, so a slot has one too: a pool shared by
# every call is searched whole on each request, and the generator would measure that search.
async def measure_load(url: str, key: str, plan: Plan) -> Tally:
    """Hold the plan's calls against the gateway at the URL, on the fleet's key, and count."""
    if plan.calls < 1:
        raise ValidationError(f"--calls {plan.calls}: at least one")
    headers = {"Authorization": f"Bearer {key}"}
    # Built once: every client would otherwise load the machine's certificates for itself.
    trusted = httpx.create_ssl_context()

    def connect() -> GatewayClient:
        return GatewayClient(httpx.AsyncClient(base_url=url, headers=headers, timeout=TIMEOUT_S, verify=trusted))

    return await run_load(connect, plan)


async def run_load(connect: Connect, plan: Plan) -> Tally:
    """Hold the plan's calls, each slot on a client of its own, and count what happened."""
    tally = Tally()
    began = time.monotonic()
    window = Window(top_at=began + plan.ramp_s, ends_at=began + plan.ramp_s + plan.hold_s)
    stopped = asyncio.Event()
    try:
        async with asyncio.timeout(plan.ramp_s + plan.hold_s + GRACE_S), asyncio.TaskGroup() as group:
            group.create_task(_lag(tally, stopped))
            run = Run(connect, plan, tally, window)
            slots = [group.create_task(_slot(run, start)) for start in starts_of(plan.calls, plan.ramp_s)]
            await asyncio.wait(slots)
            stopped.set()
    except TimeoutError:
        # Past the grace, a call still writing is cut; the report says how many were open.
        pass
    return tally


def report_of(tally: Tally, hold_s: float) -> list[str]:
    """What a run measured, a line each, as a person and a script both read it."""
    per_second = "-" if hold_s <= 0 else f"{tally.at_top / hold_s:.1f}"
    lag = percentile(tally.lag_ms, 0.99)
    lines = [
        f"calls opened: {tally.opened}",
        f"calls sealed: {tally.sealed}",
        f"calls open at the end: {tally.held}",
        f"most held at once: {tally.most_held}",
        f"entries sent: {tally.sent} ({tally.durable} durable)",
        f"entries a second at the top: {per_second}",
        f"append ms: {_percentiles(tally.append_ms, (0.5, 0.95, 0.99))}",
        f"entries per batch: {_percentiles([float(n) for n in tally.batches], (0.5, 0.99))}",
        f"seal ms: {_percentiles(tally.seal_ms, (0.5, 0.99))}",
        f"refusals: {_show_counts(tally.refusals)}",
        f"logs verified: {tally.verified}",
        f"logs found wrong: {tally.wrong}",
        f"logs unread: {sum(tally.unread.values())} (refused: {_show_counts(tally.unread)})",
        f"loop lag ms: p99 {_ms(lag)}",
    ]
    if lag is not None and lag > LAG_WARNING_MS:
        lines.append(
            f"warning: this generator's own loop lagged {lag:.1f} ms at p99, over "
            f"{LAG_WARNING_MS:.0f}: it measured itself, not the gateway; run fewer calls a process"
        )
    return lines


async def _lag(tally: Tally, stopped: asyncio.Event) -> None:
    while not stopped.is_set():
        before = time.monotonic()
        await asyncio.sleep(LAG_EVERY_S)
        tally.lag_ms.append((time.monotonic() - before - LAG_EVERY_S) * 1000)


# A refusal ends that call, never the slot: the slot opens a fresh call after a pause.
async def _slot(run: Run, start_s: float) -> None:
    await asyncio.sleep(start_s)
    client = run.connect()
    try:
        while time.monotonic() < run.window.ends_at:
            try:
                await _call(run, client)
            except UpstreamError as refused:
                run.tally.refusals[_status(refused)] += 1
                await asyncio.sleep(REFUSED_PAUSE_S)
    finally:
        await client.aclose()


async def _call(run: Run, client: GatewayClient) -> None:
    plan, tally = run.plan, run.tally
    context = CallContext(
        call=new_call_id(),
        channel=CHANNEL,
        direction=Direction.inbound,
        caller=CALLER,
        route=Route(org=plan.org, agent=plan.agent, channel=CHANNEL, env=Env.sandbox),
        today=datetime.now(UTC).date(),
    )
    opening = OpenCallRequest(agent=plan.agent, context=CallOpened.model_validate(dump_context(context)))
    link = await open_call(client, opening)
    tally.opened += 1
    tally.held += 1
    tally.most_held = max(tally.most_held, tally.held)
    try:
        sent = await _replay(run, link)
        started = time.monotonic()
        await link.seal([], OUTCOME)
        tally.seal_ms.append((time.monotonic() - started) * 1000)
        tally.sealed += 1
    finally:
        tally.held -= 1
        await link.aclose()
    await _verify(run, link, sent)


# At the script's own times from the open, queued on the worker's own writer, which sends what
# is queued as one batch while the last is out; a call the run's end overtakes skips to its
# call.ended. A refusal ends the call once what it queued has been answered.
async def _replay(run: Run, link: CallClient) -> list[Entry]:
    script, ends_at = run.plan.script, run.window.ends_at

    async def append_counted(entries: list[BatchedEntry], *, after: int) -> list[Entry]:
        run.tally.batches.append(len(entries))
        return await link.append_many(entries, after=after)

    writing = session.Writing(append_counted, link.call)
    writing.open()
    opened_at = time.monotonic()
    written: list[asyncio.Future[Entry]] = []
    try:
        for step in (*script.steps, script.ending):
            due = opened_at + step.at_s
            if due >= ends_at and step is not script.ending:
                continue
            await asyncio.sleep(max(min(due, ends_at) - time.monotonic(), 0.0))
            written.append(_queue(run, writing, step))
        answered = await asyncio.gather(*written, return_exceptions=True)
    finally:
        await writing.close(LET_GO_S)
    sent: list[Entry] = []
    for result in answered:
        if isinstance(result, BaseException):
            raise result
        sent.append(result)
    return sent


def _queue(run: Run, writing: session.Writing, step: Step) -> asyncio.Future[Entry]:
    queued_at = time.monotonic()
    written = writing.write(step.type, step.event, ephemeral=step.ephemeral)
    written.add_done_callback(partial(_count_landing, run, queued_at))
    return written


def _count_landing(run: Run, queued_at: float, written: asyncio.Future[Entry]) -> None:
    if written.cancelled() or written.exception() is not None:
        return
    tally, done = run.tally, time.monotonic()
    tally.append_ms.append((done - queued_at) * 1000)
    tally.sent += 1
    tally.durable += 0 if written.result().ephemeral else 1
    if run.window.top_at <= done <= run.window.ends_at:
        tally.at_top += 1


# Read through the log's own endpoint as a reader pages it; a key that may not read is counted apart.
async def _verify(run: Run, link: CallClient, sent: list[Entry]) -> None:
    tally = run.tally
    if not is_rising(sent):
        tally.wrong += 1
        return
    try:
        read = [entry async for entry in link.since(0)]
    except UpstreamError as refused:
        tally.unread[_status(refused)] += 1
        return
    if log_holds(sent, read):
        tally.verified += 1
    else:
        tally.wrong += 1


# By status and endpoint, the call's id taken out: which request was refused is what a run under
# gateways killed must say (`unreachable POST /v1/calls`), not a count of statuses alone.
def _status(refused: UpstreamError) -> str:
    status = UNREACHABLE if refused.answered is None else str(refused.answered)
    endpoint = A_CALL_IN_A_PATH.sub("{call}", str(refused).split(": ", 1)[0])
    return f"{status} {endpoint}"


def _percentiles(samples: Sequence[float], shares: Sequence[float]) -> str:
    return " ".join(f"p{round(share * 100)} {_ms(percentile(samples, share))}" for share in shares)


def _ms(value: float | None) -> str:
    return "-" if value is None else f"{value:.1f}"


def _show_counts(counts: Counter[str]) -> str:
    return " ".join(f"{name}={count}" for name, count in sorted(counts.items())) or "none"
