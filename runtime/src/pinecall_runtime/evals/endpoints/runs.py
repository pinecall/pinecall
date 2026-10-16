"""The run endpoints: a suite played through the app that holds the agent, and the runs kept."""

from typing import Annotated

from fastapi import APIRouter, Path, Query

from pinecall_runtime.accounts.service import keys
from pinecall_runtime.calls.auth import TheServing
from pinecall_runtime.evals import schemas, service
from pinecall_runtime.evals.auth import EvalsKey, TheRunner
from pinecall_runtime.exceptions import NotFound
from pinecall_runtime.postgres import Session

router = APIRouter()

NO_AGENT = "no app is holding agent {slug}"


@router.post("/v1/evals/run", response_model_exclude_unset=True)
async def start_suite(
    body: schemas.RunSuiteRequest, actor: EvalsKey, serving: TheServing, runner: TheRunner, session: Session
) -> schemas.RunRow:
    """Start a run: every golden under every model through the app that holds the agent; the run, `running`."""
    keys.check_agent(actor, body.agent)
    registration = serving.registry.serving(actor.scope, body.agent, body.app)
    if registration is None:
        raise NotFound(NO_AGENT.format(slug=body.agent))
    return await service.start_suite(session, serving, runner, body, actor.scope, registration)


@router.get("/v1/evals/runs", response_model_exclude_unset=True)
async def list_runs(
    actor: EvalsKey, session: Session, query: Annotated[schemas.RunListQuery, Query()]
) -> schemas.RunList:
    """The runs of the key's org in its env, newest first."""
    found = await service.list_runs(session, actor.scope, agent=query.agent, since=query.since, limit=query.limit)
    return schemas.RunList(runs=found)


@router.get("/v1/evals/runs/{id}", response_model_exclude_unset=True)
async def get_run(run: Annotated[str, Path(alias="id")], actor: EvalsKey, session: Session) -> schemas.RunRow:
    """One run; another org's, or one nobody ran, is the same 404."""
    return await service.get_run(session, actor.scope, run)
