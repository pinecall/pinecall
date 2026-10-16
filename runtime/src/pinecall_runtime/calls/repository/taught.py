"""The facts a contact's memory holds, with the agent whose call taught each: a join on the call's head."""

import uuid
from datetime import datetime

from sqlalchemy import select, tuple_

from pinecall_runtime.calls.models import CallLogHead
from pinecall_runtime.kit.auth import Scope
from pinecall_runtime.kit.repository import Repository
from pinecall_runtime.knowledge.models import ContactMemory


class TaughtRepository(Repository[ContactMemory]):
    """What the calls taught, read with the agent that ran each."""

    model = ContactMemory

    # A fact is an agent's through the call that taught it: a golden's fact has no call, and no agent.
    async def taught_by(
        self, scope: Scope, agent: str | None, *, like: str | None, after: tuple[datetime, uuid.UUID] | None, limit: int
    ) -> list[tuple[ContactMemory, str | None]]:
        """A page of current facts the agent's calls taught (every agent's when None), with the agent."""
        statement = (
            select(ContactMemory, CallLogHead.agent)
            .join(CallLogHead, CallLogHead.log == ContactMemory.source_call)
            .where(
                ContactMemory.org == scope.org,
                ContactMemory.env == scope.env,
                ContactMemory.holder == scope.holder,
                ContactMemory.invalidated_at.is_(None),
            )
        )
        if agent is not None:
            statement = statement.where(CallLogHead.agent == agent)
        if like is not None:
            statement = statement.where(
                ContactMemory.text.ilike(like, escape="\\")
                | ContactMemory.contact.ilike(like, escape="\\")
                | ContactMemory.category.ilike(like, escape="\\")
            )
        if after is not None:
            statement = statement.where(tuple_(ContactMemory.valid_from, ContactMemory.id) < tuple_(after[0], after[1]))
        statement = statement.order_by(ContactMemory.valid_from.desc(), ContactMemory.id.desc()).limit(limit)
        return [(memory, name) for memory, name in (await self.session.execute(statement)).all()]
