"""Callbacks: somebody the overflow told to wait, and the org's list of them."""

from typing import Annotated

from fastapi import APIRouter, Query

from runtime.agents.auth import KnownFilter
from runtime.calls import schemas
from runtime.calls.auth import CallsKey, TheLogs, WorkerKey
from runtime.calls.service import callbacks
from runtime.postgres import Session

router = APIRouter()


@router.post("/v1/callbacks", status_code=204)
async def request_callback(body: schemas.CallbackRequest, actor: WorkerKey, logs: TheLogs, session: Session) -> None:
    """Somebody the overflow told to wait for a call back, on the agent's log."""
    asked = callbacks.CallbackAsked(agent=body.agent, channel=body.channel, number=body.number, call=body.call)
    await callbacks.request_callback(session, logs, actor, asked)


@router.get("/v1/callbacks", response_model_exclude_unset=True)
async def list_callbacks(
    actor: CallsKey, agent: KnownFilter, session: Session, query: Annotated[schemas.CallbackQuery, Query()]
) -> schemas.CallbackList:
    """The org's callbacks in the key's env, oldest first, a page at a time; one agent's, a known one."""
    return schemas.CallbackList.of(await callbacks.list_callbacks(session, actor, after=query.after, agent=agent))
