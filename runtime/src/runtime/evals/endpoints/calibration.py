"""The calibration endpoints: a judge's verdict labelled by a person, and each judge's agreement with the labels."""

from typing import Annotated

from fastapi import APIRouter, Query

from runtime.accounts import service as accounts
from runtime.calls import service as calls
from runtime.evals import schemas
from runtime.evals.auth import EvalsKey
from runtime.evals.service import calibration
from runtime.postgres import Session

router = APIRouter()


# The key must read the call, as a replay's does; the label is kept in the call's own env.
@router.post("/v1/evals/calibration", status_code=204)
async def label_call(body: schemas.LabelRequest, actor: EvalsKey, session: Session) -> None:
    """Keep what one judge should have answered on a finished call, replacing the last label."""
    read = await calls.read_for_key(session, actor, body.call)
    where = calibration.Where(org=actor.org, env=read.env, agent=read.agent)
    label = calibration.Label(body.call, body.judge, body.held, author=actor.asked_by, note=body.note)
    await calibration.label_call(session, where, label)


@router.get("/v1/evals/calibration")
async def read_calibration(
    actor: EvalsKey, session: Session, agent: Annotated[str | None, Query()] = None
) -> schemas.Calibration:
    """Each judge's agreement with the labels on the key's env's calls, one agent's or all."""
    if agent is not None:
        accounts.check_agent(actor, agent)
    return schemas.Calibration.of(await calibration.calibration_of(session, actor.org, actor.env, agent))
