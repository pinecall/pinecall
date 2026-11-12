"""The agents tables: canaries, config, declarations, documents, lines, widgets, hold_audio, lexicon."""

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
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from runtime.enums import Env, HoldPlayed
from runtime.kit.db import Kept, Model, StringEnum, descending, utc_now

# Every table here names its agent in `agent`, and each says so in its `Kept`: an agent erased is erased
# from all eight. Until 2026-11 the list of tables an erasure walked was typed beside it, and the three
# tables made after that list (declarations, documents, lines) outlived their agent: a new agent of the
# same slug read the old class's fixed settings, and its lines were served for a year.


class AgentCanary(Model):
    """Which version takes `share` % of the scope's calls; NULL version is the canary cleared."""

    __tablename__ = "agent_canaries"
    __table_args__ = (
        Index("agent_canaries_standing", "org", "env", "holder", "agent", descending("set_at"), descending("id")),
    )
    __kept__ = Kept(
        agent="agent",
        exported=("agent", "holder", "version", "share", "author", "note", "set_at"),
        exported_as="canary",
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


# The table keeps the name it was made with: its rows are an agent's settings, one per version.
class AgentConfig(Model):
    """The settings an org set on an agent, versioned per (org, env, holder, agent)."""

    __tablename__ = "agent_config"
    __kept__ = Kept(agent="agent", exported=("agent", "holder", "version", "config", "author", "note", "set_at"))

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
    __kept__ = Kept(
        agent="agent",
        not_exported="what the org's own class declares, kept from its app's last connection: the class is its code",
    )

    org: Mapped[str] = mapped_column(ForeignKey("orgs.id", ondelete="CASCADE"), primary_key=True)
    env: Mapped[Env] = mapped_column(StringEnum(Env), primary_key=True)
    holder: Mapped[str] = mapped_column(Text, primary_key=True)
    agent: Mapped[str] = mapped_column(Text, primary_key=True)
    # The wire's AgentConfig as the app sent it, every configure of one socket merged into the first. The
    # columns keep the names the table was made with (`declared`, `declared_at`).
    declaration: Mapped[dict[str, Any]] = mapped_column("declared", JSONB, nullable=False)
    sdk: Mapped[str | None] = mapped_column(Text)
    set_at: Mapped[datetime] = mapped_column("declared_at", TIMESTAMP(timezone=True), nullable=False, default=utc_now)


class AgentDocument(Model):
    """A JSON document an agent's app publishes under a name, read by any page with no key."""

    __tablename__ = "agent_documents"
    __kept__ = Kept(agent="agent", exported=("agent", "name", "body", "set_at"))

    org: Mapped[str] = mapped_column(ForeignKey("orgs.id", ondelete="CASCADE"), primary_key=True)
    env: Mapped[Env] = mapped_column(StringEnum(Env), primary_key=True)
    agent: Mapped[str] = mapped_column(Text, primary_key=True)
    name: Mapped[str] = mapped_column(Text, primary_key=True)
    body: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    set_at: Mapped[datetime] = mapped_column(TIMESTAMP(timezone=True), nullable=False, default=utc_now)


# `audio` is read only where the MP3 itself is answered: a list of lines answers ids and URLs, and until
# 2026-11 it loaded up to 64 MP3s to do it.
class AgentLine(Model):
    """A line recorded once in the agent's voice: its MP3, its length, and when each written word is said."""

    __tablename__ = "agent_lines"
    __kept__ = Kept(
        agent="agent",
        not_exported="audio recorded from the texts the org's app sends: asked for again, a line is recorded again",
    )

    org: Mapped[str] = mapped_column(ForeignKey("orgs.id", ondelete="CASCADE"), primary_key=True)
    env: Mapped[Env] = mapped_column(StringEnum(Env), primary_key=True)
    agent: Mapped[str] = mapped_column(Text, primary_key=True)
    # A hash of the voice, the lexicon and the text: the same line asked again is this row.
    id: Mapped[str] = mapped_column(Text, primary_key=True)
    text: Mapped[str] = mapped_column(Text, nullable=False)
    voice: Mapped[str] = mapped_column(Text, nullable=False)
    audio: Mapped[bytes] = mapped_column(LargeBinary, nullable=False, deferred=True)
    duration_ms: Mapped[int] = mapped_column(Integer, nullable=False)
    words: Mapped[list[Any]] = mapped_column(JSONB, nullable=False)
    # Whether the voice timed the words or they were spread over the line by their length.
    timed: Mapped[bool] = mapped_column(Boolean, nullable=False)
    recorded_at: Mapped[datetime] = mapped_column(TIMESTAMP(timezone=True), nullable=False, default=utc_now)

    __table_args__ = (Index("agent_lines_by_id", "id"),)


class AgentWidget(Model):
    """Title, tagline, greeting, accent, autostart and theme, per agent and env."""

    __tablename__ = "agent_widgets"
    __kept__ = Kept(
        agent="agent",
        exported=("agent", "title", "tagline", "greeting", "accent", "autostart", "theme", "set_at"),
    )

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


# No foreign key reaches a row from its org (`org` is text): an org erased whole calls `forget_melodies`.
# `audio` is read only where the clip itself is answered: the worker asks what plays before every call,
# and until 2026-11 that read loaded the clip, up to a few megabytes, each time.
class HoldAudio(Model):
    """The runtime's melody, off, or a custom Ogg Opus clip with its hash, length and name; and how long it waits."""

    __tablename__ = "hold_audio"
    __kept__ = Kept(
        agent="agent",
        exported=("agent", "played", "sha256", "source_sha256", "seconds", "name", "after_s", "set_at"),
        erased_by="agents.service.hold_audio.forget_melodies",
    )

    org: Mapped[str] = mapped_column(Text, primary_key=True)
    env: Mapped[Env] = mapped_column(StringEnum(Env), primary_key=True)
    agent: Mapped[str] = mapped_column(Text, primary_key=True)
    played: Mapped[HoldPlayed] = mapped_column(StringEnum(HoldPlayed), nullable=False)
    audio: Mapped[bytes | None] = mapped_column(LargeBinary, deferred=True)
    sha256: Mapped[str | None] = mapped_column(Text)
    # The hash of the file as it was uploaded, before conversion: what a class says it ships.
    source_sha256: Mapped[str | None] = mapped_column(Text)
    seconds: Mapped[float | None] = mapped_column(REAL)
    name: Mapped[str | None] = mapped_column(Text)
    # Seconds of the agent's quiet before the melody starts; null is the runtime's own.
    after_s: Mapped[float | None] = mapped_column(Float)
    set_at: Mapped[datetime] = mapped_column(TIMESTAMP(timezone=True), nullable=False, default=utc_now)


class Lexicon(Model):
    """`said` maps a word to its pronunciation; `heard` lists the keyterms."""

    __tablename__ = "lexicon"
    __kept__ = Kept(agent="agent", exported=("agent", "holder", "version", "said", "heard", "author", "note", "set_at"))

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
