"""The knowledge tables: contact_memories, knowledge_bases, knowledge_files, knowledge_chunks; a language, a kind."""

import uuid
from datetime import datetime
from enum import StrEnum

from sqlalchemy import REAL, TIMESTAMP, ForeignKey, ForeignKeyConstraint, Index, Integer, Text, Uuid
from sqlalchemy.orm import Mapped, mapped_column

from runtime.enums import Env
from runtime.kit.db import Kept, Model, StringEnum, Vector, utc_now


# Each has a partial BM25 index of its own (migrations/versions/…000007); `simple` stems nothing.
class Language(StrEnum):
    """The text-search configuration a base's words are stemmed with: one Postgres ships."""

    english = "english"
    spanish = "spanish"
    portuguese = "portuguese"
    french = "french"
    german = "german"
    italian = "italian"
    dutch = "dutch"
    simple = "simple"


class ChunkKind(StrEnum):
    """What a row of a base is: a piece of a file, or a question the piece at the same ordinal answers."""

    text = "text"
    ask = "ask"


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
    # The embedding is the box's to compute again; the words are the org's.
    __kept__ = Kept(
        call="source_call",
        contact="contact",
        exported=("env", "holder", "contact", "text", "category", "valid_from", "invalidated_at", "source_call"),
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
    """One base in one scope: the model it was embedded with, its language, how many chunks, when it was pushed."""

    __tablename__ = "knowledge_bases"
    __kept__ = Kept(
        not_exported="a base's count and its model, made again by pushing its files: the export carries them"
    )

    org: Mapped[str] = mapped_column(Text, ForeignKey("orgs.id", ondelete="CASCADE"), primary_key=True)
    env: Mapped[Env] = mapped_column(StringEnum(Env), primary_key=True)
    holder: Mapped[str] = mapped_column(Text, primary_key=True)
    base: Mapped[str] = mapped_column(Text, primary_key=True)
    model: Mapped[str] = mapped_column(Text, nullable=False)
    dimensions: Mapped[int] = mapped_column(Integer, nullable=False)
    chunks: Mapped[int] = mapped_column(Integer, nullable=False)
    pushed_at: Mapped[datetime] = mapped_column(TIMESTAMP(timezone=True), nullable=False, default=utc_now)
    # The text-search configuration its words are stemmed with.
    language: Mapped[Language] = mapped_column(StringEnum(Language), nullable=False)


# No key of its own reaches a file or a chunk from its org (`org` is text): each goes with its base by
# the composite key's cascade, and the base with its org.
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
    __kept__ = Kept(
        exported=("env", "holder", "base", "path", "text", "pushed_at"),
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
    """One chunk of a file: its heading path, its order, its text and its vector; or a question that chunk answers."""

    __tablename__ = "knowledge_chunks"
    __table_args__ = (
        ForeignKeyConstraint(
            ["org", "env", "holder", "base"],
            ["knowledge_bases.org", "knowledge_bases.env", "knowledge_bases.holder", "knowledge_bases.base"],
            ondelete="CASCADE",
        ),
        Index("knowledge_chunks_by_base", "org", "env", "holder", "base"),
    )
    __kept__ = Kept(
        not_exported="a file cut and embedded: the words are in its file, the vectors the box's to compute again",
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
    # The base's, on every chunk: each language's partial BM25 index reads its own rows.
    language: Mapped[Language] = mapped_column(StringEnum(Language), nullable=False)
    kind: Mapped[ChunkKind] = mapped_column(StringEnum(ChunkKind), nullable=False, default=ChunkKind.text)
