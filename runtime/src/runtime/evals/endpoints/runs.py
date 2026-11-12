"""The run endpoints: a suite started, the runs of the key's env, one run."""

from typing import Annotated

from fastapi import APIRouter, Path, Query

from runtime.evals import schemas
from runtime.evals.auth import EvalsKey, TheHarness
from runtime.evals.service import runs, suites
from runtime.postgres import Session
from runtime.wire.runs import Run

router = APIRouter()


# No session is asked for: the run's rows are written in transactions of their own, and it plays
# after this answers.
@router.post("/v1/evals/run", response_model_exclude_unset=True)
async def start_suite(body: schemas.RunSuiteRequest, actor: EvalsKey, parts: TheHarness) -> Run:
    """Start a run: every golden under every model through the app that holds the agent; the run, `running`."""
    asked = suites.Asked(
        agent=body.agent,
        goldens=tuple(body.goldens),
        cases=tuple(body.cases),
        dataset=body.dataset,
        version=body.version,
        models=tuple(body.models),
        app=body.app,
        spoken=body.voice,
        interferer_db=body.interferer_db,
        packet_loss=body.packet_loss,
        ambience=body.ambience,
    )
    return await suites.start_suite(parts, actor, asked)


@router.get("/v1/evals/runs", response_model_exclude_unset=True)
async def list_runs(
    actor: EvalsKey, session: Session, query: Annotated[schemas.RunListQuery, Query()]
) -> schemas.RunList:
    """The runs of the key's org in its env, newest first."""
    found = await runs.list_runs(session, actor.scope, agent=query.agent, since=query.since, limit=query.limit)
    return schemas.RunList(runs=found)


@router.get("/v1/evals/runs/{id}", response_model_exclude_unset=True)
async def get_run(run: Annotated[str, Path(alias="id")], actor: EvalsKey, session: Session) -> Run:
    """One run; another org's, or one nobody ran, is the same 404."""
    return await runs.get_run(session, actor.scope, run)
