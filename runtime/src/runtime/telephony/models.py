"""The telephony tables: carriers, carrier_networks, routes, email_inboxes, email_layouts; and their words."""

from datetime import datetime
from enum import StrEnum

from sqlalchemy import (
    TIMESTAMP,
    BigInteger,
    Boolean,
    ForeignKey,
    ForeignKeyConstraint,
    Identity,
    Index,
    Text,
    UniqueConstraint,
    false,
)
from sqlalchemy.dialects.postgresql import ARRAY, CIDR
from sqlalchemy.orm import Mapped, mapped_column

from runtime.enums import Channel, Env, RouteOrigin
from runtime.kit.db import Kept, Model, Sealed, StringEnum, utc_now


class CarrierKind(StrEnum):
    """What an org's carrier account is."""

    twilio = "twilio"
    sip = "sip"
    whatsapp = "whatsapp"
    email = "email"
    # A Facebook Page at Meta: its Messenger, and the Instagram account linked to it.
    messenger = "messenger"


class NetworkState(StrEnum):
    """Whether the operator admitted a network an org asked for."""

    waiting = "waiting"
    approved = "approved"
    refused = "refused"


class Carrier(Model):
    """One row per account, keyed by the account's own id; the credentials in `ciphertext`."""

    __tablename__ = "carriers"
    __kept__ = Kept(
        not_exported=(
            "an account's credentials at its carrier, sealed: an export names the account on each number that "
            "lives in it, never its secret"
        )
    )

    org: Mapped[str] = mapped_column(ForeignKey("orgs.id", ondelete="CASCADE"), primary_key=True)
    account: Mapped[str] = mapped_column(Text, primary_key=True)
    kind: Mapped[CarrierKind] = mapped_column(StringEnum(CarrierKind), nullable=False)
    ciphertext: Mapped[str] = mapped_column(Sealed, nullable=False)
    label: Mapped[str] = mapped_column(Text, nullable=False, default="")
    set_at: Mapped[datetime] = mapped_column(TIMESTAMP(timezone=True), nullable=False, default=utc_now)


class CarrierNetwork(Model):
    """Nothing is admitted until approved; the fence opens to the approved rows alone."""

    __tablename__ = "carrier_networks"
    __table_args__ = (
        UniqueConstraint("org", "source", "network"),
        Index("carrier_networks_by_state", "state", "asked_at"),
    )
    __kept__ = Kept(exported=("source", "network", "state", "asked_at", "decided_at"))

    id: Mapped[int] = mapped_column(BigInteger, Identity(always=True), primary_key=True)
    org: Mapped[str] = mapped_column(ForeignKey("orgs.id", ondelete="CASCADE"), nullable=False)
    # A SIP peer's username, or the number hooked with networks of its own.
    source: Mapped[str] = mapped_column(Text, nullable=False)
    network: Mapped[str] = mapped_column(CIDR, nullable=False)
    state: Mapped[NetworkState] = mapped_column(StringEnum(NetworkState), nullable=False, default=NetworkState.waiting)
    asked_at: Mapped[datetime] = mapped_column(TIMESTAMP(timezone=True), nullable=False, default=utc_now)
    decided_by: Mapped[str | None] = mapped_column(Text)
    decided_at: Mapped[datetime | None] = mapped_column(TIMESTAMP(timezone=True))


# The row names its org with no key to it, so nothing cascades: an org or an agent erased lets its
# numbers go through `release_numbers_of`, which takes them off the SFU too.
class Route(Model):
    """A number's row: its agent, channel, env, how it was written and whether it was approved."""

    __tablename__ = "routes"
    __table_args__ = (
        ForeignKeyConstraint(["org", "account"], ["carriers.org", "carriers.account"], ondelete="SET NULL (account)"),
        # A number answers once a channel, across the box. That one org holds a number, whatever its
        # channels, is said where a number is imported.
        Index("routes_number_held_once_a_channel", "number", "channel", unique=True),
    )
    __kept__ = Kept(
        agent="agent",
        exported=("number", "agent", "channel", "managed", "account", "networks", "origin", "via", "added_at"),
        erased_by="telephony.service.numbers.release_numbers_of",
    )

    org: Mapped[str] = mapped_column(Text, primary_key=True)
    number: Mapped[str] = mapped_column(Text, primary_key=True)
    agent: Mapped[str] = mapped_column(Text, nullable=False)
    channel: Mapped[Channel] = mapped_column(StringEnum(Channel), primary_key=True)
    added_at: Mapped[datetime] = mapped_column(TIMESTAMP(timezone=True), nullable=False, default=utc_now)
    env: Mapped[Env] = mapped_column(StringEnum(Env), nullable=False)
    # Bought on the box's carrier account: counts against the `numbers` quota.
    managed: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    # The org's carrier account the number lives in, or NULL.
    account: Mapped[str | None] = mapped_column(Text)
    # A hooked number's own networks, which the operator approves.
    networks: Mapped[list[str]] = mapped_column(ARRAY(Text), nullable=False, default=list)
    origin: Mapped[RouteOrigin] = mapped_column(StringEnum(RouteOrigin), nullable=False, default=RouteOrigin.typed)
    # The catalog carrier a number with no account comes through.
    via: Mapped[str | None] = mapped_column(Text)
    last_call_at: Mapped[datetime | None] = mapped_column(TIMESTAMP(timezone=True))
    approved_at: Mapped[datetime | None] = mapped_column(TIMESTAMP(timezone=True), default=utc_now)
    approved_by: Mapped[str | None] = mapped_column(Text)

    @property
    def approved(self) -> bool:
        """Whether a call to the number may open."""
        return self.approved_at is not None


# A mailbox's inbox is read by one gateway at a time: the one whose lease runs. Where the last pass
# stopped is the IMAP UID of the newest message read, good while the mailbox keeps its UIDVALIDITY.
class EmailInbox(Model):
    """Where the reading of an email account's inbox stands: the newest message read, and who reads it now."""

    __tablename__ = "email_inboxes"
    __table_args__ = (
        ForeignKeyConstraint(["org", "account"], ["carriers.org", "carriers.account"], ondelete="CASCADE"),
    )
    __kept__ = Kept(not_exported="where the box's reading of a mailbox stands, which the mailbox itself says again")

    org: Mapped[str] = mapped_column(Text, primary_key=True)
    account: Mapped[str] = mapped_column(Text, primary_key=True)
    uid_validity: Mapped[int | None] = mapped_column(BigInteger)
    last_uid: Mapped[int | None] = mapped_column(BigInteger)
    leased_by: Mapped[str | None] = mapped_column(Text)
    leased_until: Mapped[datetime | None] = mapped_column(TIMESTAMP(timezone=True))
    read_at: Mapped[datetime | None] = mapped_column(TIMESTAMP(timezone=True))
    last_error: Mapped[str | None] = mapped_column(Text)


class EmailLayout(Model):
    """How the org's agents' emails are set: in its HTML, where `{{content}}` is the reply, or as text alone."""

    __tablename__ = "email_layouts"
    __kept__ = Kept(exported=("html", "text_only", "set_at"))

    org: Mapped[str] = mapped_column(ForeignKey("orgs.id", ondelete="CASCADE"), primary_key=True)
    # Empty for an org that sends text alone.
    html: Mapped[str] = mapped_column(Text, nullable=False)
    text_only: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False, server_default=false())
    set_by: Mapped[str | None] = mapped_column(Text)
    set_at: Mapped[datetime] = mapped_column(TIMESTAMP(timezone=True), nullable=False, default=utc_now)
