"""An agent's inbox by contact: the threads, one thread, and what its reader has read."""

from typing import Annotated

from fastapi import APIRouter, Query

from runtime.agents.auth import KnownAgent
from runtime.calls import schemas
from runtime.calls.auth import CallsKey
from runtime.calls.service import inbox
from runtime.postgres import Session

router = APIRouter()


@router.get("/v1/agents/{slug}/threads")
async def list_threads(
    slug: KnownAgent, actor: CallsKey, session: Session, page: Annotated[schemas.ThreadQuery, Query()]
) -> schemas.ThreadList:
    """The agent's contacts, the one that moved last first, with what this reader has not read."""
    return schemas.ThreadList.of(await inbox.list_threads(session, actor, slug, after=page.after, limit=page.limit))


@router.get("/v1/agents/{slug}/threads/{contact}")
async def get_thread(slug: KnownAgent, contact: str, actor: CallsKey, session: Session) -> schemas.ThreadResponse:
    """A contact's calls with the agent merged into one thread, oldest first."""
    return schemas.ThreadResponse.of(await inbox.thread_of(session, actor.scope, slug, contact))


# The read cursor is the person's; a server's key keeps its own.
@router.post("/v1/agents/{slug}/threads/{contact}/read", status_code=204)
async def mark_thread_read(slug: KnownAgent, contact: str, actor: CallsKey, session: Session) -> None:
    """This reader has read the thread up to now."""
    await inbox.mark_read(session, actor, slug, contact)
