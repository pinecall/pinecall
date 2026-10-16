"""An eval run: one agent, every golden under every model, judged into a matrix as it goes."""

import asyncio
from collections.abc import Coroutine, Iterable, Sequence
from typing import Never

from livekit.agents import llm
from livekit.agents.evals import EvaluationResult
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from pinecall_runtime.evals.repository import RunLeaseRepository, RunRepository
from pinecall_runtime.evals.schemas import Failure, OpenedCall, RunRow, ScoreMatrix, ScoreRow
from pinecall_runtime.exceptions import Conflict, NotFound
from pinecall_runtime.judging import service as judging
from pinecall_runtime.kit.auth import Scope
from pinecall_runtime.kit.crypto import random_id
from pinecall_runtime.kit.text import JsonObject
from pinecall_runtime.kit.time import epoch
from pinecall_runtime.wire.parts import ModelConfig

# A run is coroutines of the gateway, so its deadline is a timeout; its finished calls stay.
A_RUN_MAY_TAKE_S = 15 * 60
# The column of the agent's own model, when the run named none.
DECLARED = "declared"
# A run holds its agent for so long and renews it at a third of that: a gateway that died
# mid-run leaves a lease another run takes once it ran out.
LEASED_S = 60.0

ALREADY_RUNNING = (
    "eval run {id} is running on agent {agent}: a run drives the app that also answers that "
    "agent's real calls, so there is one per agent at a time"
)
TOOK_TOO_LONG = "the run passed its {minutes} minute deadline and was stopped"
NO_SUCH_RUN = "no eval run {id} in this key's org and env"


# The run itself is coroutines of this process, gone with it; the lease is in Postgres, so a run on
# one gateway holds the agent on every one, and a gateway that died mid-run leaves a lease another
# run takes once it ran out.
class Runner:
    """The runs this gateway plays, each on a task of its own, and the agent each one holds."""

    def __init__(self, sessions: async_sessionmaker[AsyncSession]) -> None:
        """No agent under a run of this process, nothing playing."""
        self.sessions = sessions
        self.running: dict[str, str] = {}
        self.renewing: dict[str, asyncio.Task[None]] = {}
        self.playing: dict[str, asyncio.Task[None]] = {}

    # Refused, not queued: the refusal names the run to follow instead.
    async def hold(self, run: str, agent: str) -> None:
        """Hold the agent for this run, renewed while it plays; Conflict while another run holds it."""
        if not await self._leased(run, agent):
            async with self.sessions.begin() as session:
                holding = await RunLeaseRepository(session).holder(agent)
            raise Conflict(ALREADY_RUNNING.format(id=holding or "another run", agent=agent))
        self.running[agent] = run
        self.renewing[run] = asyncio.create_task(self._renewed(run, agent))

    async def let_go(self, run: str, agent: str) -> None:
        """Let the agent go: the lease released, its renewal stopped."""
        renewing = self.renewing.pop(run, None)
        if renewing is not None:
            renewing.cancel()
            await asyncio.gather(renewing, return_exceptions=True)
        if self.running.get(agent) == run:
            del self.running[agent]
        async with self.sessions.begin() as session:
            await RunLeaseRepository(session).release(agent, run)

    # The request's context goes with the task, so the run plays as the org that asked for it.
    def play(self, run: str, played: Coroutine[object, object, None]) -> None:
        """Play the run on a task of its own, kept until it ends."""
        task = asyncio.create_task(played)
        self.playing[run] = task
        task.add_done_callback(lambda _done: self.playing.pop(run, None))

    async def stop(self) -> None:
        """Stop every run still playing: each one writes itself stopped as its task is cancelled."""
        playing = list(self.playing.values())
        for task in playing:
            task.cancel()
        await asyncio.gather(*playing, return_exceptions=True)

    async def _leased(self, run: str, agent: str) -> bool:
        async with self.sessions.begin() as session:
            return await RunLeaseRepository(session).take(agent, run, LEASED_S)

    async def _renewed(self, run: str, agent: str) -> None:
        while True:
            await asyncio.sleep(LEASED_S / 3)
            await self._leased(run, agent)


def new_run(agent: str) -> RunRow:
    """A run of the agent that starts now and opened nothing yet."""
    return RunRow(
        id=random_id("run_", 6),
        agent=agent,
        started_at=epoch(),
        finished_at=None,
        status="running",
        calls=[],
        matrix=None,
        error=None,
    )


def column_of(model: ModelConfig | None) -> str:
    """The matrix column a model's cells are under."""
    return DECLARED if model is None else f"{model.provider}/{model.model}"


def judged(run: RunRow, cells: Sequence[ScoreRow]) -> RunRow:
    """The run with the matrix of the cells judged so far."""
    return run.model_copy(update={"matrix": matrix_of(cells)})


def finished(run: RunRow) -> RunRow:
    """The run done: every golden under every model was judged."""
    return run.model_copy(update={"status": "done", "finished_at": epoch()})


# A failing golden is a score; this is the run itself stopping early, its cells kept.
def stopped(run: RunRow, why: str) -> RunRow:
    """The run failed, and why."""
    return run.model_copy(update={"status": "failed", "finished_at": epoch(), "error": why})


async def put_run(session: AsyncSession, scope: Scope, run: RunRow) -> None:
    """Write the run whole, in its org and env."""
    await RunRepository(session).put(
        id=run.id,
        org=scope.org,
        env=scope.env,
        agent=run.agent,
        started_at=run.started_at,
        finished_at=run.finished_at,
        status=run.status,
        document=run.dump(),
    )


async def get_run(session: AsyncSession, scope: Scope, run: str) -> RunRow:
    """One run of the org in the env; another org's, or one nobody ran, is the same 404."""
    found = await RunRepository(session).get(scope.org, scope.env, run)
    if found is None:
        raise NotFound(NO_SUCH_RUN.format(id=run))
    return RunRow.model_validate(found.document)


async def list_runs(
    session: AsyncSession, scope: Scope, *, agent: str | None, since: float, limit: int
) -> list[RunRow]:
    """The org's runs in the env started after `since`, newest first, one agent's or all."""
    found = await RunRepository(session).listed(scope.org, scope.env, agent=agent, since=since, limit=limit)
    return [RunRow.model_validate(row.document) for row in found]


async def score(
    judges: Sequence[judging.GoldenJudge], case: judging.Case, model: llm.LLM[Never] | None
) -> list[judging.JudgeScore]:
    """Every judge over one case, in order: its verdict as a score, and the model calls it made."""
    chat = judging.as_chat(case)
    scores: list[judging.JudgeScore] = []
    for judge in judges:
        result = await judge.evaluate(chat_ctx=chat, llm=model)
        scores.append(
            judging.JudgeScore(
                metric=judge.name,
                score=EvaluationResult(judgments={judge.name: result}).score,
                passed=result.passed,
                reason=result.reasoning,
                criteria=result.instructions,
                judge_calls=judge.calls,
            )
        )
    return scores


# Every cell carries the call's own summary, never a number of its own.
def cell_of(
    opened: OpenedCall, case: judging.Case, scores: list[judging.JudgeScore], requests: Sequence[JsonObject] | None
) -> ScoreRow:
    """One golden under one model; a cell that did not hold carries the requests it was sent."""
    cell = ScoreRow(model=opened.model, golden=opened.golden, scores=scores, summary=case.summary)
    if all(cell_score.passed for cell_score in scores):
        return cell
    return cell.model_copy(update={"asked": None if requests is None else list(requests)})


def matrix_of(cells: Iterable[ScoreRow]) -> ScoreMatrix:
    """The matrix of these cells: the axes in the order they came, and every judge that broke."""
    rows = list(cells)
    return ScoreMatrix(
        models=list(dict.fromkeys(row.model for row in rows)),
        goldens=list(dict.fromkeys(row.golden for row in rows)),
        metrics=list(dict.fromkeys(score.metric for row in rows for score in row.scores)),
        judge_calls=sum(score.judge_calls for row in rows for score in row.scores),
        runs=rows,
        failures=[
            Failure(model=row.model, golden=row.golden, metric=score.metric)
            for row in rows
            for score in row.scores
            if not score.passed
        ],
    )
