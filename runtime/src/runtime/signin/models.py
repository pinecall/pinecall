"""The sign-in tables: one_use_words, org_sso, sso_domain_proofs."""

from datetime import datetime

from sqlalchemy import TIMESTAMP, Boolean, Float, ForeignKey, Index, Integer, LargeBinary, Text
from sqlalchemy.dialects.postgresql import ARRAY
from sqlalchemy.orm import Mapped, mapped_column

from runtime.kit.db import Kept, Model, Sealed, utc_now


# The table is `one_use_words`, from when the vocabulary still said "word"; the model says what it holds.
class OneTimeSecret(Model):
    """A sign-in code, a pairing, a provider's handshake, a sign-up: its hash, its kind, its value sealed."""

    __tablename__ = "one_use_words"
    __table_args__ = (Index("one_use_words_by_end", "expires_at"),)
    __kept__ = Kept(not_exported="a secret that opens once and dies in minutes: no org wrote it")

    word_hash: Mapped[bytes] = mapped_column(LargeBinary, primary_key=True)
    kind: Mapped[str] = mapped_column(Text, nullable=False)
    sealed: Mapped[str] = mapped_column(Sealed, nullable=False)
    expires_at: Mapped[float] = mapped_column(Float, nullable=False)
    attempts: Mapped[int] = mapped_column(Integer, nullable=False, default=0)


class OrgSso(Model):
    """The provider: its issuer, client id, the secret sealed, the domains it admits."""

    __tablename__ = "org_sso"
    __kept__ = Kept(exported=("issuer", "client_id", "domains", "role", "required"))

    org: Mapped[str] = mapped_column(ForeignKey("orgs.id", ondelete="CASCADE"), primary_key=True)
    issuer: Mapped[str] = mapped_column(Text, nullable=False)
    client_id: Mapped[str] = mapped_column(Text, nullable=False)
    ciphertext: Mapped[str] = mapped_column(Sealed, nullable=False)
    domains: Mapped[list[str]] = mapped_column(ARRAY(Text), nullable=False)
    # The role a person signed in by the provider is seated with; NULL is the box's default.
    role: Mapped[str | None] = mapped_column(Text)
    # Whether a password sign-in is refused for this org.
    required: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    set_at: Mapped[datetime] = mapped_column(TIMESTAMP(timezone=True), nullable=False, default=utc_now)


# No foreign key reaches a proof from its org (`sso_domain_proofs.org` is text): until 2026-11 an org
# erased left its proofs behind. The org's erasure calls the verb named here.
class SsoDomainProof(Model):
    """A TXT record `pinecall-verify=<token>` the org publishes to prove a domain is its own."""

    __tablename__ = "sso_domain_proofs"
    __kept__ = Kept(exported=("domain", "verified_at"), erased_by="signin.service.sso.delete_proofs")

    org: Mapped[str] = mapped_column(Text, primary_key=True)
    domain: Mapped[str] = mapped_column(Text, primary_key=True)
    token: Mapped[str] = mapped_column(Text, nullable=False)
    asked_at: Mapped[datetime] = mapped_column(TIMESTAMP(timezone=True), nullable=False, default=utc_now)
    verified_at: Mapped[datetime | None] = mapped_column(TIMESTAMP(timezone=True))
