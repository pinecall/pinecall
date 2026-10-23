"""The calibration endpoints: a person labels what a judge should have said; each judge is judged."""

from typing import Annotated

from fastapi import APIRouter, Query

from pinecall_runtime.accounts.service import keys
from pinecall_runtime.calls import service as calls
from pinecall_runtime.calls.auth import Reader, TheServing, check_readable
from pinecall_runtime.evals.auth import EvalsKey
from pinecall_runtime.evals.endpoints.reading import NO_SUCH_CALL, asked_by
from pinecall_runtime.exceptions import NotFound
from pinecall_runtime.judging import schemas as judged
from pinecall_runtime.judging import service as judging
from pinecall_runtime.postgres import Session

router = APIRouter()


# The key must read the call, as a replay's does; the label is kept in the call's own env.
@router.post("/v1/evals/calibration", status_code=204)
async def label_call(body: judged.LabelRequest, actor: EvalsKey, serving: TheServing, session: Session) -> None:
    """Keep what one judge should have answered on a finished call, replacing the last label."""
    await check_readable(session, serving, Reader(actor=actor), body.call)
    kept = await calls.head_of_call(session, body.call)
    if kept is None or kept.scope is None:
        raise NotFound(NO_SUCH_CALL.format(call=body.call))
    keys.check_agent(actor, kept.agent)
    where = judging.Where(org=actor.org, env=kept.scope.env, agent=kept.agent)
    await judging.check_labellable(session, where, body.judge)
    label = judging.Label(call=body.call, judge=body.judge, held=body.held, author=asked_by(actor), note=body.note)
    await judging.label_call(session, where, label)


@router.get("/v1/evals/calibration")
async def read_calibration(
    actor: EvalsKey, session: Session, agent: Annotated[str | None, Query()] = None
) -> judged.Calibration:
    """Each judge's agreement with the labels on the key's env's calls, one agent's or all."""
    if agent is not None:
        keys.check_agent(actor, agent)
    return await judging.calibration_of(session, actor.org, actor.env, agent)
