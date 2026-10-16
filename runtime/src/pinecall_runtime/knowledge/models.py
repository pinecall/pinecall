"""The knowledge tables: contact_memories, knowledge_bases, knowledge_files, knowledge_chunks."""

import uuid
from datetime import datetime

from sqlalchemy import REAL, TIMESTAMP, ForeignKey, ForeignKeyConstraint, Index, Integer, Text, Uuid
from sqlalchemy.orm import Mapped, mapped_column

from pinecall_runtime.enums import Env
from pinecall_runtime.kit.db import Model, StringEnum, Vector, utc_now


class ContactMemory(Model):
    """A fact, its category, the call it came from, and its place in time."""

    __tablename__ = "contact_memories"
    __table_args__ = (
        Index(
            "contact_memories_current",
            "org",
            "env",
            "holder",
            "contact",
            postgresql_where="invalidated_at IS NULL",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    org: Mapped[str] = mapped_column(ForeignKey("orgs.id", ondelete="CASCADE"), nullable=False)
    env: Mapped[Env] = mapped_column(StringEnum(Env), nullable=False)
    holder: Mapped[str] = mapped_column(Text, nullable=False)
    contact: Mapped[str] = mapped_column(Text, nullable=False)
    text: Mapped[str] = mapped_column(Text, nullable=False)
    category: Mapped[str | None] = mapped_column(Text)
    embedding: Mapped[list[float]] = mapped_column(Vector(), nullable=False)
    valid_from: Mapped[datetime] = mapped_column(TIMESTAMP(timezone=True), nullable=False)
    invalidated_at: Mapped[datetime | None] = mapped_column(TIMESTAMP(timezone=True))
    supersedes: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("contact_memories.id"))
    source_call: Mapped[str | None] = mapped_column(Text)
    confidence: Mapped[float] = mapped_column(REAL, nullable=False, default=1.0)
    created_at: Mapped[datetime] = mapped_column(TIMESTAMP(timezone=True), nullable=False, default=utc_now)
    model: Mapped[str] = mapped_column(Text, nullable=False, default="")


class KnowledgeBase(Model):
    """One base in one scope: the model it was embedded with, how many chunks, when it was pushed."""

    __tablename__ = "knowledge_bases"

    org: Mapped[str] = mapped_column(Text, ForeignKey("orgs.id", ondelete="CASCADE"), primary_key=True)
    env: Mapped[Env] = mapped_column(StringEnum(Env), primary_key=True)
    holder: Mapped[str] = mapped_column(Text, primary_key=True)
    base: Mapped[str] = mapped_column(Text, primary_key=True)
    model: Mapped[str] = mapped_column(Text, nullable=False)
    dimensions: Mapped[int] = mapped_column(Integer, nullable=False)
    chunks: Mapped[int] = mapped_column(Integer, nullable=False)
    pushed_at: Mapped[datetime] = mapped_column(TIMESTAMP(timezone=True), nullable=False, default=utc_now)


class KnowledgeFile(Model):
    """A file of a base: its text whole, its hash, how many chunks it was cut into."""

    __tablename__ = "knowledge_files"
    __table_args__ = (
        ForeignKeyConstraint(
            ["org", "env", "holder", "base"],
            ["knowledge_bases.org", "knowledge_bases.env", "knowledge_bases.holder", "knowledge_bases.base"],
            ondelete="CASCADE",
        ),
    )

    org: Mapped[str] = mapped_column(Text, primary_key=True)
    env: Mapped[Env] = mapped_column(StringEnum(Env), primary_key=True)
    holder: Mapped[str] = mapped_column(Text, primary_key=True)
    base: Mapped[str] = mapped_column(Text, primary_key=True)
    path: Mapped[str] = mapped_column(Text, primary_key=True)
    text: Mapped[str] = mapped_column(Text, nullable=False)
    chunks: Mapped[int] = mapped_column(Integer, nullable=False)
    pushed_at: Mapped[datetime] = mapped_column(TIMESTAMP(timezone=True), nullable=False, default=utc_now)
    sha256: Mapped[str] = mapped_column(Text, nullable=False, default="")


class KnowledgeChunk(Model):
    """One chunk of a file: its heading path, its order, its text and its vector."""

    __tablename__ = "knowledge_chunks"
    __table_args__ = (
        ForeignKeyConstraint(
            ["org", "env", "holder", "base"],
            ["knowledge_bases.org", "knowledge_bases.env", "knowledge_bases.holder", "knowledge_bases.base"],
            ondelete="CASCADE",
        ),
        Index("knowledge_chunks_by_base", "org", "env", "holder", "base"),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    org: Mapped[str] = mapped_column(Text, nullable=False)
    env: Mapped[Env] = mapped_column(StringEnum(Env), nullable=False)
    holder: Mapped[str] = mapped_column(Text, nullable=False)
    base: Mapped[str] = mapped_column(Text, nullable=False)
    path: Mapped[str] = mapped_column(Text, nullable=False)
    heading: Mapped[str | None] = mapped_column(Text)
    ordinal: Mapped[int] = mapped_column(Integer, nullable=False)
    text: Mapped[str] = mapped_column(Text, nullable=False)
    embedding: Mapped[list[float]] = mapped_column(Vector(), nullable=False)
