"""Callbacks: somebody the overflow told to wait, and the org's list of them."""

from typing import Annotated

from fastapi import APIRouter, Query

from pinecall_runtime.calls import schemas
from pinecall_runtime.calls.auth import CallsKey, TheServing, WorkerKey
from pinecall_runtime.calls.service import callbacks
from pinecall_runtime.postgres import Session

router = APIRouter()


@router.post("/v1/callbacks", status_code=204)
async def request_callback(
    body: schemas.CallbackRequest, actor: WorkerKey, serving: TheServing, session: Session
) -> None:
    """Somebody the overflow told to wait for a call back, on the agent's log."""
    await callbacks.request_callback(session, serving.logs, actor, body)


@router.get("/v1/callbacks", response_model_exclude_unset=True)
async def list_callbacks(
    actor: CallsKey, serving: TheServing, session: Session, query: Annotated[schemas.CallbackQuery, Query()]
) -> schemas.CallbackList:
    """The org's callbacks in the key's env, oldest first, a page at a time."""
    return await callbacks.list_callbacks(session, serving.logs, actor, after=query.after, agent=query.agent)
