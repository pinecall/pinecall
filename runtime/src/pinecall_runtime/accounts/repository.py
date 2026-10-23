"""Every query on the accounts tables: orgs, members, invitations, keys, tokens, one-time secrets."""

from collections.abc import Sequence
from datetime import datetime, timedelta

from sqlalchemy import delete, func, literal, or_, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from pinecall_runtime.accounts.models import (
    ApiKey,
    Invitation,
    Member,
    OneUseWord,
    Org,
    OrgMail,
    OrgSso,
    SignInAttempt,
    SsoDomainProof,
    Token,
)
from pinecall_runtime.enums import Env, MemberStatus, Role
from pinecall_runtime.kit.repository import Repository
from pinecall_runtime.kit.time import now


class OrgRepository(Repository[Org]):
    """Orgs by id or slug."""

    model = Org

    async def get(self, named: str) -> Org | None:
        """By id or slug."""
        return await self.one_or_none(self.statement().where(or_(Org.id == named, Org.slug == named)).limit(1))

    async def list_all(self) -> Sequence[Org]:
        """Every org, oldest first."""
        return await self.all(self.statement().order_by(Org.created_at, Org.id))


class MemberRepository(Repository[Member]):
    """Members within an org, and a person's rows across orgs."""

    model = Member

    async def get(self, org: str, member_id: str) -> Member | None:
        """By id, within the org."""
        return await self.one_or_none(self.statement().where(Member.org == org, Member.id == member_id))

    async def get_by_id(self, member_id: str) -> Member | None:
        """By id, whatever the org."""
        return await self.one_or_none(self.statement().where(Member.id == member_id))

    async def get_by_email(self, org: str, email: str) -> Member | None:
        """By address, within the org."""
        return await self.one_or_none(self.statement().where(Member.org == org, Member.email == email))

    async def list_of_org(self, org: str) -> Sequence[Member]:
        """The org's people, oldest first, the disabled ones too."""
        return await self.all(self.statement().where(Member.org == org).order_by(Member.created_at, Member.id))

    async def active_admins(self, org: str) -> Sequence[Member]:
        """The org's admins who may sign in, oldest first."""
        statement = self.statement().where(
            Member.org == org, Member.role == Role.admin, Member.status == MemberStatus.active
        )
        return await self.all(statement.order_by(Member.created_at, Member.id))

    async def active_operators(self) -> Sequence[Member]:
        """The box's operators who may sign in, in every org. Read box-wide by the caller."""
        statement = self.statement().where(Member.operator, Member.status == MemberStatus.active)
        return await self.all(statement.order_by(Member.created_at, Member.id))

    async def list_of_person(self, email: str) -> Sequence[Member]:
        """Every membership of the address, oldest first. Read box-wide by the caller."""
        return await self.all(self.statement().where(Member.email == email).order_by(Member.created_at, Member.id))

    async def count_seated(self, org: str) -> int:
        """Every member not disabled holds a seat."""
        return await self.count(self.statement().where(Member.org == org, Member.status != MemberStatus.disabled))

    async def count_other_active_admins(self, org: str, member_id: str) -> int:
        """Active admins of the org other than this one."""
        return await self.count(
            self.statement().where(
                Member.org == org,
                Member.id != member_id,
                Member.role == Role.admin,
                Member.status == MemberStatus.active,
            )
        )

    # One password per person: the newest row that has one speaks for every row of the address.
    async def password_hash_of(self, email: str) -> str | None:
        """The person's one password hash, or None when they set none. Read box-wide by the caller."""
        statement = (
            select(Member.password_hash)
            .where(Member.email == email, Member.password_hash.is_not(None))
            .order_by(Member.created_at.desc())
            .limit(1)
        )
        return (await self.session.execute(statement)).scalar_one_or_none()

    async def is_verified_anywhere(self, email: str) -> bool:
        """Whether any row of the address was proven. Read box-wide by the caller."""
        return await self.exists(self.statement().where(Member.email == email, Member.verified_at.is_not(None)))

    async def set_password_everywhere(self, email: str, password_hash: str) -> None:
        """A vouched reset sets the person's one password in every org that holds one."""
        await self.session.execute(
            update(Member)
            .where(Member.email == email, Member.password_hash.is_not(None))
            .values(password_hash=password_hash)
        )

    async def lock_org(self, org: str) -> None:
        """A transaction-long advisory lock on the org: the seat count and the insert go together."""
        await self.session.execute(select(func.pg_advisory_xact_lock(func.hashtext(literal(org)))))


class InvitationRepository(Repository[Invitation]):
    """The links that seat a person or reset their password."""

    model = Invitation

    async def spend(self, token_hash: str) -> Invitation | None:
        """Mark the link spent, once; None when dead, spent or unknown."""
        statement = (
            update(Invitation)
            .where(
                Invitation.token_hash == token_hash,
                Invitation.spent_at.is_(None),
                Invitation.expires_at > now(),
            )
            .values(spent_at=now())
            .returning(Invitation)
        )
        return (await self.session.execute(statement)).scalar_one_or_none()

    async def spend_open_of(self, member_id: str) -> None:
        """Every open link of the member is spent: a new one replaces them."""
        await self.session.execute(
            update(Invitation)
            .where(Invitation.member == member_id, Invitation.spent_at.is_(None))
            .values(spent_at=now())
        )


class ApiKeyRepository(Repository[ApiKey]):
    """API keys by fingerprint and by org."""

    model = ApiKey

    async def get_live_by_hash(self, hash_: str) -> ApiKey | None:
        """The key with this fingerprint unless revoked; expired keys are returned, so the refusal can say so."""
        return await self.one_or_none(self.statement().where(ApiKey.hash == hash_, ApiKey.revoked_at.is_(None)))

    async def get_by_hash_in_org(self, org: str, hash_: str) -> ApiKey | None:
        """The org's key with this fingerprint, revoked or not."""
        return await self.one_or_none(self.statement().where(ApiKey.org == org, ApiKey.hash == hash_))

    async def list_of_org(self, org: str) -> Sequence[ApiKey]:
        """Every key of the org, oldest first, the revoked ones too."""
        return await self.all(self.statement().where(ApiKey.org == org).order_by(ApiKey.created_at, ApiKey.id))

    async def touch(self, key: ApiKey) -> None:
        """Note the key was used, at most once a minute."""
        last = key.last_used_at
        if last is None or last < now() - timedelta(minutes=1):
            await self.update(key, last_used_at=now())

    async def revoke_tree(self, hash_: str) -> list[str]:
        """Revoke the key and every copy made of it, however deep; the fingerprints stopped."""
        roots = (
            select(ApiKey.id).where(ApiKey.hash == hash_, ApiKey.revoked_at.is_(None)).cte("stopped", recursive=True)
        )
        copies = select(ApiKey.id).where(ApiKey.parent == roots.c.id, ApiKey.revoked_at.is_(None))
        stopped = roots.union(copies)
        statement = (
            update(ApiKey).where(ApiKey.id.in_(select(stopped.c.id))).values(revoked_at=now()).returning(ApiKey.hash)
        )
        return list((await self.session.execute(statement)).scalars().all())

    async def revoke_of_person(self, member_id: str) -> None:
        """Every live key minted for the member is revoked; the rows stay, the log names them."""
        await self.session.execute(
            update(ApiKey).where(ApiKey.subject == member_id, ApiKey.revoked_at.is_(None)).values(revoked_at=now())
        )


class TokenRepository(Repository[Token]):
    """The ledger of room tokens, each spent once when its call opens."""

    model = Token

    async def spend(self, call: str, org: str, env: Env, agent: str) -> bool:
        """Spend the call's token in this scope, once; False when none matched."""
        statement = (
            update(Token)
            .where(
                Token.call == call,
                Token.spent_at.is_(None),
                Token.org == org,
                Token.agent == agent,
                or_(Token.env.is_(None), Token.env == env),
            )
            .values(spent_at=now())
            .returning(Token.call)
        )
        return (await self.session.execute(statement)).scalar_one_or_none() is not None

    async def get(self, call: str) -> Token | None:
        """The ledger's row for the call, spent or not."""
        return await self.one_or_none(self.statement().where(Token.call == call))


class OneUseWordRepository(Repository[OneUseWord]):
    """Secrets spent once, kept by their hash with their value sealed."""

    model = OneUseWord

    async def get(self, word_hash: bytes) -> OneUseWord | None:
        """By hash, dead or alive."""
        return await self.one_or_none(self.statement().where(OneUseWord.word_hash == word_hash))

    async def put(self, word_hash: bytes, kind: str, sealed: str, expires_at: float) -> None:
        """Keep, or replace whole with attempts reset."""
        from sqlalchemy.dialects.postgresql import insert

        statement = insert(OneUseWord).values(word_hash=word_hash, kind=kind, sealed=sealed, expires_at=expires_at)
        await self.session.execute(
            statement.on_conflict_do_update(
                index_elements=[OneUseWord.word_hash],
                set_={"kind": kind, "sealed": sealed, "expires_at": expires_at, "attempts": 0},
            )
        )

    async def spend(self, word_hash: bytes, at: float) -> OneUseWord | None:
        """Delete and return the row if alive; of two spenders, one gets it."""
        statement = (
            delete(OneUseWord)
            .where(OneUseWord.word_hash == word_hash, OneUseWord.expires_at > at)
            .returning(OneUseWord)
        )
        return (await self.session.execute(statement)).scalar_one_or_none()

    async def fill(self, word_hash: bytes, sealed: str, at: float) -> bool:
        """Change what a living word holds; False for a dead one."""
        statement = (
            update(OneUseWord)
            .where(OneUseWord.word_hash == word_hash, OneUseWord.expires_at > at)
            .values(sealed=sealed)
            .returning(OneUseWord.word_hash)
        )
        return (await self.session.execute(statement)).scalar_one_or_none() is not None

    async def count_attempt(self, word_hash: bytes) -> int:
        """One more wrong guess; how many there were."""
        statement = (
            update(OneUseWord)
            .where(OneUseWord.word_hash == word_hash)
            .values(attempts=OneUseWord.attempts + 1)
            .returning(OneUseWord.attempts)
        )
        return (await self.session.execute(statement)).scalar_one_or_none() or 0

    async def forget(self, word_hash: bytes) -> None:
        """The word opens nothing from now on."""
        await self.session.execute(delete(OneUseWord).where(OneUseWord.word_hash == word_hash))

    async def sweep(self, at: float) -> None:
        """Drop every dead word."""
        await self.session.execute(delete(OneUseWord).where(OneUseWord.expires_at <= at))


class SignInAttemptRepository(Repository[SignInAttempt]):
    """Sign-in attempts by name, in a sliding minute, across every gateway."""

    model = SignInAttempt

    async def count_and_record(self, name: str, at: float, window_s: float) -> int:
        """Record one attempt and answer how many the name made in the window, this one included."""
        await self.session.execute(delete(SignInAttempt).where(SignInAttempt.at < at - window_s))
        await self.session.execute(select(func.pg_advisory_xact_lock(func.hashtext(literal(name)))))
        await self.add(SignInAttempt(name=name, at=at), flush=True)
        return await self.count(self.statement().where(SignInAttempt.name == name, SignInAttempt.at >= at - window_s))


class SsoRepository(Repository[OrgSso]):
    """An org's identity provider and its domain proofs."""

    model = OrgSso

    async def get(self, org: str) -> OrgSso | None:
        """The org's provider row."""
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

    async def proofs_of(self, org: str) -> Sequence[SsoDomainProof]:
        """Every domain's proof, by domain."""
        return list(
            (
                await self.session.execute(
                    select(SsoDomainProof).where(SsoDomainProof.org == org).order_by(SsoDomainProof.domain)
                )
            )
            .scalars()
            .all()
        )

    async def add_proof(self, proof: SsoDomainProof) -> SsoDomainProof:
        """Keep a domain's proof, flushed so its token is read back."""
        self.session.add(proof)
        await self.session.flush()
        return proof

    async def verify_proof(self, proof: SsoDomainProof, at: datetime) -> None:
        """The domain's TXT record was seen: the proof stands from now."""
        proof.verified_at = at
        await self.session.flush()

    async def proof_of(self, org: str, domain: str) -> SsoDomainProof | None:
        """One domain's proof."""
        return (
            await self.session.execute(
                select(SsoDomainProof).where(SsoDomainProof.org == org, SsoDomainProof.domain == domain)
            )
        ).scalar_one_or_none()

    async def drop_proofs_not_in(self, org: str, domains: Sequence[str]) -> None:
        """Forget the proofs of domains the provider no longer admits."""
        statement = delete(SsoDomainProof).where(SsoDomainProof.org == org)
        if domains:
            statement = statement.where(SsoDomainProof.domain.not_in(domains))
        await self.session.execute(statement)


class MailRepository(Repository[OrgMail]):
    """An org's mailbox row."""

    model = OrgMail

    async def get(self, org: str) -> OrgMail | None:
        """The org's mailbox."""
        return await self.one_or_none(self.statement().where(OrgMail.org == org))


class Accounts:
    """The domain's repositories, one session."""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session
        self.orgs = OrgRepository(session)
        self.members = MemberRepository(session)
        self.invitations = InvitationRepository(session)
        self.keys = ApiKeyRepository(session)
        self.tokens = TokenRepository(session)
        self.words = OneUseWordRepository(session)
        self.sign_in_attempts = SignInAttemptRepository(session)
        self.sso = SsoRepository(session)
        self.mail = MailRepository(session)
