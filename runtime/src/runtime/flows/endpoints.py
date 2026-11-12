"""The flows endpoints: an event sent to an app, the work its process is owed, its runs and each run's journal."""

from typing import Annotated

from fastapi import APIRouter, Query

from runtime.enums import RunStatus
from runtime.flows import schemas, service
from runtime.flows.auth import TheApp, TheAppRead, TheDial, TheHolders
from runtime.handles import TheSessions
from runtime.live.auth import AppKey
from runtime.postgres import Session

router = APIRouter()


@router.post("/v1/apps/{app}/events", status_code=202)
async def send_event(app: TheApp, body: schemas.EventRequest, session: Session) -> schemas.EventSent:
    """Send an event to the app: kept until its process hears it, and it wakes a run waiting for one like it."""
    return schemas.EventSent.of(await service.send_event(session, app, body.name, body.data))


@router.post("/v1/apps/{app}/events/{event_id}/heard", status_code=204)
async def hear_event(app: TheApp, event_id: int, session: Session) -> None:
    """The app's process handled the event."""
    await service.hear_event(session, app, event_id)


# No session of the request's: each look of the wait is a transaction of its own.
@router.post("/v1/apps/{app}/work")
async def take_work(app: TheApp, body: schemas.WorkRequest, sessions: TheSessions) -> schemas.Work:
    """What the app's process is owed, waited for up to `wait_s`: unheard events, and the runs ready to go on."""
    return schemas.Work.of(await service.wait_for_work(sessions, app, body.wait_s))


@router.post("/v1/apps/{app}/runs", status_code=201)
async def start_run(app: TheApp, body: schemas.StartRequest, session: Session) -> schemas.RunRow:
    """Start a flow with an input; the same key is the same run."""
    return schemas.RunRow.of(await service.start_run(session, app, body.flow, body.key, body.input))


@router.get("/v1/apps/{app}/runs")
async def list_runs(
    app: TheAppRead,
    session: Session,
    flow: Annotated[str | None, Query()] = None,
    status: Annotated[str | None, Query()] = None,
) -> schemas.RunList:
    """The app's runs, newest first; of one flow, or in one status, when named."""
    found = await service.list_runs(session, app, flow, status)
    return schemas.RunList(runs=[schemas.RunRow.of(run) for run in found])


@router.get("/v1/apps/{app}/runs/{run}")
async def read_run(app: TheAppRead, run: str, session: Session) -> schemas.RunRow:
    """One run with its journal."""
    return schemas.RunRow.of(await service.get_run(session, app, run))


@router.post("/v1/apps/{app}/runs/{run}/steps", status_code=201)
async def write_step(
    app: TheApp,
    run: str,
    body: schemas.StepRequest,
    actor: AppKey,
    holders: TheHolders,
    dial: TheDial,
    session: Session,
) -> schemas.RunRow:
    """Write the run's next step: a sleep, a wait, a call, or what a step the process ran came to."""
    return schemas.RunRow.of(await service.write_step(session, holders, dial, app, run, actor.asked_by, body))


@router.post("/v1/apps/{app}/runs/{run}/end")
async def end_run(app: TheApp, run: str, body: schemas.EndRequest, session: Session) -> schemas.RunRow:
    """The flow returned, or threw: the run is over."""
    return schemas.RunRow.of(await service.end_run(session, app, run, RunStatus(body.status), body.error))


@router.post("/v1/apps/{app}/runs/{run}/cancel")
async def cancel_run(app: TheApp, run: str, session: Session) -> schemas.RunRow:
    """Stop a run where it stands."""
    return schemas.RunRow.of(await service.cancel_run(session, app, run))
