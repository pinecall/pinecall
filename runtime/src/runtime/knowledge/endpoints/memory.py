"""A contact's memory over HTTP: its history read, the contact forgotten, one fact ended."""

import uuid
from typing import Annotated

from fastapi import APIRouter, Path

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
