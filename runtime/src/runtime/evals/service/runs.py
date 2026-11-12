"""An eval run's record: one agent, every golden under every model, written whole as it goes; what an erasure takes."""

from collections.abc import Sequence

from sqlalchemy.ext.asyncio import AsyncSession

from runtime.actor import Scope
from runtime.evals.models import EvalRun
from runtime.evals.repository import RunRepository
from runtime.evals.service.matrix import matrix_of
from runtime.exceptions import NotFound
from runtime.kit.crypto import random_id
from runtime.kit.time import epoch
from runtime.wire.declaration import ModelConfig
from runtime.wire.runs import Run, ScoreRow

# A run is coroutines of the gateway, so its deadline is a timeout; its finished calls stay.
A_RUN_MAY_TAKE_S = 15 * 60
# The column of the agent's own model, when the run named none.
THE_AGENTS_OWN = "declared"
TOOK_TOO_LONG = "the run passed its {minutes} minute deadline and was stopped"
NO_SUCH_RUN = "no eval run {id} in this key's org and env"


def new_run(agent: str) -> Run:
    """A run of the agent that starts now and opened nothing yet."""
    return Run(
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
    return THE_AGENTS_OWN if model is None else f"{model.provider}/{model.model}"


def judge(run: Run, cells: Sequence[ScoreRow]) -> Run:
    """The run with the matrix of the cells judged so far."""
    return run.model_copy(update={"matrix": matrix_of(cells)})


def finish(run: Run) -> Run:
    """The run done: every golden under every model was judged."""
    return run.model_copy(update={"status": "done", "finished_at": epoch()})


# A failing golden is a score; this is the run itself stopping early, its cells kept.
def stop(run: Run, why: str) -> Run:
    """The run failed, and why."""
    return run.model_copy(update={"status": "failed", "finished_at": epoch(), "error": why})


# The document is the run as the release before 2026-11 dumps and reads it: both follow one run.
async def put_run(session: AsyncSession, scope: Scope, run: Run) -> None:
    """Write the run whole, in its org and env."""
    await RunRepository(session).put(
        EvalRun(
            id=run.id,
            org=scope.org,
            env=scope.env,
            agent=run.agent,
            started_at=run.started_at,
            finished_at=run.finished_at,
            status=run.status,
            document=run.dump(),
        )
    )


async def get_run(session: AsyncSession, scope: Scope, run: str) -> Run:
    """One run of the org in the env; another org's, or one nobody ran, is the same 404."""
    found = await RunRepository(session).find(scope.org, scope.env, run)
    if found is None:
        raise NotFound(NO_SUCH_RUN.format(id=run))
    return Run.model_validate(found.document)


async def list_runs(session: AsyncSession, scope: Scope, *, agent: str | None, since: float, limit: int) -> list[Run]:
    """The org's runs in the env started after `since`, newest first, one agent's or all."""
    found = await RunRepository(session).list_newest(scope.org, scope.env, agent=agent, since=since, limit=limit)
    return [Run.model_validate(row.document) for row in found]


# The row names its org with no key to it, so no cascade reaches it: the erasure of an org, or of one
# of its agents, asks here (`EvalRun.__kept__`).
async def delete_runs(session: AsyncSession, org: str, agent: str | None = None) -> int:
    """Delete the org's eval runs, one agent's or all; how many went."""
    return await RunRepository(session).delete_of_org(org, agent)
