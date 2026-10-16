"""The telephony tables: carriers, carrier_networks, contact_consents, dials, dial_policy."""

from datetime import datetime

from sqlalchemy import (
    TIMESTAMP,
    BigInteger,
    Boolean,
    ForeignKey,
    Identity,
    Index,
    Integer,
    Text,
    UniqueConstraint,
    text,
)
from sqlalchemy.dialects.postgresql import CIDR
from sqlalchemy.orm import Mapped, mapped_column

from pinecall_runtime.enums import CarrierKind, ConsentKind, Env, NetworkState
from pinecall_runtime.kit.db import Model, StringEnum, utc_now


class Carrier(Model):
    """One row per account, keyed by the account's own id; the credentials in `ciphertext`."""

    __tablename__ = "carriers"

    org: Mapped[str] = mapped_column(ForeignKey("orgs.id", ondelete="CASCADE"), primary_key=True)
    account: Mapped[str] = mapped_column(Text, primary_key=True)
    kind: Mapped[CarrierKind] = mapped_column(StringEnum(CarrierKind), nullable=False)
    ciphertext: Mapped[str] = mapped_column(Text, nullable=False)
    label: Mapped[str] = mapped_column(Text, nullable=False, default="")
    set_at: Mapped[datetime] = mapped_column(TIMESTAMP(timezone=True), nullable=False, default=utc_now)


class CarrierNetwork(Model):
    """Nothing is admitted until approved; the fence opens to the approved rows alone."""

    __tablename__ = "carrier_networks"
    __table_args__ = (
        UniqueConstraint("org", "source", "network"),
        Index("carrier_networks_by_state", "state", "asked_at"),
    )

    id: Mapped[int] = mapped_column(BigInteger, Identity(always=True), primary_key=True)
    org: Mapped[str] = mapped_column(ForeignKey("orgs.id", ondelete="CASCADE"), nullable=False)
    # A SIP peer's username, or the number hooked with networks of its own.
    source: Mapped[str] = mapped_column(Text, nullable=False)
    network: Mapped[str] = mapped_column(CIDR, nullable=False)
    state: Mapped[NetworkState] = mapped_column(StringEnum(NetworkState), nullable=False, default=NetworkState.waiting)
    asked_at: Mapped[datetime] = mapped_column(TIMESTAMP(timezone=True), nullable=False, default=utc_now)
    decided_by: Mapped[str | None] = mapped_column(Text)
    decided_at: Mapped[datetime | None] = mapped_column(TIMESTAMP(timezone=True))


class ContactConsent(Model):
    """Outlives an erasure of the contact: an opt-out has to survive the person's data."""

    __tablename__ = "contact_consents"
    __table_args__ = (
        Index("contact_consents_by_number", "org", "env", "number", text("given_at DESC"), text("id DESC")),
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


class Dial(Model):
    """Who asked to dial whom, shown as what, and why it was refused when it was."""

    __tablename__ = "dials"
    __table_args__ = (Index("dials_by_org", "org", text("at DESC")),)

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


class DialPolicy(Model):
    """Strangers allowed or not, the pace per minute and per day, the longest leg."""

    __tablename__ = "dial_policy"

    org: Mapped[str] = mapped_column(ForeignKey("orgs.id", ondelete="CASCADE"), primary_key=True)
    dial_anywhere: Mapped[bool | None] = mapped_column(Boolean)
    per_minute: Mapped[int | None] = mapped_column(Integer)
    per_day: Mapped[int | None] = mapped_column(Integer)
    max_duration_s: Mapped[int | None] = mapped_column(Integer)
    set_at: Mapped[datetime] = mapped_column(TIMESTAMP(timezone=True), nullable=False, default=utc_now)
