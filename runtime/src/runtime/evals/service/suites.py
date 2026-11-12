"""An eval suite played through the app that holds the agent: each golden, under each model, judged into the run."""

import asyncio
import logging
from collections.abc import Sequence
from contextlib import AsyncExitStack
from dataclasses import dataclass, field, replace

from livekit.agents import APIError
from sqlalchemy.ext.asyncio import AsyncSession

from runtime.accounts import service as accounts
from runtime.actor import Actor, Scope
from runtime.agents import service as agents
from runtime.calls.context import CallContext, Route, new_call_id
from runtime.enums import Channel, Direction, Env, Stage
from runtime.evals.parts import Harness
from runtime.evals.service import goldens, lines, runs, simulations, turns
from runtime.evals.service.callers import Spending, caller_voice
from runtime.evals.service.leg import Spoken
from runtime.evals.service.matrix import cell_of, failing, score_of
from runtime.evals.service.simulated_calls import keep_cost, keep_heard, opens_with_a_notice
from runtime.evals.service.spoken import SpokenLine
from runtime.evals.service.turn_checks import TurnRun, score_turn
from runtime.evals.service.written import JudgeTurn, Played, Unplayed, drive
from runtime.exceptions import (
    Forbidden,
    NotFound,
    QuotaExceeded,
    ServiceUnavailable,
    TooManyRequests,
    ValidationError,
)
from runtime.judging import service as judging
from runtime.kit.time import today_in
from runtime.live import service as live
from runtime.providers import service as providers
from runtime.providers.catalog import Catalog
from runtime.wire.base import Entry
from runtime.wire.declaration import ModelConfig
from runtime.wire.dispatch import Dispatch
from runtime.wire.feed import RunChanged
from runtime.wire.goldens import Golden
from runtime.wire.room import A_SIMULATED_CALLER
from runtime.wire.runs import JudgeScore, OpenedCall, Run, ScoreRow

logger = logging.getLogger(__name__)

# Without the app the rest would run against a bare model: no view, no tools.
THE_APP_LEFT = (
    "the app detached after {done} of {total} goldens ({slug}): the socket holding the agent "
    "closed, and a conversation with no app behind it drives a model with no view and no tools"
)
# A golden's facts are answered to recall, which runs only on an agent that keeps memory: the
# golden breaks on that alone, and the rest of the run plays.
NOT_REMEMBERED = (
    "golden {name} gives memory, and agent {slug} keeps none: its memory policy names nothing to "
    "keep (pinecall memory policy --remember '…')"
)
KEEPS_MEMORY = "the agent keeps memory, so the golden's facts can be recalled"
GATEWAY_STOPPED = "the gateway stopped mid-run"
RUN_BROKE = "the run broke on the gateway: {error}"
# Every call of a run is a simulated caller and an agent the box may pay for: goldens and cases,
# each played once under every model.
CALLS_A_RUN = 200
# The worker writes call.summary and call.score after the caller leaves.
A_SEAL_MAY_TAKE_S = 25.0


@dataclass(frozen=True, slots=True)
class Asked:
    """What a run is asked with: the agent, its goldens and cases, the models, a version, written or out loud."""

    agent: str
    goldens: tuple[Golden, ...] = ()
    # Cases of the org's dataset by name; a case held out is played only when named here.
    cases: tuple[str, ...] = ()
    # Every case of the agent's that is not held out: the nightly run.
    dataset: bool = False
    # A version of the agent's settings in the app's scope to run instead of the one standing.
    version: int | None = None
    # Empty: the model the agent declares. Each one plays every golden again.
    models: tuple[ModelConfig, ...] = ()
    # The app socket to drive; None, the newest that holds the agent.
    app: str | None = None
    # Each golden said out loud, through the env's fleet, under this noise when named.
    spoken: bool = False
    interferer_db: float | None = None
    packet_loss: float = 0.0
    ambience: str | None = None


# Until 2026-11 this was a frozen dataclass whose two lists were appended to, copied once to hand it
# its judge model and working only because the copy shared the lists.
@dataclass
class Suite:
    """One run as it goes: the socket it drives, what its calls run on, what it opened, what was judged."""

    asked: Asked
    registration: live.Registration
    setup: live.WrittenSetup
    catalog: Catalog
    keys: providers.Keyring
    run: Run
    # The judge model the run's turns and goldens are asked on; None: the intents break saying so.
    judge: providers.Answerer | None = None
    calls: list[OpenedCall] = field(default_factory=list[OpenedCall])
    cells: list[ScoreRow] = field(default_factory=list[ScoreRow])

    @property
    def now(self) -> Run:
        """The run as it stands: the calls opened and the matrix of the cells judged."""
        opened = self.run.model_copy(update={"calls": list(self.calls)})
        return runs.judge(opened, self.cells) if self.cells else opened


# One per agent at a time: a run drives the app that answers the agent's real calls. The request
# answers the run as written, `running`: its goldens play on a task of this gateway after, and the
# row is rewritten as each is judged, so the run is followed by its id and on the org's feed. Nothing
# of the request outlives the answer, and no session of it is taken: a run held one of the pool's
# connections for its fifteen minutes once, one per tenant testing.
async def start_suite(parts: Harness, actor: Actor, asked: Asked) -> Run:
    """The run refused, or stored and started: every golden under every model, played after this answers."""
    accounts.check_agent(actor, asked.agent)
    registration = parts.apps.get(actor.scope, asked.agent, asked.app)
    if asked.spoken:
        _refuse_out_loud(asked)
    async with parts.sessions.begin() as session_:
        if asked.cases or asked.dataset:
            asked = await _add_cases(session_, asked, actor.scope)
        _refuse_past_the_ceiling(asked)
        suite = await _suite_of(session_, parts, asked, registration)
    where = registration.scope
    await parts.runner.hold(suite.run.id, asked.agent)
    try:
        await _store(parts, where, suite.run)
    except Exception:
        # The row could not be written: the agent is let go, or the lease would be renewed for ever.
        await parts.runner.let_go(suite.run.id, asked.agent)
        raise
    parts.runner.play(suite.run.id, _play(parts, suite))
    return suite.run


# Whatever happens to the run, its row says how it ended and the agent is let go. A cancellation
# (the gateway stopping) is written down, then raised again: the task ends cancelled, as asked.
async def _play(parts: Harness, suite: Suite) -> None:
    where = suite.registration.scope
    cancelled = False
    try:
        why = await _judge_suite(parts, suite, where)
        done = runs.finish(suite.now) if why is None else runs.stop(suite.now, why)
    except asyncio.CancelledError:
        cancelled = True
        done = runs.stop(suite.now, GATEWAY_STOPPED)
    except Exception as broke:
        logger.exception("run %s of %s broke", suite.run.id, suite.asked.agent)
        done = runs.stop(suite.now, RUN_BROKE.format(error=_say_why(broke)))
    try:
        await _store(parts, where, done)
    finally:
        await parts.runner.let_go(suite.run.id, suite.asked.agent)
    if cancelled:
        raise asyncio.CancelledError


# The run's calls run on what a real caller's would: the declaration over the settings where the app holds it.
async def _suite_of(session_: AsyncSession, parts: Harness, asked: Asked, registration: live.Registration) -> Suite:
    where = registration.scope
    catalog = await providers.get_catalog(session_)
    if asked.version is not None:
        candidate = await agents.find_settings_version(session_, where, asked.agent, asked.version)
        if candidate is None or candidate.holder != where.holder:
            raise NotFound(f"no version {asked.version} of {asked.agent} in the scope of the app that holds it")
    of_its_class = (await agents.agent_of(session_, where, asked.agent)).whole
    picked = agents.Picked(version=asked.version)
    resolved = await agents.resolve_for_call(session_, of_its_class, where, catalog, picked)
    keys = await providers.keys_of(session_, parts.vault, where)
    model = providers.thinking_of(resolved.declaration, catalog, keys)
    setup = live.WrittenSetup(resolved.declaration, resolved.versions, model)
    return Suite(asked, registration, setup, catalog, keys, runs.new_run(asked.agent))


# Real callers' words are played in written calls in the sandbox: never through the live app,
# whose tools act for real, and never out loud.
async def _add_cases(session_: AsyncSession, asked: Asked, scope: Scope) -> Asked:
    if scope.env is Env.production:
        raise Forbidden(
            "cases are real callers' words played again: they run in the sandbox, against the app a developer "
            "holds there, never through production's, whose tools act for real"
        )
    if asked.spoken:
        raise ValidationError("cases are played as written calls: drop --voice, or play only goldens out loud")
    played = await judging.pick_cases(session_, scope.org, asked.agent, asked.cases, every=asked.dataset)
    return replace(asked, goldens=(*asked.goldens, *played))


# The judge model is opened once for the run, and closed with it. A run asks it and counts its
# requests in the matrix; it bills no eval for them (the page's defect 5, left for Bernardo).
async def _judge_suite(parts: Harness, suite: Suite, scope: Scope) -> str | None:
    declaration = suite.setup.declaration
    async with parts.sessions.begin() as session_:
        try:
            judge = await judging.judge_model_of(session_, parts.vault, suite.catalog, scope, declaration)
        except judging.Unjudged:
            judge = None
    async with AsyncExitStack() as stack:
        if judge is not None:
            suite.judge = await stack.enter_async_context(providers.open_answerer(judge.running))
        try:
            async with asyncio.timeout(runs.A_RUN_MAY_TAKE_S):
                return await _play_every_golden(parts, suite)
        except QuotaExceeded as refused:
            async with parts.sessions.begin() as session_:
                await parts.alerting.credits_exhausted(session_, scope, suite.asked.agent, refused)
            return str(refused)
        except TooManyRequests as busy:
            # The fleet had no slot for a spoken golden: the run stops saying so; no quota was reached.
            return str(busy)
        except TimeoutError:
            return runs.TOOK_TOO_LONG.format(minutes=runs.A_RUN_MAY_TAKE_S // 60)


# The row is written before each call (so it can be tailed) and after it is judged. A golden whose
# turn broke is not held to its final expect: the conversation it describes never happened.
async def _play_every_golden(parts: Harness, suite: Suite) -> str | None:
    asked, registration = suite.asked, suite.registration
    total = len(asked.goldens) * max(len(asked.models), 1)
    models: list[ModelConfig | None] = list(asked.models) or [None]
    for model in models:
        column = runs.column_of(model)
        setup = _column_setup(suite, model)
        for golden in asked.goldens:
            if not parts.apps.still_holds(registration):
                return THE_APP_LEFT.format(done=len(suite.cells), total=total, slug=asked.agent)
            if golden.memory and setup.declaration.memory is None:
                suite.cells.append(_break_for_no_memory(golden, column, asked.agent))
                continue
            opened = OpenedCall(golden=golden.name, model=column, call=new_call_id())
            suite.calls.append(opened)
            await _store(parts, registration.scope, suite.now)
            scores: list[JudgeScore] = []
            played = await (
                _say_out_loud(parts, suite, golden, opened)
                if asked.spoken
                else _write(parts, suite, golden, opened, setup, _judge_turns(golden, suite, scores))
            )
            if played is None:
                return THE_APP_LEFT.format(done=len(suite.cells), total=total, slug=asked.agent)
            if played.unplayed is not None:
                scores.append(_score_unplayed(played.unplayed))
            entries = await parts.store.whole_of(opened.call)
            transcript = judging.transcript_of(entries, setup.declaration)
            if played.broke_at is None:
                scores += await _score_final(parts, suite, golden, transcript, entries)
            requests = None if asked.spoken else played.requests
            suite.cells.append(cell_of(opened, transcript.summary, scores, requests))
            await _store(parts, registration.scope, suite.now)
    return None


# The turn's steps were never asked: nothing was played they could be checked on.
def _score_unplayed(why: Unplayed) -> JudgeScore:
    return score_of(why.metric, why.criteria, failing(why.reason))


# No call is opened for it: there is nothing to answer its facts with.
def _break_for_no_memory(golden: Golden, column: str, slug: str) -> ScoreRow:
    broke = score_of("memory", KEEPS_MEMORY, failing(NOT_REMEMBERED.format(name=golden.name, slug=slug)))
    return ScoreRow(model=column, golden=golden.name, scores=[broke], summary=None)


# Each line's steps asserted as its run ends, their scores kept in `scores`: True to play on.
def _judge_turns(golden: Golden, suite: Suite, scores: list[JudgeScore]) -> JudgeTurn:
    async def judge(number: int, played: TurnRun) -> bool:
        steps = golden.turns[number - 1].then
        answered = await score_turn(steps, number, played, suite.judge)
        scores.extend(answered)
        return all(score.passed for score in answered)

    return judge


# Every judge a real call of the agent may meet, on or off: a golden's grounded and `expect.judges`
# are asked from it, told what the panel tells a judge at hang-up.
async def _score_final(
    parts: Harness, suite: Suite, golden: Golden, transcript: judging.Transcript, entries: Sequence[Entry]
) -> list[JudgeScore]:
    org, declaration = suite.registration.scope.org, suite.setup.declaration
    async with parts.sessions.begin() as session_:
        roster = await judging.roster_of(session_, org, transcript.agent, declaration.judges)
        around = await judging.surroundings_of(session_, org, transcript.call, declaration)
        prompt = await judging.prompt_of(session_, parts.prompts, org, entries)
    checks = goldens.list_checks(golden, transcript, {judge.spec.name: judge for judge in roster})
    context = judging.context_of(transcript, around, prompt)
    return await goldens.score_golden(checks, transcript, context, suite.judge)


# A column runs the agent's own model, or the one named, on the same declaration and keys.
def _column_setup(suite: Suite, model: ModelConfig | None) -> live.WrittenSetup:
    declaration = suite.setup.declaration
    if model is not None:
        declaration = replace(declaration, llm=agents.read_model(model, Stage.llm))
    thinking = providers.thinking_of(declaration, suite.catalog, suite.keys)
    return replace(suite.setup, declaration=declaration, model=thinking)


async def _write(
    parts: Harness, suite: Suite, golden: Golden, opened: OpenedCall, setup: live.WrittenSetup, judge: JudgeTurn
) -> Played | None:
    registration = suite.registration
    scope = registration.scope
    context = CallContext(
        call=opened.call,
        channel=Channel.web,
        direction=Direction.inbound,
        caller=f"web_{new_call_id()[5:17]}",
        route=Route(org=scope.org, agent=registration.slug, channel=Channel.web, env=scope.env),
        today=golden.today or today_in(parts.settings.timezone),
        pinned_day=golden.today,
        run=suite.run.id,
        holder=scope.holder or None,
        state=dict(golden.state),
    )
    async with parts.sessions.begin() as session_:
        recalling = replace(setup, recalled=tuple(golden.memory))
        running = await parts.apps.open_written_as(session_, registration, context, recalling)
    heard = await parts.logs.writing(opened.call, registration.slug).follow()
    try:
        played = await drive(running, golden, heard, judge, is_held=lambda: parts.apps.still_holds(registration))
    finally:
        heard.close()
    return played if played.held else None


# A golden's lines said by a caller's leg, on the line every spoken simulation is on. Until 2026-11 this
# was a second copy of a spoken simulation's set-up, and it forgot two things the first did: what the
# voice that reads the golden cost, and how the agent heard it.
async def _say_out_loud(parts: Harness, suite: Suite, golden: Golden, opened: OpenedCall) -> Played | None:
    registration, asked = suite.registration, suite.asked
    scope = registration.scope
    async with parts.sessions.begin() as session_:
        # Refused, the run stops where it is, as for any quota (`_judge_suite`).
        await simulations.admit_simulation(session_, parts, scope, registration.slug, spoken=True)
        voice = await caller_voice(session_, parts.vault, scope, suite.setup.declaration, None)
        notice = await opens_with_a_notice(session_, scope, voice.language)
    script = [turn.say for turn in golden.turns if turn.say is not None]
    dispatch = Dispatch(
        agent=registration.slug,
        org=scope.org,
        env=scope.env,
        holder=scope.holder or None,
        caller=A_SIMULATED_CALLER,
        app=registration.owner,
        run=suite.run.id,
        state=dict(golden.state),
    )

    async def next_line(turns_left: int) -> tuple[str, bool]:
        return (script[len(script) - turns_left], False) if turns_left <= len(script) else ("", False)

    acts = judging.Behavior(
        interferer_db=asked.interferer_db, packet_loss=asked.packet_loss, ambience=asked.ambience or "television"
    )
    spoken = Spoken(opened.call, acts, language=voice.language, notice=notice)
    line = SpokenLine(parts, dispatch, voice, spoken, waits_for_slot=False)
    spending = Spending(suite.catalog)
    try:
        await lines.play(line, len(script), next_line, spending.count)
    finally:
        await keep_cost(parts, opened.call, spending)
        await keep_heard(parts, opened.call, line.list_said())
    await _wait_for_the_seal(parts, opened.call)
    return Played(held=True, requests=())


# The row is written and committed on its own, then the org's feed says it changed: a screen
# following the run reads it then, and the run the lease names is found while it runs.
async def _store(parts: Harness, scope: Scope, run: Run) -> None:
    async with parts.sessions.begin() as session_:
        await runs.put_run(session_, scope, run)
    changed = RunChanged(run=run.id, agent=run.agent, finished=run.finished_at is not None)
    parts.feeds.announce(scope, "run.changed", changed)


async def _wait_for_the_seal(parts: Harness, call: str) -> None:
    subscription = await parts.logs.reading(call).follow()
    try:
        async with asyncio.timeout(A_SEAL_MAY_TAKE_S):
            while not await parts.store.is_sealed(call):
                await turns.wait_for_entry_or_beat(subscription)
    except TimeoutError as never:
        raise ServiceUnavailable(
            f"the spoken call {call} never sealed within {A_SEAL_MAY_TAKE_S:.0f}s: there is nothing to judge"
        ) from never
    finally:
        subscription.close()


def _refuse_past_the_ceiling(asked: Asked) -> None:
    models = max(len(asked.models), 1)
    total = len(asked.goldens) * models
    if total > CALLS_A_RUN:
        raise ValidationError(
            f"a run plays 200 calls at most, and {len(asked.goldens)} goldens and cases under {models} models "
            f"are {total}: run fewer, or fewer models"
        )


def _refuse_out_loud(asked: Asked) -> None:
    if asked.models:
        # The worker builds a spoken session from the declaration: a column per model cannot hold.
        raise ValidationError(
            "--voice runs the model the agent declares: the worker builds the session, so a run cannot put a "
            "golden through a second model out loud. Drop --model, or drop --voice."
        )
    for golden in asked.goldens:
        if golden.today is not None:
            raise ValidationError(
                f"golden {golden.name} pins today={golden.today}, and a spoken call runs on the real day: the "
                "worker seeds its clock when the room opens. Run this golden without --voice."
            )
        for number, turn in enumerate(golden.turns, 1):
            if turn.event is not None:
                # A dispatch carries no date: the worker's clock is the real day's. A spoken caller says lines;
                # the app's facts reach a written call alone. A turn's steps are asserted on livekit's test run,
                # which only a written line has.
                raise ValidationError(
                    f"golden {golden.name} sends {turn.event.name} at turn {number}, and a spoken call takes "
                    "lines only: run this golden without --voice"
                )
            if turn.then:
                raise ValidationError(
                    f"golden {golden.name} holds turn {number} to steps, and a spoken call is judged on its "
                    "final expect only: run this golden without --voice"
                )


# A vendor's refusal is read in its words; anything else says what it is.
def _say_why(broke: Exception) -> str:
    return providers.sentence_of(broke) if isinstance(broke, APIError) else str(broke)
