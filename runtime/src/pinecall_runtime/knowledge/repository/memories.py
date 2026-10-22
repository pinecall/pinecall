"""The contact_memories table: a contact's facts in one scope, current and past, and the recall over them."""

import uuid
from collections.abc import Sequence
from datetime import datetime
from typing import Any

from sqlalchemy import delete, func, select, update

from pinecall_runtime.enums import Env
from pinecall_runtime.kit.auth import Scope
from pinecall_runtime.kit.repository import Repository
from pinecall_runtime.knowledge.models import ContactMemory
from pinecall_runtime.knowledge.repository.search import Hit, Lexical, hybrid

MEMORY_TEXT_INDEX = "contact_memories_text_bm25"
MEMORY_NOW = "org = :org AND env = :env AND holder = :holder AND contact = :contact AND invalidated_at IS NULL"
MEMORY_THEN = (
    "org = :org AND env = :env AND holder = :holder AND contact = :contact"
    " AND valid_from <= :as_of AND (invalidated_at IS NULL OR invalidated_at > :as_of)"
)
# Vectors of two models share a width and still mean nothing to each other.
SAME_MODEL = "model = :model"
MEMORY_COLUMNS = (
    "id",
    "contact",
    "category",
    "text",
    "valid_from",
    "invalidated_at",
    "supersedes",
    "source_call",
    "model",
    "confidence",
)


class MemoryRepository(Repository[ContactMemory]):
    """A contact's facts in one scope: current, history, pages by agent, the hybrid recall."""

    model = ContactMemory

    async def current(self, scope: Scope, contact: str) -> Sequence[ContactMemory]:
        """The contact's facts that hold now, oldest first."""
        statement = (
            self.statement()
            .where(*_contacts(scope, contact), ContactMemory.invalidated_at.is_(None))
            .order_by(ContactMemory.valid_from, ContactMemory.id)
        )
        return await self.all(statement)

    async def history(self, scope: Scope, contact: str) -> Sequence[ContactMemory]:
        """Every fact ever kept of the contact in the scope, current first, newest first."""
        statement = (
            self.statement()
            .where(*_contacts(scope, contact))
            .order_by(ContactMemory.invalidated_at.is_(None).desc(), ContactMemory.valid_from.desc(), ContactMemory.id)
        )
        return await self.all(statement)

    async def get_current(self, scope: Scope, fact_id: uuid.UUID) -> ContactMemory | None:
        """One current fact of the scope by id."""
        statement = self.statement().where(
            ContactMemory.org == scope.org,
            ContactMemory.env == scope.env,
            ContactMemory.holder == scope.holder,
            ContactMemory.id == fact_id,
            ContactMemory.invalidated_at.is_(None),
        )
        return await self.one_or_none(statement)

    async def kept_by_org(self, org: str, env: Env) -> int:
        """How many current facts the org keeps in the env, every holder's and contact's."""
        statement = (
            select(func.count())
            .select_from(ContactMemory)
            .where(ContactMemory.org == org, ContactMemory.env == env, ContactMemory.invalidated_at.is_(None))
        )
        return int((await self.session.execute(statement)).scalar_one())

    async def forget(self, scope: Scope, contact: str) -> int:
        """Delete every fact of the contact in the scope, history included; how many went."""
        return await self.changed(delete(ContactMemory).where(*_contacts(scope, contact)))

    async def end(self, scope: Scope, fact_id: uuid.UUID, *, at: datetime) -> bool:
        """End one current fact at `at`; False when there is none by that id."""
        statement = (
            update(ContactMemory)
            .where(
                ContactMemory.id == fact_id,
                ContactMemory.org == scope.org,
                ContactMemory.env == scope.env,
                ContactMemory.holder == scope.holder,
                ContactMemory.invalidated_at.is_(None),
            )
            .values(invalidated_at=at)
        )
        return bool(await self.changed(statement))

    async def stale(self, model: str, batch: int) -> Sequence[ContactMemory]:
        """A batch of facts another model embedded, oldest first."""
        statement = (
            self.statement()
            .where(ContactMemory.model != model)
            .order_by(ContactMemory.created_at, ContactMemory.id)
            .limit(batch)
        )
        return await self.all(statement)

    async def recall(
        self, scope: Scope, contact: str, *, model: str, as_of: datetime | None, vector: str, words: str, room: int
    ) -> list[Hit]:
        """The hybrid search over the contact's facts holding now, or at a moment."""
        params = {
            "org": scope.org,
            "env": scope.env.value,
            "holder": scope.holder,
            "contact": contact,
            "model": model,
            "as_of": as_of,
        }
        return await hybrid(
            self.session,
            "contact_memories",
            [Lexical(MEMORY_TEXT_INDEX)],
            MEMORY_COLUMNS,
            params,
            scope=MEMORY_NOW if as_of is None else MEMORY_THEN,
            same_space=SAME_MODEL,
            vector=vector,
            words=words,
            room=room,
        )


def _contacts(scope: Scope, contact: str) -> tuple[Any, ...]:
    return (
        ContactMemory.org == scope.org,
        ContactMemory.env == scope.env,
        ContactMemory.holder == scope.holder,
        ContactMemory.contact == contact,
    )
