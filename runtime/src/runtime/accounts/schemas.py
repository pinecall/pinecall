"""The bodies of the accounts endpoints: members, invitations, keys, whoami, and the operator's orgs."""

from datetime import datetime
from typing import Literal

from pydantic import AwareDatetime, Field

from runtime.enums import Env, KeyScope, MemberStatus, Role
from runtime.kit.schemas import EmailAddress, Row, Schema

# ── members ──


class MemberRow(Row):
    """A member as every members endpoint answers one: never a password nor a link."""

    id: str
    email: str
    name: str
    role: Role
    agents: list[str]
    status: MemberStatus
    scopes: list[str]
    operator: bool
    production: bool
    verified: bool


class MemberList(Row):
    """GET /v1/members."""

    members: list[MemberRow]


class InviteMember(Schema):
    """POST /v1/members."""

    email: EmailAddress
    name: str
    role: Role
    agents: list[str] = Field(default_factory=list[str])
    production: bool = False


class Invited(Row):
    """An invitation or a reset: the member, the link's token once (null when only mailed)."""

    member: MemberRow
    token: str | None
    expires_at: datetime | None
    mailed: bool
    link: str | None = None


class SetPassword(Schema):
    """PUT /v1/members/{id}/password: the password, typed by an admin or by the member."""

    password: str = Field(min_length=1)


class ChangeMember(Schema):
    """PATCH /v1/members/{id}: what is named changes, what is left out stays."""

    role: Role | None = None
    agents: list[str] | None = None
    status: MemberStatus | None = None
    production: bool | None = None


class AcceptInvitation(Schema):
    """POST /v1/invitations/{token}."""

    password: str
    device: str | None = None


# ── keys ──


class KeyIssued(Row):
    """Every endpoint that mints a key: the secret this once, and what it was written under."""

    key: str
    key_id: str
    org: str
    label: str | None
    env: Env
    scopes: list[str]
    subject: str | None
    name: str | None


class FirstKey(KeyIssued):
    """POST /v1/invitations/{token}: the first key, and the member now active."""

    member: MemberRow


class CreateKey(Schema):
    """POST /v1/keys: a server's token for one env; fewer scopes and an end, if asked."""

    label: str
    env: Env
    scopes: list[KeyScope] | None = None
    expires_at: AwareDatetime | None = None


class KeyRow(Row):
    """GET /v1/keys, one row: by fingerprint, never the key."""

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
    expires_at: datetime | None = None


class KeyRevoked(Row):
    """POST /v1/keys/{fingerprint}/revoke."""

    fingerprint: str
    revoked: bool


# ── whoami ──


class Whoami(Row):
    """GET /v1/whoami: whose key this is and what it opens."""

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


# ── the operator's: the box, its orgs, their people and keys ──


class BoxIdentity(Row):
    """GET /v1/ops/whoami: the box an operator's key opens, and who holds the key."""

    operator: bool
    version: str
    domain: str | None
    # None for the box's own key.
    name: str | None
    org: str | None


class CreateOrg(Schema):
    """POST /v1/ops/orgs: the slug, and the name people read; the slug when none."""

    slug: str
    name: str | None = None


class OrgRow(Row):
    """One org: its minted id, its slug and its name."""

    id: str
    slug: str
    name: str


class OrgMembers(Row):
    """GET /v1/ops/orgs/{named}/members: the org's people, and how many hold a seat."""

    members: list[MemberRow]
    seated: int


class OperatorChange(Schema):
    """PUT /v1/ops/orgs/{named}/members/{id}/operator: whether this member runs the box."""

    operator: bool


class IssueOrgKey(Schema):
    """POST /v1/ops/orgs/{named}/keys: a key of the org, in an env, with scopes and an owner."""

    env: Env
    label: str | None = None
    scopes: list[KeyScope] | None = None
    subject: str | None = None
    name: str | None = None
