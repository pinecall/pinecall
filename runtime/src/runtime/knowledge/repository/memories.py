"""The contact_memories table: a contact's facts in one scope, current and past, and the recall over them."""

import dataclasses
import uuid
from collections.abc import Sequence
from datetime import datetime
from typing import Any

from sqlalchemy import RowMapping, delete, func, select, update

from runtime.actor import Scope
from runtime.enums import Env
from runtime.kit.repository import Repository
from runtime.knowledge.models import ContactMemory
from runtime.knowledge.repository.search import FactFound, Hit, HybridQuery, Lexical, hybrid

MEMORY_TEXT_INDEX = "contact_memories_text_bm25"
MEMORY_NOW = "org = :org AND env = :env AND holder = :holder AND contact = :contact AND invalidated_at IS NULL"
# Vectors of two models share a width and still mean nothing to each other.
SAME_MODEL = "model = :model"
# What a recall reads of a fact is what `FactFound` holds, by the columns' own names.
FACT_COLUMNS = tuple(one.name for one in dataclasses.fields(FactFound))


class MemoryRepository(Repository[ContactMemory]):
    """A contact's facts in one scope: current, history, ended, forgotten, the hybrid recall."""

    model = ContactMemory

    async def list_current(self, scope: Scope, contact: str) -> Sequence[ContactMemory]:
        """The contact's facts that hold now, oldest first."""
        statement = (
            self.statement()
            .where(*_of_contact(scope, contact), ContactMemory.invalidated_at.is_(None))
            .order_by(ContactMemory.valid_from, ContactMemory.id)
        )
        return await self.all(statement)

    async def list_history(self, scope: Scope, contact: str) -> Sequence[ContactMemory]:
        """Every fact ever kept of the contact in the scope, current first, newest first."""
        statement = (
            self.statement()
            .where(*_of_contact(scope, contact))
            .order_by(ContactMemory.invalidated_at.is_(None).desc(), ContactMemory.valid_from.desc(), ContactMemory.id)
        )
        return await self.all(statement)

    async def find_current(self, scope: Scope, fact_id: uuid.UUID) -> ContactMemory | None:
        """One current fact of the scope by id."""
        return await self.one_or_none(self.statement().where(*_current_in(scope, fact_id)))

    async def count_current(self, org: str, env: Env) -> int:
        """How many current facts the org keeps in the env, every holder's and contact's."""
        statement = (
            select(func.count())
            .select_from(ContactMemory)
            .where(ContactMemory.org == org, ContactMemory.env == env, ContactMemory.invalidated_at.is_(None))
        )
        return int((await self.session.execute(statement)).scalar_one())

    async def delete_of_contact(self, scope: Scope, contact: str) -> int:
        """Delete every fact of the contact in the scope, history included; how many went."""
        return await self.change(delete(ContactMemory).where(*_of_contact(scope, contact)))

    async def end(self, scope: Scope, fact_id: uuid.UUID, *, at: datetime) -> bool:
        """End one current fact at `at`; False when there is none by that id."""
        statement = update(ContactMemory).where(*_current_in(scope, fact_id)).values(invalidated_at=at)
        return bool(await self.change(statement))

    async def list_stale(self, model: str, batch: int) -> Sequence[ContactMemory]:
        """A batch of facts another model embedded, oldest first."""
        statement = (
            self.statement()
            .where(ContactMemory.model != model)
            .order_by(ContactMemory.created_at, ContactMemory.id)
            .limit(batch)
        )
        return await self.all(statement)

    async def put_embedding(self, fact_id: uuid.UUID, embedding: list[float], model: str) -> None:
        """Replace one fact's vector with the one this model gave its text."""
        statement = update(ContactMemory).where(ContactMemory.id == fact_id).values(embedding=embedding, model=model)
        await self.change(statement)

    async def recall(
        self, scope: Scope, contact: str, *, model: str, vector: Sequence[float], words: str, room: int
    ) -> list[Hit[FactFound]]:
        """The hybrid search over the contact's facts holding now."""
        query = HybridQuery(
            table="contact_memories",
            columns=FACT_COLUMNS,
            scope=MEMORY_NOW,
            params={
                "org": scope.org,
                "env": scope.env.value,
                "holder": scope.holder,
                "contact": contact,
                "model": model,
            },
            lexical=[Lexical(MEMORY_TEXT_INDEX)],
            vector=vector,
            words=words,
            room=room,
            same_space=SAME_MODEL,
        )
        return await hybrid(self.session, query, _read_fact)


def _read_fact(row: RowMapping) -> FactFound:
    return FactFound(**{column: row[column] for column in FACT_COLUMNS})


def _of_contact(scope: Scope, contact: str) -> tuple[Any, ...]:
    return (
        ContactMemory.org == scope.org,
        ContactMemory.env == scope.env,
        ContactMemory.holder == scope.holder,
        ContactMemory.contact == contact,
    )


def _current_in(scope: Scope, fact_id: uuid.UUID) -> tuple[Any, ...]:
    return (
        ContactMemory.id == fact_id,
        ContactMemory.org == scope.org,
        ContactMemory.env == scope.env,
        ContactMemory.holder == scope.holder,
        ContactMemory.invalidated_at.is_(None),
    )
