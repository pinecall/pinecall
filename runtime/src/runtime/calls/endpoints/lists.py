"""The lists of calls: an agent's newest and the org's, one row each, as the console draws them."""

from typing import Annotated

from fastapi import APIRouter, Query

from runtime.agents.auth import KnownAgent
from runtime.calls import schemas
from runtime.calls.auth import ListingKey, TheLogs
from runtime.calls.service import lists
from runtime.postgres import Session

router = APIRouter()


@router.get("/v1/agents/{slug}/sessions", response_model_exclude_unset=True)
async def list_agent_calls(
    slug: KnownAgent, actor: ListingKey, logs: TheLogs, session: Session, query: Annotated[schemas.ListQuery, Query()]
) -> schemas.CallList:
    """The agent's newest calls, one row each."""
    found = await lists.list_calls(
        session,
        logs,
        actor,
        agent=slug,
        q=query.q,
        channel=query.channel,
        before=query.before,
        limit=query.limit,
        holders=query.holders,
        runs=query.runs,
    )
    return schemas.CallList.of(found)


@router.get("/v1/sessions", response_model_exclude_unset=True)
async def list_calls(
    actor: ListingKey, logs: TheLogs, session: Session, query: Annotated[schemas.ListQuery, Query()]
) -> schemas.CallList:
    """The org's newest calls across its agents, one row each."""
    found = await lists.list_calls(
        session,
        logs,
        actor,
        agent=query.agent,
        q=query.q,
        channel=query.channel,
        before=query.before,
        limit=query.limit,
        holders=query.holders,
        runs=query.runs,
    )
    return schemas.CallList.of(found)
