"""The accounts tables, one class each: api_keys, invitations, members, one_use_words, orgs, org_mail and more."""

from datetime import datetime
from typing import Any

from sqlalchemy import TIMESTAMP, Boolean, Float, ForeignKey, Index, Integer, LargeBinary, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import ARRAY, JSONB
from sqlalchemy.orm import Mapped, mapped_column

from pinecall_runtime.enums import Env, InvitationPurpose, MemberStatus, Role
from pinecall_runtime.kit.db import Model, StringEnum, utc_now


class ApiKey(Model):
    """A key as the database keeps it: never the secret, only its sha256."""

    __tablename__ = "api_keys"
    __table_args__ = (Index("api_keys_parent", "parent", postgresql_where="parent IS NOT NULL"),)

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


class Invitation(Model):
    """A link's token (hashed), whom it seats, its purpose, and whether it was spent."""

    __tablename__ = "invitations"

    token_hash: Mapped[str] = mapped_column(Text, primary_key=True)
    member: Mapped[str] = mapped_column(ForeignKey("members.id", ondelete="CASCADE"), nullable=False)
    expires_at: Mapped[datetime] = mapped_column(TIMESTAMP(timezone=True), nullable=False)
    spent_at: Mapped[datetime | None] = mapped_column(TIMESTAMP(timezone=True))
    created_at: Mapped[datetime] = mapped_column(TIMESTAMP(timezone=True), nullable=False, default=utc_now)
    # Sent by an operator or an admin who vouches for the address: it counts as verified.
    vouched: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    purpose: Mapped[InvitationPurpose] = mapped_column(
        StringEnum(InvitationPurpose), nullable=False, default=InvitationPurpose.invite
    )


class Member(Model):
    """A person in one org, with their role, agents and status."""

    __tablename__ = "members"
    __table_args__ = (
        UniqueConstraint("org", "email"),
        # The operators, few among the members, found without a scan.
        Index("members_operators", "id", postgresql_where="operator"),
    )

    id: Mapped[str] = mapped_column(Text, primary_key=True)
    org: Mapped[str] = mapped_column(ForeignKey("orgs.id", ondelete="CASCADE"), nullable=False)
    email: Mapped[str] = mapped_column(Text, nullable=False)
    name: Mapped[str] = mapped_column(Text, nullable=False)
    role: Mapped[Role] = mapped_column(StringEnum(Role), nullable=False)
    # Empty means every agent of the org.
    agents: Mapped[list[str]] = mapped_column(ARRAY(Text), nullable=False, default=list)
    status: Mapped[MemberStatus] = mapped_column(StringEnum(MemberStatus), nullable=False)
    password_hash: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(TIMESTAMP(timezone=True), nullable=False, default=utc_now)
    # The box's operator: their key also opens /v1/ops/*.
    operator: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    # Granted by an admin, checked per request.
    production: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    verified_at: Mapped[datetime | None] = mapped_column(TIMESTAMP(timezone=True))

    @property
    def opens_production(self) -> bool:
        """Whether this member may act in production; admins always may."""
        return self.role is Role.admin or self.production

    @property
    def verified(self) -> bool:
        """Whether the email was proven theirs."""
        return self.verified_at is not None


class OneUseWord(Model):
    """A sign-in code, a pairing, a provider handshake: its hash, its kind, its value sealed."""

    __tablename__ = "one_use_words"
    __table_args__ = (Index("one_use_words_by_end", "expires_at"),)

    word_hash: Mapped[bytes] = mapped_column(LargeBinary, primary_key=True)
    kind: Mapped[str] = mapped_column(Text, nullable=False)
    sealed: Mapped[str] = mapped_column(Text, nullable=False)
    expires_at: Mapped[float] = mapped_column(Float, nullable=False)
    attempts: Mapped[int] = mapped_column(Integer, nullable=False, default=0)


DEFAULT_ORG = "default"


class Org(Model):
    """An organisation: immutable id, editable slug, display name, and whether its calls are judged."""

    __tablename__ = "orgs"

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


class OrgMail(Model):
    """SMTP for the org: host, port, security, the username, the password sealed, the sender."""

    __tablename__ = "org_mail"

    org: Mapped[str] = mapped_column(ForeignKey("orgs.id", ondelete="CASCADE"), primary_key=True)
    host: Mapped[str] = mapped_column(Text, nullable=False)
    port: Mapped[int] = mapped_column(Integer, nullable=False)
    security: Mapped[str] = mapped_column(Text, nullable=False)
    username: Mapped[str] = mapped_column(Text, nullable=False)
    ciphertext: Mapped[str] = mapped_column(Text, nullable=False)
    sender: Mapped[str] = mapped_column(Text, nullable=False)
    verified_at: Mapped[datetime | None] = mapped_column(TIMESTAMP(timezone=True))
    last_error: Mapped[str | None] = mapped_column(Text)
    set_at: Mapped[datetime] = mapped_column(TIMESTAMP(timezone=True), nullable=False, default=utc_now)


class OrgSso(Model):
    """The provider: its issuer, client id, the secret sealed, the domains it admits."""

    __tablename__ = "org_sso"

    org: Mapped[str] = mapped_column(ForeignKey("orgs.id", ondelete="CASCADE"), primary_key=True)
    issuer: Mapped[str] = mapped_column(Text, nullable=False)
    client_id: Mapped[str] = mapped_column(Text, nullable=False)
    ciphertext: Mapped[str] = mapped_column(Text, nullable=False)
    domains: Mapped[list[str]] = mapped_column(ARRAY(Text), nullable=False)
    # The role a person signed in by the provider is seated with; NULL is the box's default.
    role: Mapped[str | None] = mapped_column(Text)
    # Whether a password sign-in is refused for this org.
    required: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    set_at: Mapped[datetime] = mapped_column(TIMESTAMP(timezone=True), nullable=False, default=utc_now)


class SsoDomainProof(Model):
    """A TXT record `pinecall-verify=<token>` the org publishes to prove a domain is its own."""

    __tablename__ = "sso_domain_proofs"

    org: Mapped[str] = mapped_column(Text, primary_key=True)
    domain: Mapped[str] = mapped_column(Text, primary_key=True)
    token: Mapped[str] = mapped_column(Text, nullable=False)
    asked_at: Mapped[datetime] = mapped_column(TIMESTAMP(timezone=True), nullable=False, default=utc_now)
    verified_at: Mapped[datetime | None] = mapped_column(TIMESTAMP(timezone=True))


class SignInAttempt(Model):
    """A name tried a sign-in or asked a voice sample at this moment; rows past the window go."""

    __tablename__ = "knocks"
    __table_args__ = (Index("knocks_by_name", "name", "at"), Index("knocks_by_age", "at"))

    # The table has no primary key: SQLAlchemy needs one to map, so both columns stand as it.
    name: Mapped[str] = mapped_column(Text, primary_key=True)
    at: Mapped[float] = mapped_column(Float, primary_key=True)


class Token(Model):
    """What a token was minted for, so the call that opens with it opens there and once."""

    __tablename__ = "tokens"

    call: Mapped[str] = mapped_column(Text, primary_key=True)
    org: Mapped[str] = mapped_column(Text, nullable=False)
    agent: Mapped[str] = mapped_column(Text, nullable=False)
    scope: Mapped[str] = mapped_column(Text, nullable=False)
    minted_at: Mapped[datetime] = mapped_column(TIMESTAMP(timezone=True), nullable=False, default=utc_now)
    expires_at: Mapped[datetime] = mapped_column(TIMESTAMP(timezone=True), nullable=False)
    spent_at: Mapped[datetime | None] = mapped_column(TIMESTAMP(timezone=True))
    # None on a token minted before the env was kept: held to its org and agent alone.
    env: Mapped[Env | None] = mapped_column(StringEnum(Env))
