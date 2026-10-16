"""The agents tables: agent_canaries, agent_config, agent_widgets, hold_audio, lexicon, prompts."""

from datetime import datetime
from typing import Any

from sqlalchemy import (
    REAL,
    TIMESTAMP,
    BigInteger,
    Boolean,
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
    """Off, or a custom Ogg Opus clip with its hash, length and name."""

    __tablename__ = "hold_audio"

    org: Mapped[str] = mapped_column(Text, primary_key=True)
    env: Mapped[Env] = mapped_column(StringEnum(Env), primary_key=True)
    agent: Mapped[str] = mapped_column(Text, primary_key=True)
    played: Mapped[HoldPlayed] = mapped_column(StringEnum(HoldPlayed), nullable=False)
    audio: Mapped[bytes | None] = mapped_column(LargeBinary)
    sha256: Mapped[str | None] = mapped_column(Text)
    seconds: Mapped[float | None] = mapped_column(REAL)
    name: Mapped[str | None] = mapped_column(Text)
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
