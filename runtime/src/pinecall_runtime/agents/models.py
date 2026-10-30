"""The agents tables: canaries, config, declarations, documents, lines, widgets, hold_audio, lexicon, prompts."""

from datetime import datetime
from typing import Any

from sqlalchemy import (
    REAL,
    TIMESTAMP,
    BigInteger,
    Boolean,
    Float,
    ForeignKey,
    Identity,
    Index,
    Integer,
    LargeBinary,
    Text,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from pinecall_runtime.enums import Env, HoldPlayed
from pinecall_runtime.kit.db import Model, StringEnum, utc_now


class AgentCanary(Model):
    """Which version takes `share` % of the scope's calls; NULL version is the canary cleared."""

    __tablename__ = "agent_canaries"
    __table_args__ = (
        Index("agent_canaries_standing", "org", "env", "holder", "agent", text("set_at DESC"), text("id DESC")),
    )

    id: Mapped[int] = mapped_column(BigInteger, Identity(always=True), primary_key=True)
    org: Mapped[str] = mapped_column(ForeignKey("orgs.id", ondelete="CASCADE"), nullable=False)
    env: Mapped[Env] = mapped_column(StringEnum(Env), nullable=False)
    holder: Mapped[str] = mapped_column(Text, nullable=False)
    agent: Mapped[str] = mapped_column(Text, nullable=False)
    version: Mapped[int | None] = mapped_column(Integer)
    share: Mapped[int | None] = mapped_column(Integer)
    author: Mapped[str] = mapped_column(Text, nullable=False)
    note: Mapped[str | None] = mapped_column(Text)
    set_at: Mapped[datetime] = mapped_column(TIMESTAMP(timezone=True), nullable=False, default=utc_now)


class AgentConfig(Model):
    """The tuning an org set on an agent, versioned per (org, env, holder, agent)."""

    __tablename__ = "agent_config"

    org: Mapped[str] = mapped_column(ForeignKey("orgs.id", ondelete="CASCADE"), primary_key=True)
    env: Mapped[Env] = mapped_column(StringEnum(Env), primary_key=True)
    holder: Mapped[str] = mapped_column(Text, primary_key=True)
    agent: Mapped[str] = mapped_column(Text, primary_key=True)
    version: Mapped[int] = mapped_column(Integer, primary_key=True)
    config: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    author: Mapped[str] = mapped_column(Text, nullable=False)
    note: Mapped[str | None] = mapped_column(Text)
    set_at: Mapped[datetime] = mapped_column(TIMESTAMP(timezone=True), nullable=False, default=utc_now)


class AgentDeclaration(Model):
    """The last declaration an app made of the agent in a scope: what its class fixes, kept past the socket."""

    __tablename__ = "agent_declarations"

    org: Mapped[str] = mapped_column(ForeignKey("orgs.id", ondelete="CASCADE"), primary_key=True)
    env: Mapped[Env] = mapped_column(StringEnum(Env), primary_key=True)
    holder: Mapped[str] = mapped_column(Text, primary_key=True)
    agent: Mapped[str] = mapped_column(Text, primary_key=True)
    # The wire's AgentConfig as the app sent it, every configure of one socket merged into the first.
    declared: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    sdk: Mapped[str | None] = mapped_column(Text)
    declared_at: Mapped[datetime] = mapped_column(TIMESTAMP(timezone=True), nullable=False, default=utc_now)


class AgentDocument(Model):
    """A JSON document an agent's app publishes under a name, read by any page with no key."""

    __tablename__ = "agent_documents"

    org: Mapped[str] = mapped_column(ForeignKey("orgs.id", ondelete="CASCADE"), primary_key=True)
    env: Mapped[Env] = mapped_column(StringEnum(Env), primary_key=True)
    agent: Mapped[str] = mapped_column(Text, primary_key=True)
    name: Mapped[str] = mapped_column(Text, primary_key=True)
    body: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    set_at: Mapped[datetime] = mapped_column(TIMESTAMP(timezone=True), nullable=False, default=utc_now)


class AgentLine(Model):
    """A line recorded once in the agent's voice: its MP3, its length, and when each written word is said."""

    __tablename__ = "agent_lines"

    org: Mapped[str] = mapped_column(ForeignKey("orgs.id", ondelete="CASCADE"), primary_key=True)
    env: Mapped[Env] = mapped_column(StringEnum(Env), primary_key=True)
    agent: Mapped[str] = mapped_column(Text, primary_key=True)
    # A hash of the voice, the lexicon and the text: the same line asked again is this row.
    id: Mapped[str] = mapped_column(Text, primary_key=True)
    text: Mapped[str] = mapped_column(Text, nullable=False)
    voice: Mapped[str] = mapped_column(Text, nullable=False)
    audio: Mapped[bytes] = mapped_column(LargeBinary, nullable=False)
    duration_ms: Mapped[int] = mapped_column(Integer, nullable=False)
    words: Mapped[list[Any]] = mapped_column(JSONB, nullable=False)
    # Whether the voice timed the words or they were spread over the line by their length.
    timed: Mapped[bool] = mapped_column(Boolean, nullable=False)
    recorded_at: Mapped[datetime] = mapped_column(TIMESTAMP(timezone=True), nullable=False, default=utc_now)

    __table_args__ = (Index("agent_lines_by_id", "id"),)


class AgentWidget(Model):
    """Title, tagline, greeting, accent, autostart and theme, per agent and env."""

    __tablename__ = "agent_widgets"

    org: Mapped[str] = mapped_column(ForeignKey("orgs.id", ondelete="CASCADE"), primary_key=True)
    env: Mapped[Env] = mapped_column(StringEnum(Env), primary_key=True)
    agent: Mapped[str] = mapped_column(Text, primary_key=True)
    title: Mapped[str | None] = mapped_column(Text)
    tagline: Mapped[str | None] = mapped_column(Text)
    greeting: Mapped[str | None] = mapped_column(Text)
    accent: Mapped[str | None] = mapped_column(Text)
    autostart: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    theme: Mapped[str | None] = mapped_column(Text)
    set_at: Mapped[datetime] = mapped_column(TIMESTAMP(timezone=True), nullable=False, default=utc_now)


class HoldAudio(Model):
    """The runtime's melody, off, or a custom Ogg Opus clip with its hash, length and name; and how long it waits."""

    __tablename__ = "hold_audio"

    org: Mapped[str] = mapped_column(Text, primary_key=True)
    env: Mapped[Env] = mapped_column(StringEnum(Env), primary_key=True)
    agent: Mapped[str] = mapped_column(Text, primary_key=True)
    played: Mapped[HoldPlayed] = mapped_column(StringEnum(HoldPlayed), nullable=False)
    audio: Mapped[bytes | None] = mapped_column(LargeBinary)
    sha256: Mapped[str | None] = mapped_column(Text)
    seconds: Mapped[float | None] = mapped_column(REAL)
    name: Mapped[str | None] = mapped_column(Text)
    # Seconds of the agent's quiet before the melody starts; null is the runtime's own.
    after_s: Mapped[float | None] = mapped_column(Float)
    set_at: Mapped[datetime] = mapped_column(TIMESTAMP(timezone=True), nullable=False, default=utc_now)


class Lexicon(Model):
    """`said` maps a word to its pronunciation; `heard` lists the keyterms."""

    __tablename__ = "lexicon"

    org: Mapped[str] = mapped_column(ForeignKey("orgs.id", ondelete="CASCADE"), primary_key=True)
    env: Mapped[Env] = mapped_column(StringEnum(Env), primary_key=True)
    holder: Mapped[str] = mapped_column(Text, primary_key=True)
    agent: Mapped[str] = mapped_column(Text, primary_key=True)
    version: Mapped[int] = mapped_column(Integer, primary_key=True)
    said: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False, default=dict)
    heard: Mapped[list[Any]] = mapped_column(JSONB, nullable=False, default=list)
    author: Mapped[str] = mapped_column(Text, nullable=False)
    note: Mapped[str | None] = mapped_column(Text)
    set_at: Mapped[datetime] = mapped_column(TIMESTAMP(timezone=True), nullable=False, default=utc_now)


class Prompt(Model):
    """The words behind the hash a `prompt.changed` entry names, so a call's prompt reads back whole."""

    __tablename__ = "prompts"

    org: Mapped[str] = mapped_column(ForeignKey("orgs.id", ondelete="CASCADE"), primary_key=True)
    hash: Mapped[str] = mapped_column(Text, primary_key=True)
    text: Mapped[str] = mapped_column(Text, nullable=False)
    first_used_at: Mapped[datetime] = mapped_column(TIMESTAMP(timezone=True), nullable=False, default=utc_now)
