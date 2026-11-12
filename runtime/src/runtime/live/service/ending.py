"""The steps of a call's end: what it taught memory, what it cost, how it was judged, and what follows its seal."""

import asyncio
import logging
import time
from collections.abc import Awaitable, Callable, Sequence
from dataclasses import dataclass

from runtime.accounts import service as accounts
from runtime.actor import Scope
from runtime.agents.declaration import Declaration
from runtime.alerts import service as alerts
from runtime.billing import service as billing
from runtime.calls import folds
from runtime.calls import service as calls
from runtime.calls.context import CallContext
from runtime.calls.log import Log
from runtime.exceptions import QuotaExceeded, ValidationError
from runtime.insights import service as insights
from runtime.judging import service as judging
from runtime.knowledge import service as knowledge
from runtime.live.parts import LiveParts
from runtime.live.served import Served
from runtime.providers import service as providers
from runtime.wire.base import Entry, WireModel
from runtime.wire.events import CallEnded, CallStarted, CallSummary, ErrorEvent, MemoryOps
from runtime.wire.feed import JudgeBroke
from runtime.wire.metrics import ModelUsage
from runtime.wire.parts import EndReason, MemoryOp
from runtime.wire.scores import CallScore
from runtime.wire.state import AgentTurn

logger = logging.getLogger(__name__)

JUDGING_OFF = "this org's calls are not judged at hang-up: POST /v1/evals/judge/{call} judges one"
A_RUN_JUDGES_IT = "an eval run opened this call, and its own judges scored it in the run's matrix"
NOBODY_CLAIMED = "no org ever claimed this call: there was nobody's panel to judge it"

# What a hang-up waits for the one model call that writes memory, unless the settings say.
REMEMBER_BUDGET_S = 8.0
# How long a seal waits for the app that holds the call to say its end hook ran (call.done), when the
# app says it will: what the hook logs lands only before `call.score`, which seals the log. An app
# that never answers costs the call this much and no more.
END_HOOK_WAITED_S = 3.0


# A call the platform ends for nobody (its worker went away, its dial was refused) has no session
# left to read: it is neither remembered nor judged, and its end is written here when its log holds none.
@dataclass(frozen=True, slots=True)
class End:
    """The end of a call nothing runs any more: why, when, how long it lasted, and why no judge read it."""

    reason: EndReason
    ended_at: float
    duration_s: float
    not_judged: str


@dataclass(frozen=True, slots=True)
class Sealing:
    """The end of a call as whoever ran it hands it over: what its models used and the last thing it said."""

    usage: tuple[ModelUsage, ...] = ()
    outcome: str = ""
    recording: str | None = None
    # The vendors that ran on the box's own key: the operator bills their usage.
    lent: tuple[str, ...] = ()
    # Given for a call nothing runs any more; None for one its session or its worker ended.
    end: End | None = None


# As much as is known of the call: one served here is known whole; one the reaper found has what its
# head and its opening kept, which for a call that never opened is nothing but its name.
@dataclass(frozen=True, slots=True)
class Closing:
    """A call at its end: its log, whose it is, what it ran on, and how it is ended."""

    call: str
    agent: str
    log: Log
    scope: Scope | None
    declaration: Declaration | None
    context: CallContext | None
    sealing: Sealing


def closing_of(served: Served, sealing: Sealing) -> Closing:
    """A call served here, at its end."""
    return Closing(served.call, served.agent, served.log, served.scope, served.declaration, served.context, sealing)


async def closing_of_unserved(live: LiveParts, call: str, agent: str, log: Log, sealing: Sealing) -> Closing:
    """A call nothing serves here, at its end: what its head and its opening kept of it."""
    async with live.sessions() as session:
        kept = await calls.find_head(session, call)
        opening = await calls.opening_of(session, call)
    return Closing(
        call,
        agent,
        log,
        None if kept is None else kept.scope,
        None if opening is None else opening.declaration,
        None if opening is None else opening.context,
        sealing,
    )


# ── before the seal: each step adds what it writes to the entries it was handed ──


async def write_end(closing: Closing, entries: list[Entry]) -> None:
    """call.ended for a call nothing runs any more, unless its log holds one."""
    end = closing.sealing.end
    if end is None or any(entry.type == "call.ended" for entry in entries):
        return
    ended = CallEnded(reason=end.reason, ended_by="platform", ended_at=end.ended_at, duration_s=end.duration_s)
    entries.append(await closing.log.append("call.ended", ended.dump()))


# Between call.ended and call.summary, on the org's keys as they are now. A refusal at the cap
# goes on the agent's log and the call's says an empty remember; a break is an entry, and it seals.
#
# No transaction is open while the model answers: `knowledge.remember` reads, asks and writes in
# short ones of its own. Until 2026-11 the seal's one session stayed open for the whole wait (a
# connection held up to eight seconds by each hang-up), and a timeout that fell inside a statement
# left that session unusable for the summary that followed.
async def remember(live: LiveParts, closing: Closing, entries: list[Entry]) -> knowledge.MemoryWrite | None:
    """What the call taught its contact's memory, written; None when the agent keeps nothing."""
    scope, context, declaration = closing.scope, closing.context, closing.declaration
    if scope is None or context is None or declaration is None or closing.sealing.end is not None:
        return None
    heard = knowledge.hear_call(closing.call, context.channel, context.remembered_as, declaration, entries, at=live.now)
    if heard is None:
        return None
    budget = live.settings.remember_budget_s or REMEMBER_BUDGET_S
    try:
        async with asyncio.timeout(budget):
            written = await knowledge.remember(
                live.sessions, live.vault, knowledge.box_embedder(live.vault, live.http), scope, declaration, heard
            )
    except QuotaExceeded as refused:
        async with live.sessions.begin() as own:
            await live.alerting.credits_exhausted(own, scope, closing.agent, refused)
        op = MemoryOp(op="remember", contact=heard.contact, facts=[], took_ms=0.0)
        entries.append(await closing.log.append("memory.ops", MemoryOps(ops=[op]).dump()))
        return knowledge.MemoryWrite(op=op, usage=None)
    except Exception as broke:
        # Memory is a courtesy to the next call; this one ends all the same.
        logger.warning("call %s was not written into memory", closing.call, exc_info=True)
        why = f"the call was not written into memory: {broke or type(broke).__name__}"
        failed = ErrorEvent(code="remember_failed", message=why, recoverable=True)
        entries.append(await closing.log.append("error", failed.dump()))
        return None
    # None on a box that embeds nothing: nothing is remembered there, and nothing says a call was.
    if written is not None:
        entries.append(await closing.log.append("memory.ops", MemoryOps(ops=[written.op]).dump()))
    return written


@dataclass(frozen=True, slots=True)
class Remembered:
    """What remembering a call now wrote: how many facts, and how long it took."""

    facts: int
    took_ms: float


# What a worker asks for a call it still runs (`POST /v1/calls/{call}/remember`).
async def remember_now(live: LiveParts, served: Served) -> Remembered:
    """Write what the call taught into its contact's memory now, as the seal would."""
    started = time.perf_counter()
    entries = await live.store.whole_of(served.call)
    written = await remember(live, closing_of(served, Sealing()), entries)
    facts = 0 if written is None else len(written.op.facts)
    return Remembered(facts, (time.perf_counter() - started) * 1000)


# The vendors lent are kept before the summary is written: whoever reads the summary off the metered
# feed reads them beside it.
async def price(live: LiveParts, closing: Closing, entries: list[Entry], written: knowledge.MemoryWrite | None) -> None:
    """call.summary: how the call ended, what it used, what that cost."""
    sealing = closing.sealing
    # The memory model's tokens are the call's: they are billed with it.
    usage = [*sealing.usage, *([written.usage] if written is not None and written.usage is not None else [])]
    over = _read(CallEnded, next((entry for entry in reversed(entries) if entry.type == "call.ended"), None))
    started = _read(CallStarted, next((entry for entry in entries if entry.type == "call.started"), None))
    duration = 0.0 if over is None else over.duration_s
    async with live.sessions.begin() as session:
        catalog = await providers.get_catalog(session)
        if sealing.lent:
            await calls.keep_lent(session, closing.call, sealing.lent)
    summary = CallSummary(
        reason="error" if over is None else over.reason,
        outcome=sealing.outcome,
        duration_s=duration,
        turns=sum(1 for turn in folds.reduce(entries).turns if isinstance(turn, AgentTurn)),
        usage=usage,
        cost=providers.cost_of(usage, catalog, legs=folds.phone_legs(entries), seconds=duration),
        recording=sealing.recording,
        simulated=judging.is_simulated(entries),
        run=None if started is None else started.run,
    )
    # Once per log: two gateways sealing one call (a lease lapsed under a stalled seal) price it once.
    summed = await closing.log.append_first("call.summary", summary.dump())
    if summed is not None:
        entries.append(summed)


# The seal never fails on a judge: a call that could not be judged says why and seals all the same
# (`judging.judge_call`). The panel is read in a transaction of its own and the model asked with no
# connection held: until 2026-11 the seal's session stayed open while every judge answered.
async def score(live: LiveParts, closing: Closing, entries: Sequence[Entry]) -> CallScore:
    """What the panel says of the call, or why no judge read it."""
    scope, context = closing.scope, closing.context
    if closing.sealing.end is not None:
        return _leave_unjudged(closing.sealing.end.not_judged)
    if context is not None and context.run is not None:
        return _leave_unjudged(A_RUN_JUDGES_IT)
    if scope is None:
        return _leave_unjudged(NOBODY_CLAIMED)
    async with live.sessions.begin() as session:
        judged_here = await accounts.is_judged(session, scope.org)
    if not judged_here:
        return _leave_unjudged(JUDGING_OFF.format(call=closing.call))
    judged = await judging.judge_call(live.sessions, live.vault, live.prompts, entries, closing.declaration, scope)
    if judged.out_of_evals:
        async with live.sessions.begin() as own:
            limit = (await billing.get_quotas(own, scope.org, scope.env)).evals or 0
            refused = QuotaExceeded(judging.OUT_OF_EVALS, quota="evals", used=limit, limit=limit)
            await live.alerting.credits_exhausted(own, scope, closing.agent, refused)
    return judged.score


# The app is sent call.ended when it is written and answers with its end hook: a line the hook logs, a
# state it writes, lands only if it is appended before call.score, which seals the log and from which
# a later append is refused. The wait is on the app's own word (call.done), after the work the seal
# has to do anyway, so an app that answers in the time the judges take costs the call nothing.
async def wait_for_the_app(live: LiveParts, served: Served) -> None:
    """Wait, a little, for the app that holds the call to say its end hook ran."""
    if not _says_done(live, served):
        return
    try:
        await asyncio.wait_for(served.hooked.wait(), END_HOOK_WAITED_S)
    except TimeoutError:
        logger.warning(
            "call %s: its app did not say its end hook ran within %g s; the log is sealed without it, "
            "and a line the hook logs later is refused",
            served.call,
            END_HOOK_WAITED_S,
        )


# ── after the seal ──

# The score sealed the log: the call is over whatever its bookkeeping does. Each step stands alone, in
# a transaction of its own, and what one raises is said and the next runs. Until 2026-11 they shared
# one transaction: an alert that raised took the day's drift and the case with it, and the seal asked
# again found the call gone.
type AfterSeal = Callable[[LiveParts, Closing, Sequence[Entry], CallScore], Awaitable[None]]


# The feed says which judge broke and on which call, nothing of why: the reason is the call's content.
async def announce_broken_judges(
    live: LiveParts, closing: Closing, _entries: Sequence[Entry], judged: CallScore
) -> None:
    """Say on the org's feed, once per judge, that it found the sealed call broken."""
    if closing.scope is None:
        return
    for judgment in judged.judges:
        if judgment.verdict == "broken":
            broke = JudgeBroke(call=closing.call, agent=closing.agent, judge=judgment.name)
            live.feeds.announce(closing.scope, "judge.broke", broke)


# Drift is a measure of the day, not of the call: a fold that breaks is logged and the call is over
# all the same, and `pinecall-runtime drift rebuild` counts it later. Every call that ends is folded
# here, one the reaper ended too: until 2026-11 a reaped call was counted by a rebuild alone, and a
# day's numbers moved when one ran.
async def fold_drift(live: LiveParts, closing: Closing, entries: Sequence[Entry], judged: CallScore) -> None:
    """Count the call's stages and verdicts into its day's drift."""
    async with live.sessions.begin() as session:
        await insights.fold_call(session, closing.call, entries, judged)


# A call a judge broke on waits in the org's inbox as a case.
async def keep_case(live: LiveParts, closing: Closing, entries: Sequence[Entry], judged: CallScore) -> None:
    """Keep a call one of its judges broke on as a pending case."""
    scope = closing.scope
    if judged.passed is not False or scope is None:
        return
    transcript = judging.transcript_of(entries, closing.declaration)
    async with live.sessions.begin() as session:
        kept = await calls.find_head(session, closing.call)
        version = None if kept is None else kept.versions.settings
        born = judging.Born(scope.org, scope.env, closing.agent, version)
        await judging.keep_at_hangup(session, transcript, entries, judged, born)


async def alert_vendor(live: LiveParts, closing: Closing, entries: Sequence[Entry], _judged: CallScore) -> None:
    """Tell the org of the vendor that failed the call, when one did."""
    failed = alerts.failure_of(closing.call, entries, lent=closing.sealing.lent)
    if failed is None or closing.scope is None:
        return
    async with live.sessions.begin() as session:
        await live.alerting.raise_alert(session, closing.scope, closing.agent, failed)


# What was found is kept whether or not it was said, so /metrics holds it up for as long as it is unusual.
async def watch_spend(live: LiveParts, closing: Closing, _entries: Sequence[Entry], _judged: CallScore) -> None:
    """Say once a day that the org spends more today than it usually does."""
    scope = closing.scope
    if scope is None:
        return
    async with live.sessions.begin() as session:
        found = await alerts.watch_spend(
            session, live.alerting, scope, closing.agent, spend=calls.sum_spend_by_day, at=live.store.clock()
        )
    live.spending.note(scope.org, found)


async def check_monitors(live: LiveParts, closing: Closing, _entries: Sequence[Entry], _judged: CallScore) -> None:
    """Say, once a day per monitor, that a number of the env crossed its line."""
    scope, declaration = closing.scope, closing.declaration
    if scope is None:
        return
    async with live.sessions.begin() as session:
        await alerts.check_monitors(
            session,
            live.alerting,
            scope,
            closing.agent,
            series=insights.series_window,
            at=live.store.clock(),
            wanted=None if declaration is None else declaration.monitors,
        )


# In this order: the fold comes before the monitors, which read the day it counts into.
AFTER_SEAL: tuple[tuple[str, AfterSeal], ...] = (
    ("telling the feed of the judges that broke", announce_broken_judges),
    ("folding the call into its day's drift", fold_drift),
    ("keeping the call as a case", keep_case),
    ("telling of the vendor that failed", alert_vendor),
    ("watching the org's spend", watch_spend),
    ("checking the env's monitors", check_monitors),
)


# ── private ──


def _leave_unjudged(why: str) -> CallScore:
    return CallScore(judges=[], judge_calls=0, not_judged=why)


# The socket the call is bound to, else the one that would take a new call of its agent, and whether it
# promised call.done: an SDK of before, or a console, is not waited for.
def _says_done(live: LiveParts, served: Served) -> bool:
    holders = live.holders
    bound = None if served.app is None else holders.find_on_socket(served.app, served.scope.env, served.agent)
    holder = bound or holders.find_serving(served.scope, served.agent)
    return holder is not None and holder.says_done


# The summary reads the call's first and last words: one this version cannot read counts as one
# the call never wrote, and the call seals all the same. The worker's endpoints refuse such an
# entry now; a log written before they did may hold one (2026-10-23: a call.started with no
# `caller` was taken, and its seal answered 500 for ever).
def _read[T: WireModel](model: type[T], entry: Entry | None) -> T | None:
    if entry is None:
        return None
    try:
        return model.parse(entry.data, entry.type)
    except ValidationError:
        logger.warning(
            "call %s: its %s at seq %d is unreadable, and the seal goes on without it",
            entry.call,
            entry.type,
            entry.seq,
        )
        return None
