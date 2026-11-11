"""The flows endpoints: an event sent to an app, the work its process is owed, its runs and each run's journal."""

from typing import Annotated

from fastapi import APIRouter, Query, Request

from pinecall_runtime.calls import service as calls
from pinecall_runtime.flows import schemas, service
from pinecall_runtime.flows.auth import AppKey, ReadsRuns
from pinecall_runtime.kit.auth import Actor
from pinecall_runtime.kit.text import parse_slug
from pinecall_runtime.postgres import Session

router = APIRouter()


def _asked_by(actor: Actor) -> str:
    return actor.person.id if actor.person is not None else actor.key_id


@router.post("/v1/apps/{app}/events", status_code=202)
async def send_event(app: str, body: schemas.EventRequest, actor: AppKey, session: Session) -> schemas.EventSent:
    """Send an event to the app: kept until its process hears it, and it wakes a run waiting for one like it."""
    event = await service.send_event(session, actor.scope, parse_slug(app), body.name, body.data)
    return schemas.EventSent(id=event.id)


@router.post("/v1/apps/{app}/events/{event_id}/heard", status_code=204)
async def hear_event(app: str, event_id: int, actor: AppKey, session: Session) -> None:
    """The app's process handled the event."""
    await service.hear_event(session, actor.scope, parse_slug(app), event_id)


@router.post("/v1/apps/{app}/work")
async def take_work(app: str, body: schemas.WorkRequest, actor: AppKey, request: Request) -> schemas.Work:
    """What the app's process is owed, waited for up to `wait_s`: unheard events, and the runs ready to go on."""
    events, runs = await service.wait_for_work(request.app.state.sessions, actor.scope, parse_slug(app), body.wait_s)
    return schemas.Work(
        events=[schemas.EventRow.of(event) for event in events],
        runs=[schemas.RunRow.of(run, steps) for run, steps in runs],
    )


@router.post("/v1/apps/{app}/runs", status_code=201)
async def start_run(app: str, body: schemas.StartRequest, actor: AppKey, session: Session) -> schemas.RunRow:
    """Start a flow with an input; the same key is the same run."""
    return schemas.RunRow.of(
        await service.start_run(session, actor.scope, parse_slug(app), body.flow, body.key, body.input)
    )


@router.get("/v1/apps/{app}/runs")
async def list_runs(
    app: str,
    actor: ReadsRuns,
    session: Session,
    flow: Annotated[str | None, Query()] = None,
    status: Annotated[str | None, Query()] = None,
) -> schemas.RunList:
    """The app's runs, newest first; of one flow, or in one status, when named."""
    found = await service.list_runs(session, actor.scope, parse_slug(app), flow, status)
    return schemas.RunList(runs=[schemas.RunRow.of(run) for run in found])


@router.get("/v1/apps/{app}/runs/{run}")
async def read_run(app: str, run: str, actor: ReadsRuns, session: Session) -> schemas.RunRow:
    """One run with its journal."""
    found, steps = await service.run_of(session, actor.scope, parse_slug(app), run)
    return schemas.RunRow.of(found, steps)


@router.post("/v1/apps/{app}/runs/{run}/steps", status_code=201)
async def write_step(
    app: str, run: str, body: schemas.StepRequest, actor: AppKey, request: Request, session: Session
) -> schemas.RunRow:
    """Write the run's next step: a sleep, a wait, a call, or what a step the process ran came to."""
    serving: calls.Serving = request.app.state.serving
    found, _ = await service.write_step(session, serving, actor.scope, parse_slug(app), run, _asked_by(actor), body)
    return schemas.RunRow.of(found)


@router.post("/v1/apps/{app}/runs/{run}/end")
async def end_run(app: str, run: str, body: schemas.EndRequest, actor: AppKey, session: Session) -> schemas.RunRow:
    """The flow returned, or threw: the run is over."""
    return schemas.RunRow.of(await service.end_run(session, actor.scope, parse_slug(app), run, body.status, body.error))


@router.post("/v1/apps/{app}/runs/{run}/cancel")
async def cancel_run(app: str, run: str, actor: AppKey, session: Session) -> schemas.RunRow:
    """Stop a run where it stands."""
    return schemas.RunRow.of(await service.cancel_run(session, actor.scope, parse_slug(app), run))
