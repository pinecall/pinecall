"""Memory over HTTP: a contact's history read, what an agent's calls taught, the contact forgotten, one fact ended."""

import uuid
from typing import Annotated

from fastapi import APIRouter, Path, Query

from runtime.agents.auth import KnownAgent
from runtime.calls import service as calls
from runtime.compliance import service as compliance
from runtime.enums import ReadKind
from runtime.knowledge import schemas
from runtime.knowledge.auth import MemoryKey
from runtime.knowledge.service import memory
from runtime.postgres import Session

router = APIRouter()


# The whole history, superseded facts included; a call reads the current ones through `recall`.
@router.get("/v1/contacts/{contact}/memory")
async def get_contact_memory(contact: str, actor: MemoryKey, session: Session) -> schemas.ContactMemory:
    """Every fact ever kept of the contact, current first."""
    facts = await memory.read_history(session, actor.scope, contact, by=actor.asked_by)
    return schemas.ContactMemory(facts=[schemas.ContactFact.of(fact) for fact in facts])


# A fact is an agent's through the call that taught it: the rows are asked of the calls' heads, one
# more than the page shows, and the page is cut by memory's own cursor.
@router.get("/v1/agents/{slug}/memory")
async def list_agent_memory(
    slug: KnownAgent, actor: MemoryKey, session: Session, page: Annotated[schemas.MemoryPage, Query()]
) -> schemas.AgentMemory:
    """The current facts the agent's calls taught, across contacts, newest first, a page."""
    await compliance.record_read(session, actor.scope, slug, ReadKind.memory, by=actor.asked_by)
    like, after = memory.like_pattern(page.q), memory.parse_cursor(page.after)
    taught = await calls.list_taught(session, actor.scope, slug, like=like, after=after, limit=page.limit + 1)
    return schemas.AgentMemory.of(memory.page_taught(taught, page.limit))


@router.get("/v1/memory")
async def list_org_memory(
    actor: MemoryKey, session: Session, page: Annotated[schemas.MemoryPage, Query()]
) -> schemas.OrgMemory:
    """The current facts every agent's calls taught, each with its agent, newest first, a page."""
    await compliance.record_read(session, actor.scope, actor.org, ReadKind.memory, by=actor.asked_by)
    like, after = memory.like_pattern(page.q), memory.parse_cursor(page.after)
    taught = await calls.list_taught(session, actor.scope, None, like=like, after=after, limit=page.limit + 1)
    return schemas.OrgMemory.of(memory.page_taught(taught, page.limit))


# Reading and erasing are the contact's rights: no quota ever refuses them.
@router.delete("/v1/contacts/{contact}/memory")
async def forget_contact(contact: str, actor: MemoryKey, session: Session) -> schemas.Forgotten:
    """Every fact of the contact deleted, history included; zero is an answer, not a 404."""
    return schemas.Forgotten(forgotten=await memory.forget(session, actor.scope, contact))


# The row stays, ended: the history still shows it.
@router.delete("/v1/memory/facts/{id}")
async def forget_fact(
    fact: Annotated[uuid.UUID, Path(alias="id")], actor: MemoryKey, session: Session
) -> schemas.Forgotten:
    """One current fact ended from now on; 404 when there is none by that id."""
    await memory.invalidate(session, actor.scope, fact)
    return schemas.Forgotten(forgotten=1)
