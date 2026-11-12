"""The accounts tables: orgs, people, members, invitations, api_keys."""

from datetime import datetime
from enum import StrEnum
from typing import Any

from sqlalchemy import TIMESTAMP, Boolean, ForeignKey, Index, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import ARRAY, JSONB
from sqlalchemy.orm import Mapped, mapped_column

from runtime.enums import Env, MemberStatus, Role
from runtime.kit.db import Kept, Model, StringEnum, utc_now


class InvitationPurpose(StrEnum):
    """What a mailed link does."""

    invite = "invite"
    reset = "reset"


# The box's own org: what a runner's key is minted in, and what an operator's verb that names no org acts on.
BOX_ORG = "default"


class Org(Model):
    """An organisation: immutable id, editable slug, display name, and whether its calls are judged."""

    __tablename__ = "orgs"
    __kept__ = Kept(exported=("id", "slug", "name", "created_at", "judging", "judge_model"))

    id: Mapped[str] = mapped_column(Text, primary_key=True)
    slug: Mapped[str] = mapped_column(Text, nullable=False, unique=True)
    name: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(TIMESTAMP(timezone=True), nullable=False, default=utc_now)
    # NULL and True both judge: judging is what an org turns off.
    judging: Mapped[bool | None]
    # The model its calls are judged on (a wire ModelConfig); NULL is the platform's.
    judge_model: Mapped[dict[str, Any] | None] = mapped_column(JSONB)

    @property
    def is_judged(self) -> bool:
        """Whether the org's calls meet the judges at hang-up."""
        return self.judging is not False


# Until 2026-11 a person had no row: they were an address repeated on one member row per org, and their
# one password was "the newest any of their rows holds". Every rule about who may set whose password was
# a special case sewn on top, and one path forgot it: an admin of any org could sign in as a member of
# another (2026-11-11). The password, the proof of the mailbox and running the box are the person's, here.
class Person(Model):
    """A person on the box: one address, one password, and whether the address was proven theirs, in whatever orgs."""

    __tablename__ = "people"
    __kept__ = Kept(
        not_exported="a person is the box's, not one org's: an org's export carries its members, with their addresses",
        erased_by="accounts.service.people.delete_orphans",
    )

    id: Mapped[str] = mapped_column(Text, primary_key=True)
    email: Mapped[str] = mapped_column(Text, nullable=False, unique=True)
    password_hash: Mapped[str | None] = mapped_column(Text)
    verified_at: Mapped[datetime | None] = mapped_column(TIMESTAMP(timezone=True))
    # The box's operator: their key also opens /v1/ops/*, from whatever org they signed in to.
    operator: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    created_at: Mapped[datetime] = mapped_column(TIMESTAMP(timezone=True), nullable=False, default=utc_now)

    @property
    def verified(self) -> bool:
        """Whether the address was proven theirs."""
        return self.verified_at is not None


class Member(Model):
    """A person's seat in one org: their role, their agents, their status, the phone they test from."""

    __tablename__ = "members"
    __table_args__ = (
        UniqueConstraint("org", "email"),
        # The operators, few among the members, found without a scan.
        Index("members_operators", "id", postgresql_where="operator"),
        # A phone is one person's on the whole box: a ring from it is looked up here.
        Index("members_by_test_phone", "test_phone", unique=True, postgresql_where="test_phone IS NOT NULL"),
        # A person's seats across orgs, read at every sign-in.
        Index("members_by_person", "person"),
    )
    __kept__ = Kept(
        exported=("id", "email", "name", "role", "agents", "status", "production", "test_phone", "test_agent")
    )

    id: Mapped[str] = mapped_column(Text, primary_key=True)
    org: Mapped[str] = mapped_column(ForeignKey("orgs.id", ondelete="CASCADE"), nullable=False)
    # Whose seat this is. Nullable in the table until the cutover's backfill has filled every row; this
    # package writes it on every row it makes and reads no member without one.
    person: Mapped[str | None] = mapped_column(ForeignKey("people.id"))
    # The person's address, kept on the seat too: one seat per address in an org.
    email: Mapped[str] = mapped_column(Text, nullable=False)
    name: Mapped[str] = mapped_column(Text, nullable=False)
    role: Mapped[Role] = mapped_column(StringEnum(Role), nullable=False)
    # Empty means every agent of the org.
    agents: Mapped[list[str]] = mapped_column(ARRAY(Text), nullable=False, default=list)
    status: Mapped[MemberStatus] = mapped_column(StringEnum(MemberStatus), nullable=False)
    created_at: Mapped[datetime] = mapped_column(TIMESTAMP(timezone=True), nullable=False, default=utc_now)
    # Granted by an admin, checked per request.
    production: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    # The phone this person tests from, E.164: a call from it to the box's test line, or to one of
    # the org's production numbers, reaches their sandbox copy. The agent it reaches, or null for
    # the one agent the org holds.
    test_phone: Mapped[str | None] = mapped_column(Text)
    test_agent: Mapped[str | None] = mapped_column(Text)
    # The three columns the person's row took over (`people.password_hash`, `verified_at`, `operator`).
    # Declared because the table still has them and the previous runtime reads them until the cutover;
    # nothing in this package reads or writes them, and a revision after the cutover drops them.
    password_hash: Mapped[str | None] = mapped_column(Text)
    operator: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    verified_at: Mapped[datetime | None] = mapped_column(TIMESTAMP(timezone=True))

    @property
    def opens_production(self) -> bool:
        """Whether this member may act in production; admins always may."""
        return self.role is Role.admin or self.production


class Invitation(Model):
    """A link's token (hashed), whom it seats, its purpose, and whether it was spent."""

    __tablename__ = "invitations"
    __kept__ = Kept(not_exported="a link's fingerprint, which opens once and dies in a week")

    token_hash: Mapped[str] = mapped_column(Text, primary_key=True)
    member: Mapped[str] = mapped_column(ForeignKey("members.id", ondelete="CASCADE"), nullable=False)
    expires_at: Mapped[datetime] = mapped_column(TIMESTAMP(timezone=True), nullable=False)
    spent_at: Mapped[datetime | None] = mapped_column(TIMESTAMP(timezone=True))
    created_at: Mapped[datetime] = mapped_column(TIMESTAMP(timezone=True), nullable=False, default=utc_now)
    # The link reached the person through their own mailbox alone, or the box's operator handed it and
    # vouches for the address: opening it proves the address is theirs.
    vouched: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    purpose: Mapped[InvitationPurpose] = mapped_column(
        StringEnum(InvitationPurpose), nullable=False, default=InvitationPurpose.invite
    )


class ApiKey(Model):
    """A key as the database keeps it: never the secret, only its sha256."""

    __tablename__ = "api_keys"
    __table_args__ = (Index("api_keys_parent", "parent", postgresql_where="parent IS NOT NULL"),)
    __kept__ = Kept(
        not_exported="a key's fingerprint and what it opened: no secret, and nothing the org wrote",
        erased_by="accounts.service.keys.delete_keys",
    )

    id: Mapped[str] = mapped_column(Text, primary_key=True)
    hash: Mapped[str] = mapped_column(Text, nullable=False, unique=True)
    org: Mapped[str] = mapped_column(Text, nullable=False)
    label: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(TIMESTAMP(timezone=True), nullable=False, default=utc_now)
    revoked_at: Mapped[datetime | None] = mapped_column(TIMESTAMP(timezone=True))
    env: Mapped[Env] = mapped_column(StringEnum(Env), nullable=False)
    scopes: Mapped[list[str]] = mapped_column(ARRAY(Text), nullable=False)
    # The member the key was minted for; NULL on a server's token.
    subject: Mapped[str | None] = mapped_column(Text)
    name: Mapped[str | None] = mapped_column(Text)
    created_by: Mapped[str | None] = mapped_column(Text)
    last_used_at: Mapped[datetime | None] = mapped_column(TIMESTAMP(timezone=True))
    expires_at: Mapped[datetime | None] = mapped_column(TIMESTAMP(timezone=True))
    # The key this one was copied from: revoked with it.
    parent: Mapped[str | None] = mapped_column(Text)

    @property
    def is_live(self) -> bool:
        """Not revoked and not expired."""
        return self.revoked_at is None and (self.expires_at is None or self.expires_at > utc_now())

    @property
    def is_a_persons(self) -> bool:
        """Minted for a member, as opposed to a server's token."""
        return self.subject is not None
