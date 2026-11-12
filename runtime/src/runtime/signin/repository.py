"""Every statement on the sign-in tables: secrets spent once, an org's identity provider, its domains' proofs."""

from collections.abc import Sequence
from datetime import datetime

from sqlalchemy import delete, select, update

from runtime.kit.repository import Repository
from runtime.signin.models import OneTimeSecret, OrgSso, SsoDomainProof


class OneTimeSecretRepository(Repository[OneTimeSecret]):
    """Secrets spent once, kept by their hash with their value sealed."""

    model = OneTimeSecret

    async def find(self, word_hash: bytes) -> OneTimeSecret | None:
        """By hash, dead or alive."""
        return await self.one_or_none(self.statement().where(OneTimeSecret.word_hash == word_hash))

    async def put(self, word_hash: bytes, kind: str, sealed: str, expires_at: float) -> None:
        """Keep, or replace whole with attempts reset."""
        values = {"word_hash": word_hash, "kind": kind, "sealed": sealed, "expires_at": expires_at, "attempts": 0}
        await self.upsert(values, key=["word_hash"])

    async def spend(self, word_hash: bytes, at: float) -> OneTimeSecret | None:
        """Delete and return the row if alive; of two spenders, one gets it."""
        statement = (
            delete(OneTimeSecret)
            .where(OneTimeSecret.word_hash == word_hash, OneTimeSecret.expires_at > at)
            .returning(OneTimeSecret)
        )
        return (await self.session.execute(statement)).scalar_one_or_none()

    async def fill(self, word_hash: bytes, sealed: str, at: float) -> bool:
        """Change what a living secret holds; False for a dead one."""
        statement = (
            update(OneTimeSecret)
            .where(OneTimeSecret.word_hash == word_hash, OneTimeSecret.expires_at > at)
            .values(sealed=sealed)
            .returning(OneTimeSecret.word_hash)
        )
        return (await self.session.execute(statement)).scalar_one_or_none() is not None

    # Until 2026-11 a guess was read, compared and counted in three transactions: guesses sent together
    # all passed the ceiling before any of them was counted. One statement counts the guess and holds
    # the ceiling, so of any number sent at once only as many as are left get to be compared.
    async def take_attempt(self, word_hash: bytes, at: float, most: int) -> OneTimeSecret | None:
        """Count one guess at a living secret that has any left, and answer its row; None when it has none."""
        statement = (
            update(OneTimeSecret)
            .where(
                OneTimeSecret.word_hash == word_hash,
                OneTimeSecret.expires_at > at,
                OneTimeSecret.attempts < most,
            )
            .values(attempts=OneTimeSecret.attempts + 1)
            .returning(OneTimeSecret)
        )
        return (await self.session.execute(statement)).scalar_one_or_none()

    async def forget(self, word_hash: bytes) -> None:
        """The secret opens nothing from now on."""
        await self.change(delete(OneTimeSecret).where(OneTimeSecret.word_hash == word_hash))

    async def sweep(self, at: float) -> None:
        """Drop every dead secret."""
        await self.change(delete(OneTimeSecret).where(OneTimeSecret.expires_at <= at))


class SsoRepository(Repository[OrgSso]):
    """An org's identity provider and its domain proofs."""

    model = OrgSso

    async def find(self, org: str) -> OrgSso | None:
        """The org's provider row, or None."""
        return await self.one_or_none(self.statement().where(OrgSso.org == org))

    async def is_required(self, org: str) -> bool:
        """Whether the org signs in only with its provider."""
        return await self.exists(self.statement().where(OrgSso.org == org, OrgSso.required))

    async def list_for_domain(self, domain: str) -> Sequence[OrgSso]:
        """The providers that admit a verified domain, oldest first. Read box-wide by the caller."""
        statement = (
            self.statement()
            .join(
                SsoDomainProof,
                (SsoDomainProof.org == OrgSso.org)
                & (SsoDomainProof.domain == domain)
                & SsoDomainProof.verified_at.is_not(None),
            )
            .where(OrgSso.domains.any_() == domain)
            .order_by(OrgSso.set_at, OrgSso.org)
        )
        return await self.all(statement)

    async def list_proofs(self, org: str) -> Sequence[SsoDomainProof]:
        """Every domain's proof, by domain."""
        statement = select(SsoDomainProof).where(SsoDomainProof.org == org).order_by(SsoDomainProof.domain)
        return (await self.session.execute(statement)).scalars().all()

    async def find_proof(self, org: str, domain: str) -> SsoDomainProof | None:
        """One domain's proof, or None."""
        statement = select(SsoDomainProof).where(SsoDomainProof.org == org, SsoDomainProof.domain == domain)
        return (await self.session.execute(statement)).scalar_one_or_none()

    async def add_proof(self, proof: SsoDomainProof) -> SsoDomainProof:
        """Keep a domain's proof, flushed so its token is read back."""
        self.session.add(proof)
        await self.session.flush()
        return proof

    async def verify_proof(self, proof: SsoDomainProof, at: datetime) -> None:
        """The domain's TXT record was seen: the proof stands from now."""
        proof.verified_at = at
        await self.session.flush()

    async def delete_proofs_not_in(self, org: str, domains: Sequence[str]) -> None:
        """Forget the proofs of domains the provider no longer admits."""
        statement = delete(SsoDomainProof).where(SsoDomainProof.org == org)
        if domains:
            statement = statement.where(SsoDomainProof.domain.not_in(domains))
        await self.change(statement)

    async def delete_proofs(self, org: str) -> int:
        """Forget every proof of the org; how many went."""
        return await self.change(delete(SsoDomainProof).where(SsoDomainProof.org == org))
