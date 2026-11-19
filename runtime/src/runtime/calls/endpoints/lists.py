"""The lists of calls: an agent's newest and the org's, one row each, as the console draws them."""

import dataclasses
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
    asked = dataclasses.replace(lists.Asked(**query.model_dump()), agent=slug)
    found = await lists.list_calls(session, logs, actor, asked)
    return schemas.CallList.of(found)


@router.get("/v1/sessions", response_model_exclude_unset=True)
async def list_calls(
    actor: ListingKey, logs: TheLogs, session: Session, query: Annotated[schemas.ListQuery, Query()]
) -> schemas.CallList:
    """The org's newest calls across its agents, one row each."""
    found = await lists.list_calls(session, logs, actor, lists.Asked(**query.model_dump()))
    return schemas.CallList.of(found)
