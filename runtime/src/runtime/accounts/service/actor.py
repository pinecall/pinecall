"""A request's actor: a key verified into who holds it, the env and the scope it acts in, and what that actor may do."""

from collections.abc import Iterable
from dataclasses import dataclass, replace
from datetime import datetime

from sqlalchemy.ext.asyncio import AsyncSession

from runtime.accounts.models import ApiKey, Member
from runtime.accounts.repository.keys import ApiKeyRepository
from runtime.accounts.repository.members import MemberRepository, Membership
from runtime.accounts.repository.orgs import OrgRepository
from runtime.actor import THE_ORGS_OWN, Actor, Scope
from runtime.actor import Person as PersonBehind
from runtime.enums import ROLE_SCOPES, Env, KeyScope, MemberStatus, Role
from runtime.exceptions import Forbidden, Unauthorized
from runtime.kit.crypto import fingerprint
from runtime.kit.time import now
from runtime.scoping import box_wide


class KeyExpired(Unauthorized):
    """The key was found but is past its expiry."""

    def __init__(self, at: datetime) -> None:
        super().__init__(
            f"this key expired at {at.isoformat(timespec='seconds')}: it opens nothing now, "
            "and a new one is made in the console"
        )


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
class Verified:
    """A key that opens something, and the member it was minted for; none on a server's token."""

    key: ApiKey
    membership: Membership | None = None


@dataclass(frozen=True, slots=True)
class Asked:
    """Where a request says it acts: the env it names, the colleague it looks into, the scope a worker serves."""

    env: str | None = None
    looking_at: str | None = None
    dispatched: Scope | None = None


@dataclass(frozen=True, slots=True)
class Identity:
    """Whose key a request carries, the env it acts in, and what the key opens."""

    org: str
    slug: str | None
    key_id: str
    label: str | None
    env: Env
    scopes: list[str]
    subject: str | None
    name: str | None
    email: str | None
    operator: bool
    visiting: bool
    production: bool


async def verify_key(session: AsyncSession, secret: str) -> Verified | None:
    """The key and its person; None for a key unknown, revoked, or whose person is gone."""
    keys = ApiKeyRepository(session)
    with box_wide():
        key = await keys.find_live_by_hash(fingerprint(secret))
        if key is None:
            return None
        if key.expires_at is not None and key.expires_at <= now():
            raise KeyExpired(key.expires_at)
        membership = None
        if key.subject is not None:
            membership = await MemberRepository(session).find_membership(key.subject)
            # A person gone, disabled, or (on a visit) no longer running the box opens nothing.
            if membership is None or membership.status is not MemberStatus.active:
                return None
            if membership.org != key.org and not membership.operator:
                return None
        await keys.touch(key)
    return Verified(key, membership)


def actor_of(verified: Verified, env: Env, holder: str = THE_ORGS_OWN) -> Actor:
    """The actor a verified key acts as in this env."""
    key, membership = verified.key, verified.membership
    person = None
    if membership is not None:
        person = PersonBehind(
            id=membership.id,
            org=membership.org,
            email=membership.email,
            name=membership.name,
            role=membership.role,
            agents=frozenset(membership.member.agents),
            operator=membership.operator,
            production=membership.member.production,
            verified=membership.verified,
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


def env_of_request(verified: Verified, asked: str | None) -> Env:
    """The env a request acts in: a server key's own, else the one its header asks for."""
    key, membership = verified.key, verified.membership
    if asked is not None and asked not in Env.__members__:
        raise Forbidden(f"pinecall-env is sandbox or production, not {asked!r}")
    wanted = None if asked is None else Env(asked)
    if membership is None:
        if wanted is not None and wanted is not key.env:
            raise Forbidden(
                f"this key is a {key.env} server's token, and this request is for {wanted}: "
                "a server's token opens the env it was made in"
            )
        return key.env
    env = Env.sandbox if wanted is None else wanted
    if env is Env.production and not membership.member.opens_production:
        raise Forbidden(f"{membership.name} has no production access: an admin gives it in Team")
    return env


# Both team and app: a manager holds team alone and does not open developers' sandboxes.
def sees_every_copy(actor: Actor) -> bool:
    """Whether a person's key may read every colleague's copy in the sandbox, not only their own."""
    return actor.env is Env.sandbox and actor.person is not None and {KeyScope.team, KeyScope.app} <= actor.scopes


def scope_of_request(actor: Actor, looking_at: Member | None = None) -> Scope:
    """The scope a request acts in: the org's in production, the person's own in the sandbox."""
    person = actor.person
    if actor.env is Env.production or person is None:
        return Scope(actor.org, actor.env, THE_ORGS_OWN)
    if looking_at is None or looking_at.id == person.id:
        return Scope(actor.org, actor.env, person.id)
    if not sees_every_copy(actor):
        raise Forbidden("only a key that sees every scope opens a colleague's, and only in the sandbox")
    if looking_at.org != actor.org or looking_at.status is not MemberStatus.active:
        raise Forbidden("no active member of this org answers to that scope")
    return Scope(actor.org, actor.env, looking_at.id)


# Only the fleet's key names a scope: the scope of the call it serves, as its dispatch named it
# (`?org=&env=&holder=`). Its own org is the box's and holds none of the calls it answers.
def read_dispatch(org: str | None, env: str | None, holder: str | None) -> Scope | None:
    """The scope a worker asks in, from the dispatch it was started with; None when it names none."""
    if not org or env not in set(Env):
        return None
    return Scope(org, Env(env), holder or THE_ORGS_OWN)


# The colleague is looked for by id within the key's org, before the request is scoped to it.
async def resolve(session: AsyncSession, verified: Verified, asked: Asked) -> Actor:
    """The actor a verified key acts as, in the env and the scope the request asks for."""
    env = env_of_request(verified, asked.env)
    actor = actor_of(verified, env)
    colleague = None
    if asked.looking_at:
        colleague = await MemberRepository(session).find(actor.org, asked.looking_at)
    resolved = actor_of(verified, env, holder=scope_of_request(actor, colleague).holder)
    if asked.dispatched is None or not actor.opens(KeyScope.fleet):
        return resolved
    served = asked.dispatched
    return replace(resolved, org=served.org, env=served.env, holder=served.holder)


async def identify(session: AsyncSession, actor: Actor) -> Identity:
    """Whose key this is, the env the request acts in, and what the key opens."""
    org = await OrgRepository(session).find(actor.org)
    person = actor.person
    return Identity(
        org=actor.org,
        slug=None if org is None else org.slug,
        key_id=actor.key_id,
        label=actor.label,
        env=actor.env,
        scopes=sorted(scope.value for scope in actor.scopes),
        subject=None if person is None else person.id,
        name=None if person is None else person.name,
        email=None if person is None else person.email,
        operator=person is not None and person.operator,
        visiting=person is not None and person.org != actor.org,
        production=(actor.env is Env.production) if person is None else person.opens_production,
    )


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
