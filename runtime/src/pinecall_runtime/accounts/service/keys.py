"""API keys: minted, verified into an actor, revoked with every copy; the scopes a role presets."""

import asyncio
import contextlib
import logging
import time
from collections.abc import Callable, Iterable, Mapping, Sequence
from dataclasses import dataclass
from datetime import datetime

from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from pinecall_runtime.accounts.models import ApiKey, Member
from pinecall_runtime.accounts.repository import ApiKeyRepository, MemberRepository
from pinecall_runtime.enums import Env, KeyScope, MemberStatus, Role
from pinecall_runtime.exceptions import (
    Forbidden,
    NotFound,
    ServiceUnavailable,
    Unauthorized,
    ValidationError,
)
from pinecall_runtime.kit.auth import KEY_PREFIX, THE_ORGS_OWN, Actor, Person, Scope
from pinecall_runtime.kit.crypto import fingerprint, random_id, random_token
from pinecall_runtime.kit.loops import survived
from pinecall_runtime.kit.time import now
from pinecall_runtime.postgres import box_task, box_wide
from pinecall_runtime.redis import Signal

logger = logging.getLogger(__name__)

# The prefix says the env, so a key pasted into the wrong one is caught before it knocks. A
# person's one key is production's: it opens the sandbox too, and the request names the env.
PREFIX = KEY_PREFIX
KEY_BYTES = 32
ID_PREFIX = "k_"

EVERY_SCOPE: frozenset[KeyScope] = frozenset(KeyScope)
# Default scopes: every scope except the box's own two.
KEY_SCOPES: frozenset[KeyScope] = EVERY_SCOPE - {KeyScope.fleet, KeyScope.runner}
# Serving an agent, its calls, room tokens, knowledge pushes and evals; never people or money.
SERVER_SCOPES: frozenset[KeyScope] = frozenset(
    {KeyScope.app, KeyScope.calls, KeyScope.talk, KeyScope.knowledge, KeyScope.evals}
)
# A role is only a preset of key scopes. Endpoints check scopes, never roles.
ROLE_SCOPES: Mapping[Role, frozenset[KeyScope]] = {
    Role.qa: frozenset({KeyScope.calls, KeyScope.evals}),
    Role.supervisor: frozenset(
        {KeyScope.calls, KeyScope.evals, KeyScope.supervise, KeyScope.talk, KeyScope.memory, KeyScope.words}
    ),
    Role.manager: frozenset(
        {
            KeyScope.calls,
            KeyScope.evals,
            KeyScope.supervise,
            KeyScope.talk,
            KeyScope.memory,
            KeyScope.numbers,
            KeyScope.keys,
            KeyScope.providers,
            KeyScope.usage,
            KeyScope.team,
            KeyScope.words,
        }
    ),
    Role.admin: KEY_SCOPES,
    Role.developer: frozenset(
        {
            KeyScope.app,
            KeyScope.calls,
            KeyScope.talk,
            KeyScope.supervise,
            KeyScope.pipeline,
            KeyScope.knowledge,
            KeyScope.memory,
            KeyScope.evals,
            KeyScope.words,
        }
    ),
}

# Verifying a key is a round trip per request. A key is remembered this long on each gateway; a
# revocation or a change to its person is said on the signal and forgets it everywhere at once.
REMEMBERED_FOR_S = 5.0
FORGET_CHANNEL = "keys:forgotten"
RETRY_S = 1.0


class KeyExpired(Unauthorized):
    """The key was found but is past its expiry."""

    def __init__(self, at: datetime) -> None:
        super().__init__(
            f"this key expired at {at.isoformat(timespec='seconds')}: it opens nothing now, "
            "and a new one is made in the console"
        )


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


class NotYoursToGrant(Forbidden):
    """A key grants only a role whose scopes it holds, or a manager would make an admin."""

    def __init__(self, role: Role, opens: Iterable[str]) -> None:
        listed = " · ".join(sorted(opens)) or "nothing"
        super().__init__(
            f"this key does not open everything {role} would: it opens {listed}, so it cannot grant {role}"
        )


class NotYoursToSwitch(Forbidden):
    """Production access is given by somebody who has it."""

    def __init__(self, name: str) -> None:
        super().__init__(f"{name} has no production access, and cannot give it: an admin does")


class NotTheirAgent(Forbidden):
    """A person works on some agents and this is not one of them."""

    def __init__(self, name: str, agents: Iterable[str], slug: str) -> None:
        super().__init__(
            f"{name} works on {', '.join(sorted(agents))}, and agent {slug} is not one of them: "
            "an admin adds it in Team"
        )


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


async def issue_key(session: AsyncSession, issue: Issue) -> tuple[ApiKey, str]:
    """Mint a key: the row keeps its fingerprint, the secret is handed back this once."""
    secret = f"{PREFIX[issue.env]}{random_token(KEY_BYTES)}"
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
    return key, secret


async def issue_person_key(
    session: AsyncSession, member: Member, *, parent: ApiKey | None = None, label: str | None = None
) -> tuple[ApiKey, str]:
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


async def verify_key(session: AsyncSession, secret: str) -> tuple[ApiKey, Member | None] | None:
    """The key and its person; None for a key unknown, revoked, or whose person is gone."""
    keys = ApiKeyRepository(session)
    with box_wide():
        key = await keys.get_live_by_hash(fingerprint(secret))
        if key is None:
            return None
        if key.expires_at is not None and key.expires_at <= now():
            raise KeyExpired(key.expires_at)
        member = None
        if key.subject is not None:
            member = await MemberRepository(session).get_by_id(key.subject)
            # A person gone, disabled, or (on a visit) no longer running the box opens nothing.
            if member is None or member.status is not MemberStatus.active:
                return None
            if member.org != key.org and not member.operator:
                return None
        await keys.touch(key)
    return key, member


async def list_keys(session: AsyncSession, org: str) -> Sequence[ApiKey]:
    """Every key of the org, oldest first, the revoked ones too."""
    return await ApiKeyRepository(session).list_of_org(org)


async def get_key(session: AsyncSession, key_id: str) -> ApiKey:
    """The key row by id: the actor's own, as its endpoints read it back."""
    keys = ApiKeyRepository(session)
    key = await keys.one_or_none(keys.statement().where(ApiKey.id == key_id))
    if key is None:
        raise NoSuchKey(key_id)
    return key


async def revoke_key(session: AsyncSession, actor: Actor, fingerprint_: str) -> list[str]:
    """Stop one of the org's keys and every copy of it: your own, one you made, or any with `keys`."""
    keys = ApiKeyRepository(session)
    key = await keys.get_by_hash_in_org(actor.org, fingerprint_)
    if key is None or key.revoked_at is not None or not _may_stop(actor, key):
        raise NoSuchKey(fingerprint_)
    stopped = await keys.revoke_tree(fingerprint_)
    if not stopped:
        raise NoSuchKey(fingerprint_)
    return stopped


# The box's own revocation: a hosted app's token when the app goes, or the operator's word.
async def revoke_fingerprint(session: AsyncSession, fingerprint_: str) -> list[str]:
    """Stop a key and every copy of it by its fingerprint, whoever made it; the fingerprints stopped."""
    return await ApiKeyRepository(session).revoke_tree(fingerprint_)


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


def check_may_grant(actor: Actor, role: Role | None, *, production: bool) -> None:
    """Refuse a role or production access the actor does not have to give."""
    if role is not None and actor.person is not None and not ROLE_SCOPES[role] <= actor.scopes:
        raise NotYoursToGrant(role, actor.scopes)
    acts_there = (actor.env is Env.production) if actor.person is None else actor.person.opens_production
    if production and not acts_there:
        raise NotYoursToSwitch(actor.name)


def check_agent(actor: Actor, slug: str) -> None:
    """Refuse a person whose list of agents leaves this one out; an empty list is every agent."""
    person = actor.person
    if person is None or not person.agents or person.org != actor.org or slug in person.agents:
        return
    raise NotTheirAgent(person.name, person.agents, slug)


def actor_of(key: ApiKey, member: Member | None, env: Env, holder: str = THE_ORGS_OWN) -> Actor:
    """The actor a verified key acts as in this env."""
    person = None
    if member is not None:
        person = Person(
            id=member.id,
            org=member.org,
            email=member.email,
            name=member.name,
            role=member.role,
            agents=frozenset(member.agents),
            operator=member.operator,
            production=member.production,
        )
    return Actor(
        key_id=key.id,
        org=key.org,
        env=env,
        scopes=frozenset(KeyScope(scope) for scope in key.scopes),
        person=person,
        label=key.label,
        expires_at=key.expires_at,
        holder=holder,
    )


def env_of_request(key: ApiKey, member: Member | None, asked: str | None) -> Env:
    """The env a request acts in: a server key's own, else the one its header asks for."""
    if asked is not None and asked not in Env.__members__:
        raise Forbidden(f"pinecall-env is sandbox or production, not {asked!r}")
    wanted = None if asked is None else Env(asked)
    if member is None:
        if wanted is not None and wanted is not key.env:
            raise Forbidden(
                f"this key is a {key.env} server's token, and this request is for {wanted}: "
                "a server's token opens the env it was made in"
            )
        return key.env
    env = Env.sandbox if wanted is None else wanted
    if env is Env.production and not member.opens_production:
        raise Forbidden(f"{member.name} has no production access: an admin gives it in Team")
    return env


def scope_of_request(actor_: Actor, looking_at: Member | None = None) -> Scope:
    """The scope a request acts in: the org's in production, the person's own in the sandbox."""
    person = actor_.person
    if actor_.env is Env.production or person is None:
        return Scope(actor_.org, actor_.env, THE_ORGS_OWN)
    if looking_at is None or looking_at.id == person.id:
        return Scope(actor_.org, actor_.env, person.id)
    # Both team and app: a manager holds team alone and does not open developers' sandboxes.
    if not {KeyScope.team, KeyScope.app} <= actor_.scopes:
        raise Forbidden("only a key that sees every scope opens a colleague's, and only in the sandbox")
    if looking_at.org != actor_.org or looking_at.status is not MemberStatus.active:
        raise Forbidden("no active member of this org answers to that scope")
    return Scope(actor_.org, actor_.env, looking_at.id)


class Forgotten(BaseModel):
    """What to forget: one key by its fingerprint, or every key of a person."""

    fingerprint: str | None = None
    subject: str | None = None


class KeyCache:
    """The keys this gateway verified lately, and the revocations it hears from the others."""

    def __init__(
        self,
        sessions: async_sessionmaker[AsyncSession],
        signal: Signal,
        *,
        for_s: float = REMEMBERED_FOR_S,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self.sessions = sessions
        self.signal = signal
        self.for_s = for_s
        self.clock = clock
        self._kept: dict[str, tuple[ApiKey, Member | None, float]] = {}
        self._listening: asyncio.Task[None] | None = None
        self._swept_at = clock()

    async def start(self) -> None:
        """Listen for revocations said by any gateway."""
        if self._listening is None:
            self._listening = box_task(self._listen())

    async def close(self) -> None:
        """Stop listening and forget everything."""
        if self._listening is not None:
            self._listening.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await self._listening
            self._listening = None
        self._kept.clear()

    async def verify(self, secret: str) -> tuple[ApiKey, Member | None] | None:
        """From memory within the seconds, else from the database."""
        hashed = fingerprint(secret)
        moment = self.clock()
        kept = self._kept.get(hashed)
        if kept is not None and kept[2] > moment:
            return kept[0], kept[1]
        async with self.sessions() as session:
            verified = await verify_key(session, secret)
            await session.commit()
        if verified is None:
            self._kept.pop(hashed, None)
            return None
        key, member = verified
        until = moment + self.for_s
        if key.expires_at is not None:
            until = min(until, moment + max((key.expires_at - now()).total_seconds(), 0.0))
        self._kept[hashed] = (key, member, until)
        self._sweep(moment)
        return verified

    def forget(self, *, fingerprint_: str | None = None, subject: str | None = None) -> None:
        """Forget a key, or a person's keys, here and on every other gateway."""
        forgotten = Forgotten(fingerprint=fingerprint_, subject=subject)
        self._forget(forgotten)
        self.signal.publish(FORGET_CHANNEL, forgotten.model_dump_json().encode())

    def _forget(self, forgotten: Forgotten) -> None:
        if forgotten.fingerprint is not None:
            self._kept.pop(forgotten.fingerprint, None)
        if forgotten.subject is not None:
            for hashed in [h for h, (key, _, _) in self._kept.items() if key.subject == forgotten.subject]:
                del self._kept[hashed]

    def _sweep(self, moment: float) -> None:
        if moment - self._swept_at < self.for_s:
            return
        self._swept_at = moment
        for hashed in [h for h, (_, _, until) in self._kept.items() if until <= moment]:
            del self._kept[hashed]

    async def _listen(self) -> None:
        while True:
            try:
                listener = await self.signal.subscribe(FORGET_CHANNEL)
            except ServiceUnavailable:
                await asyncio.sleep(RETRY_S)
                continue
            # What was revoked while the signal was away is unknown: nothing from before is trusted.
            self._kept.clear()
            try:
                async for data in listener:
                    # A revocation that cannot be read is said and the next is heard: the listener
                    # that died with it would leave every revoked key trusted for as long as it is kept.
                    with survived("reading a revocation of another gateway"):
                        self._forget(Forgotten.model_validate_json(data))
            finally:
                listener.close()
            with contextlib.suppress(TimeoutError):
                await asyncio.wait_for(self.signal.connected(), RETRY_S)


def _may_stop(actor: Actor, key: ApiKey) -> bool:
    subject = None if actor.person is None else actor.person.id
    mine = subject is not None and subject in (key.subject, key.created_by)
    return mine or KeyScope.keys in actor.scopes
