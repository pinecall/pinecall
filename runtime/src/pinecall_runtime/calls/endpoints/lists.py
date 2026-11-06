"""The lists of calls: an agent's newest and the org's, one row each, as the console draws them."""

from dataclasses import replace
from typing import Annotated

from fastapi import APIRouter, Query

from pinecall_runtime.agents.auth import KnownAgent
from pinecall_runtime.calls import schemas
from pinecall_runtime.calls.auth import ReaderDep, TheServing
from pinecall_runtime.calls.service import ListFilters, lists
from pinecall_runtime.exceptions import Forbidden
from pinecall_runtime.postgres import Session

router = APIRouter()


@router.get("/v1/agents/{slug}/sessions", response_model_exclude_unset=True)
async def list_agent_calls(
    slug: KnownAgent,
    reader: ReaderDep,
    serving: TheServing,
    session: Session,
    query: Annotated[schemas.ListQuery, Query()],
) -> schemas.CallList:
    """The agent's newest calls, one row each."""
    wanted = ListFilters(agent=slug, q=query.q or None, channel=query.channel, before=query.before)
    return await _sessions(session, serving, reader, wanted, query)


@router.get("/v1/sessions", response_model_exclude_unset=True)
async def list_calls(
    reader: ReaderDep, serving: TheServing, session: Session, query: Annotated[schemas.ListQuery, Query()]
) -> schemas.CallList:
    """The org's newest calls across its agents, one row each."""
    wanted = ListFilters(agent=query.agent or None, q=query.q or None, channel=query.channel, before=query.before)
    return await _sessions(session, serving, reader, wanted, query)


async def _sessions(
    session: Session, serving: TheServing, reader: ReaderDep, wanted: ListFilters, query: schemas.ListQuery
) -> schemas.CallList:
    scope = reader.scope
    if reader.actor is None or scope is None:
        raise Forbidden("a list of calls is read with a key, not a call's token")
    asked = replace(wanted, holders=lists.copies_listed(reader.actor))
    found = await lists.find_calls(session, scope, asked, limit=query.limit)
    declared = {slug: serving.registry.declared(slug) for slug in {wanted.agent or ""}}
    rows = await lists.call_rows(
        session, serving.logs, found.calls, declared if wanted.agent else {}, holders=query.holders
    )
    return schemas.CallList(calls=rows, total=found.total, next=found.next)
