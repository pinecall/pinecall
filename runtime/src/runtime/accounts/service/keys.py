"""API keys: minted, listed for who may see them, and revoked with every copy made of them."""

from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from datetime import datetime
from typing import Literal

from sqlalchemy.ext.asyncio import AsyncSession

from runtime.accounts.models import ApiKey, Member, Person
from runtime.accounts.repository.keys import ApiKeyRepository
from runtime.accounts.repository.members import MemberRepository
from runtime.accounts.service.key_cache import KeyCache
from runtime.actor import Actor
from runtime.actor import Person as PersonBehind
from runtime.auth import KEY_PREFIX
from runtime.enums import KEY_SCOPES, ROLE_SCOPES, SERVER_SCOPES, Env, KeyScope
from runtime.exceptions import Forbidden, NotFound, ValidationError
from runtime.kit.crypto import fingerprint, random_id, random_token
from runtime.kit.time import now
from runtime.scoping import box_wide

# The prefix says the env, so a key pasted into the wrong one is caught before it is tried. A
# person's one key is production's: it opens the sandbox too, and the request names the env.
KEY_BYTES = 32
ID_PREFIX = "k_"


class NoSuchKey(NotFound):
    """No live key of the org has the fingerprint."""

    def __init__(self, fingerprint_: str) -> None:
        super().__init__(f"no live key of this org has the fingerprint {fingerprint_}")


class NotAServersScopes(ValidationError):
    """A server's token asked for scopes a server's token does not open."""

    def __init__(self, wanted: Iterable[str]) -> None:
        listed = ", ".join(sorted(set(wanted))) or "none"
        super().__init__(
            f"a server's token opens some of {', '.join(sorted(SERVER_SCOPES))}, and at least one; not {listed}"
        )


class ExpiryInThePast(ValidationError):
    """A key's expiry is a moment to come."""

    def __init__(self, at: datetime) -> None:
        super().__init__(f"a key's expiry is a moment to come, not {at.isoformat(timespec='seconds')}")


@dataclass(frozen=True, slots=True)
class Issue:
    """What a new key is made with."""

    org: str
    env: Env
    scopes: frozenset[KeyScope] = KEY_SCOPES
    label: str | None = None
    subject: str | None = None
    name: str | None = None
    created_by: str | None = None
    expires_at: datetime | None = None
    parent: str | None = None


# Flat beside the row, as every answer that mints a key reads one: `key` is the secret there.
@dataclass(frozen=True, slots=True)
class Issued:
    """A key just minted: its row, and the secret, which is handed over this once."""

    row: ApiKey
    secret: str

    @property
    def key(self) -> str:
        """The secret: the key itself, answered once and never kept."""
        return self.secret

    @property
    def key_id(self) -> str:
        """The row's id."""
        return self.row.id

    @property
    def org(self) -> str:
        """The org the key opens."""
        return self.row.org

    @property
    def label(self) -> str | None:
        """What the key was written under."""
        return self.row.label

    @property
    def env(self) -> Env:
        """The env it was made in."""
        return self.row.env

    @property
    def scopes(self) -> list[str]:
        """What it opens, sorted."""
        return sorted(self.row.scopes)

    @property
    def subject(self) -> str | None:
        """The member it was minted for; None on a server's token."""
        return self.row.subject

    @property
    def name(self) -> str | None:
        """Whose it is, as the org calls them."""
        return self.row.name


@dataclass(frozen=True, slots=True)
class KeyDetails:
    """One key as a list shows it: by its fingerprint, never the key, its maker named."""

    fingerprint: str
    label: str | None
    kind: Literal["person", "server"]
    env: Env | None
    name: str | None
    created_by: str | None
    created_at: datetime
    last_used_at: datetime | None
    revoked_at: datetime | None
    scopes: list[str]
    expires_at: datetime | None


async def issue_key(session: AsyncSession, issue: Issue) -> Issued:
    """Mint a key: the row keeps its fingerprint, the secret is handed back this once."""
    secret = f"{KEY_PREFIX[issue.env]}{random_token(KEY_BYTES)}"
    key = ApiKey(
        id=random_id(ID_PREFIX),
        hash=fingerprint(secret),
        org=issue.org,
        label=issue.label,
        env=issue.env,
        scopes=sorted(issue.scopes),
        subject=issue.subject,
        name=issue.name,
        created_by=issue.created_by,
        expires_at=issue.expires_at,
        parent=issue.parent,
    )
    await ApiKeyRepository(session).add(key)
    return Issued(key, secret)


async def issue_person_key(
    session: AsyncSession, member: Member, *, parent: ApiKey | None = None, label: str | None = None
) -> Issued:
    """A person's key: the role's scopes, both envs, never outliving the key it came from."""
    return await issue_key(
        session,
        Issue(
            org=member.org,
            env=Env.production,
            scopes=ROLE_SCOPES[member.role],
            label=label,
            subject=member.id,
            name=member.name,
            created_by=member.id,
            expires_at=None if parent is None else parent.expires_at,
        ),
    )


# The secret is in this answer and never again.
async def issue_server_key(
    session: AsyncSession,
    person: PersonBehind,
    org: str,
    env: Env,
    *,
    label: str,
    scopes: Sequence[KeyScope] | None = None,
    expires_at: datetime | None = None,
) -> Issued:
    """A server's token for the org in one env, made by a person who may act there."""
    if env is Env.production and not person.opens_production:
        raise Forbidden(f"{person.name} has no production access: a production token is made by somebody who has")
    check_expiry(expires_at)
    issue = Issue(
        org=org, env=env, scopes=server_scopes(scopes), label=label, created_by=person.id, expires_at=expires_at
    )
    return await issue_key(session, issue)


async def get_key(session: AsyncSession, key_id: str) -> ApiKey:
    """The key row by id: the actor's own, as its endpoints read it back."""
    key = await ApiKeyRepository(session).find(key_id)
    if key is None:
        raise NoSuchKey(key_id)
    return key


async def list_keys(session: AsyncSession, org: str) -> list[KeyDetails]:
    """Every key of the org, oldest first, the revoked ones too, each maker named where the org still knows them."""
    names = {seated.id: seated.name for seated in await MemberRepository(session).list_memberships(org)}
    return [_details_of(key, names) for key in await ApiKeyRepository(session).list_of_org(org)]


async def list_keys_visible_to(session: AsyncSession, actor: Actor) -> list[KeyDetails]:
    """The org's keys this key may see: every server's, your own person keys, or every one with `keys`."""
    names = {seated.id: seated.name for seated in await MemberRepository(session).list_memberships(actor.org)}
    subject = None if actor.person is None else actor.person.id
    return [
        _details_of(key, names)
        for key in await ApiKeyRepository(session).list_of_org(actor.org)
        if key.subject is None or key.subject == subject or KeyScope.keys in actor.scopes
    ]


# A change to a key or to the member it was minted for is said to every gateway's cache once it is
# committed: each of these takes the cache, so no caller can revoke and forget to say so.
async def revoke_key(session: AsyncSession, cache: KeyCache, actor: Actor, fingerprint_: str) -> list[str]:
    """Stop one of the org's keys and every copy of it: your own, one you made, or any with `keys`."""
    repository = ApiKeyRepository(session)
    key = await repository.find_by_hash_in_org(actor.org, fingerprint_)
    if key is None or key.revoked_at is not None or not _may_stop(actor, key):
        raise NoSuchKey(fingerprint_)
    stopped = await revoke_fingerprint(session, cache, fingerprint_)
    if not stopped:
        raise NoSuchKey(fingerprint_)
    return stopped


# The box's own revocation: a hosted app's token when the app goes, or the operator's word.
async def revoke_fingerprint(session: AsyncSession, cache: KeyCache, fingerprint_: str) -> list[str]:
    """Stop a key and every copy of it by its fingerprint, whoever made it; the fingerprints stopped."""
    stopped = await ApiKeyRepository(session).revoke_tree(fingerprint_)
    _forget(session, cache, stopped)
    return stopped


async def revoke_as_operator(session: AsyncSession, cache: KeyCache, fingerprint_: str) -> list[str]:
    """Stop any org's key and its copies at the operator's word; refused when no live key has the fingerprint."""
    stopped = await revoke_fingerprint(session, cache, fingerprint_)
    if not stopped:
        raise NoSuchKey(fingerprint_)
    return stopped


async def revoke_member_keys(session: AsyncSession, cache: KeyCache, member_id: str) -> None:
    """Every live key minted for the member is revoked, and the member forgotten by every gateway."""
    await ApiKeyRepository(session).revoke_of_member(member_id)
    cache.forget_after_commit(session, subject=member_id)


# A person's keys are their seats' keys, in every org: read and revoked as the box.
async def revoke_person_keys(session: AsyncSession, cache: KeyCache, person: Person) -> None:
    """Every live key minted for any seat of the person is revoked, in every org."""
    with box_wide():
        stopped = await ApiKeyRepository(session).revoke_of_person(person.id)
    _forget(session, cache, stopped)


# No foreign key reaches a key from its org (`api_keys.org` is text): the org's erasure calls this.
async def delete_keys(session: AsyncSession, org: str) -> int:
    """Forget every key of an org that is being erased; how many went."""
    return await ApiKeyRepository(session).delete_of_org(org)


def server_scopes(wanted: Sequence[KeyScope] | None) -> frozenset[KeyScope]:
    """The scopes a server's token is made with: all of a server's, or those asked for."""
    if wanted is None:
        return SERVER_SCOPES
    scopes = frozenset(scope for scope in SERVER_SCOPES if scope in wanted)
    if not scopes or len(scopes) != len(set(wanted)):
        raise NotAServersScopes(wanted)
    return scopes


def check_expiry(expires_at: datetime | None) -> None:
    """Refuse an expiry that is not a moment to come."""
    if expires_at is not None and expires_at <= now():
        raise ExpiryInThePast(expires_at)


def _forget(session: AsyncSession, cache: KeyCache, stopped: Iterable[str]) -> None:
    for each in stopped:
        cache.forget_after_commit(session, fingerprint=each)


def _may_stop(actor: Actor, key: ApiKey) -> bool:
    subject = None if actor.person is None else actor.person.id
    mine = subject is not None and subject in (key.subject, key.created_by)
    return mine or KeyScope.keys in actor.scopes


def _details_of(key: ApiKey, names: dict[str, str]) -> KeyDetails:
    return KeyDetails(
        fingerprint=key.hash,
        label=key.label,
        kind="person" if key.is_a_persons else "server",
        env=None if key.is_a_persons else key.env,
        name=key.name,
        created_by=None if key.created_by is None else names.get(key.created_by, key.created_by),
        created_at=key.created_at,
        last_used_at=key.last_used_at,
        revoked_at=key.revoked_at,
        scopes=sorted(key.scopes),
        expires_at=key.expires_at,
    )
