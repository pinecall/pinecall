"""An eval suite played through the app that holds the agent: each golden, each model, judged."""

import asyncio
import dataclasses
from collections.abc import Sequence
from dataclasses import dataclass, field
from typing import Never

from livekit.agents import llm
from sqlalchemy.ext.asyncio import AsyncSession

from pinecall_runtime.agents.declaration import AgentConfig, Model
from pinecall_runtime.agents.service import registry, settings
from pinecall_runtime.alerts import service as alerts
from pinecall_runtime.calls import service as calls
from pinecall_runtime.enums import Channel, Direction, Env
from pinecall_runtime.evals.schemas import OpenedCall, RunRow, RunSuiteRequest, ScoreRow
from pinecall_runtime.evals.service import playing, runs, simulations, spoken
from pinecall_runtime.exceptions import Forbidden, NotFound, QuotaExceeded, ServiceUnavailable, ValidationError
from pinecall_runtime.judging import service as judging
from pinecall_runtime.kit.auth import Scope
from pinecall_runtime.kit.time import today_in
from pinecall_runtime.providers import service as providers
from pinecall_runtime.wire.base import Entry
from pinecall_runtime.wire.dispatch import Dispatch
from pinecall_runtime.wire.feed import RunChanged
from pinecall_runtime.wire.goldens import Golden
from pinecall_runtime.wire.parts import ModelConfig

# Without the app the rest would run against a bare model: no view, no tools.
THE_APP_LEFT = (
    "the app detached after {done} of {total} goldens ({slug}): the socket holding the agent "
    "closed, and a conversation with no app behind it drives a model with no view and no tools"
)
# The worker builds a spoken session from the declaration: a column per model cannot hold.
ONE_MODEL_OUT_LOUD = (
    "--voice runs the model the agent declares: the worker builds the session, so a run cannot "
    "put a golden through a second model out loud. Drop --model, or drop --voice."
)
# A dispatch carries no date: the worker's clock is the real day's. A spoken caller says lines;
# the app's facts reach a written call alone. A turn's steps are asserted on livekit's test run,
# which only a written line has.
NO_EVENT_OUT_LOUD = (
    "golden {name} sends {event} at turn {number}, and a spoken call takes lines only: run this golden without --voice"
)
NO_STEPS_OUT_LOUD = (
    "golden {name} holds turn {number} to steps, and a spoken call is judged on its final expect "
    "only: run this golden without --voice"
)
NO_PINNED_DAY_OUT_LOUD = (
    "golden {name} pins today={day}, and a spoken call runs on the real day: the worker seeds its "
    "clock when the room opens. Run this golden without --voice."
)
# A golden's facts are answered to recall, which runs only on an agent that keeps memory.
NOT_REMEMBERED = (
    "golden {name} gives memory, and agent {slug} keeps none: its memory policy names nothing to "
    "keep (pinecall memory policy --remember '…')"
)
CASES_IN_THE_SANDBOX = (
    "cases are real callers' words played again: they run in the sandbox, against the app a "
    "developer holds there, never through production's, whose tools act for real"
)
CASES_WRITTEN = "cases are played as written calls: drop --voice, or play only goldens out loud"
# Every call of a run is a simulated caller and an agent the box may pay for: goldens and cases,
# each played once under every model.
CALLS_A_RUN = 200
TOO_MANY_CALLS = (
    "a run plays 200 calls at most, and {played} goldens and cases under {models} models are "
    "{total}: run fewer, or fewer models"
)
NO_SUCH_VERSION = "no version {version} of {slug} in the scope of the app that holds it"
# The worker writes call.summary and call.score after the caller leaves.
A_SEAL_MAY_TAKE_S = 25.0
NEVER_SEALED = "the spoken call {call} never sealed within {seconds:.0f}s: there is nothing to judge"


@dataclass(frozen=True)
class Suite:
    """One run as it goes: the socket it drives, what its calls run on, what it opened, judged."""

    body: RunSuiteRequest
    registration: registry.Registration
    setup: calls.TextSetup
    configured: providers.Catalog
    keys: providers.Keyring
    run: RunRow
    # The judge model the run's turns and goldens are asked on; None: the intents break saying so.
    judge: llm.LLM[Never] | None = None
    calls: list[OpenedCall] = field(default_factory=list[OpenedCall])
    cells: list[ScoreRow] = field(default_factory=list[ScoreRow])

    @property
    def now(self) -> RunRow:
        """The run as it stands: the calls opened and the matrix of the cells judged."""
        opened = self.run.model_copy(update={"calls": list(self.calls)})
        return runs.judged(opened, self.cells) if self.cells else opened


# One per agent at a time: a run drives the app that answers the agent's real calls.
async def run_suite(
    session_: AsyncSession,
    serving: calls.Serving,
    runner: runs.Runner,
    body: RunSuiteRequest,
    scope: Scope,
    registration: registry.Registration,
) -> RunRow:
    """Every golden under every model through the app that holds the agent, judged and stored."""
    if body.voice:
        _refuse_out_loud(body)
    if body.cases or body.dataset:
        body = await _with_cases(session_, body, scope)
    _refuse_past_the_ceiling(body)
    suite = await _suite_of(session_, serving, body, registration)
    _refuse_unremembered(body, suite.setup.config)
    where = registration.scope
    async with runner.alone(suite.run.id, body.agent):
        await _stored(serving, where, suite.run)
        why = await _judged_suite(session_, serving, suite, registration.scope)
        done = runs.finished(suite.now) if why is None else runs.stopped(suite.now, why)
        await _stored(serving, where, done)
    return done


# The run's calls run on what a real caller's would: the config tuned where the app holds it.
async def _suite_of(
    session_: AsyncSession, serving: calls.Serving, body: RunSuiteRequest, registration: registry.Registration
) -> Suite:
    where = registration.scope
    configured = await providers.get_catalog(session_)
    if body.version is not None:
        candidate = await settings.tuning_at(session_, where, body.agent, body.version)
        if candidate is None or candidate.holder != where.holder:
            raise NotFound(NO_SUCH_VERSION.format(version=body.version, slug=body.agent))
    picked = settings.Picked(version=body.version)
    config, versions = await settings.tuned_for_call(session_, registration.config, where, configured, picked)
    keys = await providers.keys_of(session_, serving.handles.vault, where)
    setup = calls.TextSetup(config, versions, providers.thinking_of(config, configured, keys))
    return Suite(body, registration, setup, configured, keys, runs.new_run(body.agent))


# Real callers' words are played in written calls in the sandbox: never through the live app,
# whose tools act for real, and never out loud.
async def _with_cases(session_: AsyncSession, body: RunSuiteRequest, scope: Scope) -> RunSuiteRequest:
    if scope.env is Env.production:
        raise Forbidden(CASES_IN_THE_SANDBOX)
    if body.voice:
        raise ValidationError(CASES_WRITTEN)
    played = await judging.pick_cases(session_, scope.org, body.agent, body.cases, every=body.dataset)
    return body.model_copy(update={"goldens": [*body.goldens, *played]})


async def _judged_suite(session_: AsyncSession, serving: calls.Serving, suite: Suite, scope: Scope) -> str | None:
    config = suite.setup.config
    judge = (await calls.judge_of(session_, serving, suite.configured, scope, config)).running
    model = None if judge is None else providers.llm_of(judge)
    try:
        async with asyncio.timeout(runs.A_RUN_MAY_TAKE_S):
            return await _every_golden(session_, serving, dataclasses.replace(suite, judge=model))
    except QuotaExceeded as refused:
        await alerts.credits_exhausted(session_, serving.handles, serving.logs, scope, suite.body.agent, refused)
        return str(refused)
    except TimeoutError:
        return runs.TOOK_TOO_LONG.format(minutes=runs.A_RUN_MAY_TAKE_S // 60)
    finally:
        if model is not None:
            await model.aclose()


# The row is written before each call (so it can be tailed) and after it is judged. A golden whose
# turn broke is not held to its final expect: the conversation it describes never happened.
async def _every_golden(session_: AsyncSession, serving: calls.Serving, suite: Suite) -> str | None:
    body, registration = suite.body, suite.registration
    total = len(body.goldens) * max(len(body.models), 1)
    models: list[ModelConfig | None] = list(body.models) or [None]
    for model in models:
        column = runs.column_of(model)
        setup = _column_setup(suite, model)
        for golden in body.goldens:
            if not _holds(serving, registration):
                return THE_APP_LEFT.format(done=len(suite.cells), total=total, slug=body.agent)
            opened = OpenedCall(golden=golden.name, model=column, call=calls.new_call_id())
            suite.calls.append(opened)
            await _stored(serving, registration.scope, suite.now)
            scores: list[judging.JudgeScore] = []
            judged = _turns_judged(golden, suite.judge, scores)
            played = await (
                _said_out_loud(session_, serving, suite, golden, opened)
                if body.voice
                else _written(session_, serving, suite, golden, opened, (setup, judged))
            )
            if played is None:
                return THE_APP_LEFT.format(done=len(suite.cells), total=total, slug=body.agent)
            entries = await serving.logs.store.whole(opened.call)
            case = judging.case_of(entries, setup.config)
            if played.broke_at is None:
                panel = await _judges_of(session_, suite, case, entries)
                final = judging.golden_judges(golden, case, panel)
                scores += await runs.score(final, case, suite.judge)
            requests = None if body.voice else played.requests
            suite.cells.append(runs.cell_of(opened, case, scores, requests))
            await _stored(serving, registration.scope, suite.now)
    return None


# Each line's steps asserted as its run ends, their scores kept in `scores`: True to play on.
def _turns_judged(golden: Golden, judge: llm.LLM[Never] | None, scores: list[judging.JudgeScore]) -> playing.TurnJudged:
    async def judged(number: int, played: judging.TurnRun) -> bool:
        steps = golden.turns[number - 1].then
        answered = await judging.turn_scores(steps, number, played, judge)
        scores.extend(answered)
        return all(score.passed for score in answered)

    return judged


# Every judge a real call of the agent may meet: a golden's grounded and `expect.judges` are
# asked from it.
async def _judges_of(
    session_: AsyncSession, suite: Suite, case: judging.Case, entries: Sequence[Entry]
) -> dict[str, judging.AskedJudge]:
    panel = await calls.panel_for(session_, suite.registration.scope.org, entries, suite.setup.config)
    return judging.asked_judges(case, panel)


# A column runs the agent's own model, or the one named, on the same tuned config and keys.
def _column_setup(suite: Suite, model: ModelConfig | None) -> calls.TextSetup:
    config = suite.setup.config
    if model is not None:
        declared = Model(provider=model.provider, model=model.model, temperature=model.temperature)
        config = dataclasses.replace(config, llm=declared)
    return dataclasses.replace(
        suite.setup, config=config, model=providers.thinking_of(config, suite.configured, suite.keys)
    )


async def _written(
    session_: AsyncSession,
    serving: calls.Serving,
    suite: Suite,
    golden: Golden,
    opened: OpenedCall,
    playing_: tuple[calls.TextSetup, playing.TurnJudged],
) -> playing.Played | None:
    setup, judged = playing_
    registration = suite.registration
    scope = registration.scope
    context = calls.CallContext(
        call=opened.call,
        channel=Channel.web,
        direction=Direction.inbound,
        caller=f"web_{calls.new_call_id()[5:17]}",
        route=calls.Route(org=scope.org, agent=registration.slug, channel=Channel.web, env=scope.env),
        today=golden.today or today_in(serving.handles.settings.timezone),
        pinned_day=golden.today,
        run=suite.run.id,
        holder=scope.holder or None,
        state=dict(golden.state),
    )
    running = await calls.open_text_as(
        session_, serving, registration, context, dataclasses.replace(setup, recalled=tuple(golden.memory))
    )
    heard = await serving.logs.writing(opened.call, registration.slug).follow()
    try:
        played = await playing.drive(running, golden, heard, judged, is_held=lambda: _holds(serving, registration))
    finally:
        heard.close()
    return played if played.held else None


async def _said_out_loud(
    session_: AsyncSession, serving: calls.Serving, suite: Suite, golden: Golden, opened: OpenedCall
) -> playing.Played | None:
    registration, body = suite.registration, suite.body
    scope = registration.scope
    # Refused, the run stops where it is, as for any quota (_judged_suite).
    await simulations.admit_simulation(session_, serving, scope, registration.slug)
    lines = [turn.say for turn in golden.turns if turn.say is not None]
    dispatch = Dispatch(
        agent=registration.slug,
        org=scope.org,
        env=scope.env,
        holder=scope.holder or None,
        caller=judging.A_SIMULATED_CALLER,
        app=registration.owner,
        run=suite.run.id,
        state=dict(golden.state),
    )

    async def scripted(turns_left: int) -> tuple[str, bool]:
        return (lines[len(lines) - turns_left], False) if turns_left <= len(lines) else ("", False)

    speech = providers.tts_of(await simulations.caller_voice(session_, serving, scope, registration.slug, None))
    line = spoken.Line(
        interferer_db=body.interferer_db, packet_loss=body.packet_loss, ambience=body.ambience or "television"
    )
    placed = spoken.SpokenLine("", "", opened.call, len(lines), line)
    try:
        await simulations.on_the_line(session_, serving, dispatch, speech, placed, scripted)
    finally:
        await speech.aclose()
    await _until_sealed(serving, opened.call)
    return playing.Played(held=True, requests=())


# The row is written and committed on its own, then the org's feed says it changed: a screen
# following the run reads it then, and `runs show` finds the run the lease names while it runs.
async def _stored(serving: calls.Serving, scope: Scope, run: RunRow) -> None:
    async with serving.handles.sessions.begin() as session_:
        await runs.put_run(session_, scope, run)
    changed = RunChanged(run=run.id, agent=run.agent, finished=run.finished_at is not None)
    serving.logs.announce(scope, "run.changed", changed)


async def _until_sealed(serving: calls.Serving, call: str) -> None:
    subscription = await serving.logs.reading(call).follow()
    try:
        async with asyncio.timeout(A_SEAL_MAY_TAKE_S):
            while not await serving.logs.store.is_sealed(call):
                await anext(subscription, None)
    except TimeoutError as never:
        raise ServiceUnavailable(NEVER_SEALED.format(call=call, seconds=A_SEAL_MAY_TAKE_S)) from never
    finally:
        subscription.close()


def _refuse_past_the_ceiling(body: RunSuiteRequest) -> None:
    models = max(len(body.models), 1)
    total = len(body.goldens) * models
    if total > CALLS_A_RUN:
        raise ValidationError(TOO_MANY_CALLS.format(played=len(body.goldens), models=models, total=total))


def _refuse_out_loud(body: RunSuiteRequest) -> None:
    if body.models:
        raise ValidationError(ONE_MODEL_OUT_LOUD)
    for golden in body.goldens:
        if golden.today is not None:
            raise ValidationError(NO_PINNED_DAY_OUT_LOUD.format(name=golden.name, day=golden.today))
        for number, turn in enumerate(golden.turns, 1):
            if turn.event is not None:
                raise ValidationError(NO_EVENT_OUT_LOUD.format(name=golden.name, event=turn.event.name, number=number))
            if turn.then:
                raise ValidationError(NO_STEPS_OUT_LOUD.format(name=golden.name, number=number))


def _refuse_unremembered(body: RunSuiteRequest, config: AgentConfig) -> None:
    if config.memory is not None:
        return
    for golden in body.goldens:
        if golden.memory:
            raise ValidationError(NOT_REMEMBERED.format(name=golden.name, slug=body.agent))


def _holds(serving: calls.Serving, registration: registry.Registration) -> bool:
    return serving.registry.on_socket(registration.owner, registration.scope.env, registration.slug) is not None
