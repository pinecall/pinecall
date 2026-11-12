"""The compliance tables: org_policy, reads, recording_keys, dial_policy, dials, contact_consents."""

from datetime import datetime

from sqlalchemy import TIMESTAMP, BigInteger, Boolean, ForeignKey, Identity, Index, Integer, SmallInteger, Text
from sqlalchemy.orm import Mapped, mapped_column

from runtime.enums import ConsentKind, Env, ReadKind
from runtime.kit.db import Kept, Model, Sealed, StringEnum, descending, utc_now


class OrgPolicy(Model):
    """How long calls are kept, when and how often a number may be rung, what a call says first."""

    __tablename__ = "org_policy"
    __kept__ = Kept(
        exported=(
            "retention_days",
            "calling_from",
            "calling_until",
            "per_number_day",
            "consent_everywhere",
            "disclosure",
            "recording_notice",
            "set_by",
            "set_at",
        )
    )

    org: Mapped[str] = mapped_column(ForeignKey("orgs.id", ondelete="CASCADE"), primary_key=True)
    # NULL keeps calls until the org erases them.
    retention_days: Mapped[int | None] = mapped_column(Integer)
    set_by: Mapped[str] = mapped_column(Text, nullable=False)
    set_at: Mapped[datetime] = mapped_column(TIMESTAMP(timezone=True), nullable=False, default=utc_now)
    calling_from: Mapped[int | None] = mapped_column(SmallInteger)
    calling_until: Mapped[int | None] = mapped_column(SmallInteger)
    per_number_day: Mapped[int | None] = mapped_column(Integer)
    consent_everywhere: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    # NULL is the platform's sentence, '' is none.
    disclosure: Mapped[str | None] = mapped_column(Text)
    recording_notice: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)


# `subject` is a call, a number, an agent or the org itself, as text: the row of a read stays when what
# was read is erased, because who read it is the question an audit asks after.
class Read(Model):
    """One row per reader, subject and kind an hour; names the subject, never what it said."""

    __tablename__ = "reads"
    __table_args__ = (
        Index("reads_by_org", "org", descending("at")),
        Index("reads_by_subject", "org", "subject", descending("at")),
    )
    __kept__ = Kept(
        not_exported="the box's audit of who read the org's data: the org reads it at /v1/org/reads",
        outlives=(
            "the audit says who read what, and stays when what was read is erased: it names its subject "
            "and holds nothing of it; the rows go with their org"
        ),
    )

    id: Mapped[int] = mapped_column(BigInteger, Identity(always=True), primary_key=True)
    org: Mapped[str] = mapped_column(ForeignKey("orgs.id", ondelete="CASCADE"), nullable=False)
    env: Mapped[Env | None] = mapped_column(StringEnum(Env))
    subject: Mapped[str] = mapped_column(Text, nullable=False)
    what: Mapped[ReadKind] = mapped_column(StringEnum(ReadKind), nullable=False)
    reader: Mapped[str] = mapped_column(Text, nullable=False)
    at: Mapped[datetime] = mapped_column(TIMESTAMP(timezone=True), nullable=False, default=utc_now)


# No foreign key reaches a key from its org (`org` is text): the row goes with its call, and an org
# erased whole calls `delete_recording_keys`.
class RecordingKey(Model):
    """What opens the call's audio; a backup that outlives the erasure no longer opens."""

    __tablename__ = "recording_keys"
    __kept__ = Kept(
        call="call",
        not_exported="a key the vault seals: an export carries the recording it opens, never the key",
        erased_by="compliance.service.recordings.delete_recording_keys",
    )

    call: Mapped[str] = mapped_column(Text, primary_key=True)
    org: Mapped[str] = mapped_column(Text, nullable=False)
    sealed: Mapped[str] = mapped_column(Sealed, nullable=False)
    made_at: Mapped[datetime] = mapped_column(TIMESTAMP(timezone=True), nullable=False, default=utc_now)


class DialPolicy(Model):
    """Strangers allowed or not, the pace per minute and per day, the longest leg."""

    __tablename__ = "dial_policy"
    __kept__ = Kept(not_exported="set by the box's operator, not by the org")

    org: Mapped[str] = mapped_column(ForeignKey("orgs.id", ondelete="CASCADE"), primary_key=True)
    dial_anywhere: Mapped[bool | None] = mapped_column(Boolean)
    per_minute: Mapped[int | None] = mapped_column(Integer)
    per_day: Mapped[int | None] = mapped_column(Integer)
    max_duration_s: Mapped[int | None] = mapped_column(Integer)
    set_at: Mapped[datetime] = mapped_column(TIMESTAMP(timezone=True), nullable=False, default=utc_now)


class Dial(Model):
    """Who asked to dial whom, shown as what, and why it was refused when it was."""

    __tablename__ = "dials"
    __table_args__ = (Index("dials_by_org", "org", descending("at")),)
    __kept__ = Kept(
        not_exported="the box's ledger of what it was asked to dial: nothing the org wrote",
        outlives=(
            "the ledger answers a carrier's traceback after the call, the agent or the org is gone: "
            "`forget_dials` takes a row once it is two years old, and nothing takes it before"
        ),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    org: Mapped[str] = mapped_column(Text, nullable=False)
    env: Mapped[Env] = mapped_column(StringEnum(Env), nullable=False)
    agent: Mapped[str] = mapped_column(Text, nullable=False)
    call: Mapped[str | None] = mapped_column(Text)
    dialled: Mapped[str] = mapped_column(Text, nullable=False)
    shown: Mapped[str | None] = mapped_column(Text)
    asked_by: Mapped[str] = mapped_column(Text, nullable=False)
    refused: Mapped[str | None] = mapped_column(Text)
    at: Mapped[datetime] = mapped_column(TIMESTAMP(timezone=True), nullable=False, default=utc_now)


class ContactConsent(Model):
    """Outlives an erasure of the contact: an opt-out has to survive the person's data."""

    __tablename__ = "contact_consents"
    __table_args__ = (
        Index("contact_consents_by_number", "org", "env", "number", descending("given_at"), descending("id")),
    )
    __kept__ = Kept(
        exported=("number", "kind", "source", "text", "evidence", "given_by", "call", "given_at"),
        exported_as="consent",
        renamed=(("kind", "consent"),),
        outlives=(
            "an opt-out has to survive the erasure of the call it was said on and of the person's data, "
            "or the next call would ring them; the rows go with their org"
        ),
    )

    id: Mapped[int] = mapped_column(BigInteger, Identity(always=True), primary_key=True)
    org: Mapped[str] = mapped_column(ForeignKey("orgs.id", ondelete="CASCADE"), nullable=False)
    env: Mapped[Env] = mapped_column(StringEnum(Env), nullable=False)
    number: Mapped[str] = mapped_column(Text, nullable=False)
    kind: Mapped[ConsentKind] = mapped_column(StringEnum(ConsentKind), nullable=False)
    source: Mapped[str] = mapped_column(Text, nullable=False)
    text: Mapped[str | None] = mapped_column(Text)
    evidence: Mapped[str | None] = mapped_column(Text)
    given_by: Mapped[str] = mapped_column(Text, nullable=False)
    call: Mapped[str | None] = mapped_column(Text)
    given_at: Mapped[datetime] = mapped_column(TIMESTAMP(timezone=True), nullable=False, default=utc_now)
