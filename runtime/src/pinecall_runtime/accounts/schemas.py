"""The bodies of the accounts endpoints: sign-in, members, keys, sign-up, SSO, mail, whoami."""

from datetime import datetime
from typing import Literal, Self, override

from pydantic import AwareDatetime, Field

from pinecall_runtime.accounts.models import ApiKey, Member
from pinecall_runtime.enums import Env, KeyScope, MemberStatus, Role
from pinecall_runtime.kit.auth import Actor
from pinecall_runtime.kit.schemas import Row, Schema

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

    @classmethod
    @override
    def of(cls, member: Member) -> Self:
        """The row, with the scopes the role presets and the production switch resolved."""
        from pinecall_runtime.accounts.service.keys import ROLE_SCOPES

        return cls(
            id=member.id,
            email=member.email,
            name=member.name,
            role=member.role,
            agents=sorted(member.agents),
            status=member.status,
            scopes=sorted(ROLE_SCOPES[member.role]),
            operator=member.operator,
            production=member.opens_production,
            verified=member.verified,
        )


class MemberList(Row):
    """GET /v1/members."""

    members: list[MemberRow]


class InviteMember(Schema):
    """POST /v1/members."""

    email: str
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

    @classmethod
    def minted(cls, key: ApiKey, secret: str) -> Self:
        """The key just minted."""
        return cls(
            key=secret,
            key_id=key.id,
            org=key.org,
            label=key.label,
            env=key.env,
            scopes=sorted(key.scopes),
            subject=key.subject,
            name=key.name,
        )


class FirstKey(KeyIssued):
    """POST /v1/invitations/{token}: the first key, and the member now active."""

    member: MemberRow


class OrgMade(KeyIssued):
    """POST /v1/signup/verify: the admin's key, the org's slug, the member, the console's code."""

    slug: str
    member: MemberRow
    code: str
    code_expires_at: float


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

    @classmethod
    def with_names(cls, key: ApiKey, names: dict[str, str]) -> Self:
        """The row, the maker named where the org still knows them."""
        is_a_persons = key.subject is not None
        return cls(
            fingerprint=key.hash,
            label=key.label,
            kind="person" if is_a_persons else "server",
            env=None if is_a_persons else key.env,
            name=key.name,
            created_by=None if key.created_by is None else names.get(key.created_by, key.created_by),
            created_at=key.created_at,
            last_used_at=key.last_used_at,
            revoked_at=key.revoked_at,
            scopes=sorted(key.scopes),
            expires_at=key.expires_at,
        )


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

    @classmethod
    def for_actor(cls, actor: Actor, slug: str | None) -> Self:
        """The actor as the endpoint answers."""
        person = actor.person
        return cls(
            org=actor.org,
            slug=slug,
            key_id=actor.key_id,
            label=actor.label,
            env=actor.env,
            scopes=sorted(actor.scopes),
            subject=None if person is None else person.id,
            name=None if person is None else person.name,
            email=None if person is None else person.email,
            operator=person is not None and person.operator,
            visiting=person is not None and person.org != actor.org,
            production=(actor.env is Env.production) if person is None else person.opens_production,
        )


class BrandRow(Row):
    """What the box's pages and emails are called and painted with."""

    name: str
    logo_url: str | None
    accent: str


class GatewayInfo(Row):
    """GET /.well-known/pinecall: what a sign-in page reads before anybody holds a key."""

    version: str
    signup: bool
    min_password: int
    mail: bool
    brand: BrandRow
    google: bool


# ── signing in ──


class SignIn(Schema):
    """POST /v1/login: an address and a password (and the org when several), or a code."""

    org: str | None = None
    email: str | None = None
    password: str | None = None
    code: str | None = None
    device: str | None = None


class SignInOrgs(Schema):
    """POST /v1/login/orgs."""

    email: str
    password: str


class SignInOrgRow(Row):
    """One org a password opens, and the person's role there."""

    org: str
    slug: str
    name: str
    role: Role


class SignInOrgList(Row):
    """POST /v1/login/orgs, the answer."""

    orgs: list[SignInOrgRow]


class OrgOfPersonRow(Row):
    """GET /v1/login/orgs, one org."""

    org: str
    slug: str | None
    name: str | None
    role: str
    status: MemberStatus
    here: bool
    member: bool


class OrgsOfPerson(Row):
    """GET /v1/login/orgs, the answer."""

    orgs: list[OrgOfPersonRow]


class SwitchOrg(Schema):
    """POST /v1/login/org."""

    org: str


class CodeMinted(Row):
    """A one-time code and when it dies, in epoch seconds."""

    code: str
    expires_at: float


class ForgotPassword(Schema):
    """POST /v1/login/reset."""

    email: str


class Empty(Row):
    """An answer whose status says everything: `{}`."""


class OpenPairing(Schema):
    """POST /v1/login/pairings."""

    device: str | None = None


class PairingStatus(Row):
    """GET /v1/login/pairings/{code}."""

    device: str | None
    expires_at: float
    answered: bool


class PairingApproved(Row):
    """POST /v1/login/pairings/{code}."""

    device: str | None
    org: str
    org_name: str


class KeyCollected(Row):
    """GET /v1/login/pairings/{code}/key."""

    key: str


# ── sign-up ──


class SignUp(Schema):
    """POST /v1/signup."""

    org: str
    name: str | None = None
    email: str
    person: str
    password: str
    device: str | None = None


class CodeMailed(Row):
    """POST /v1/signup, the answer: where the code went and when it dies; never the code."""

    email: str
    code_expires_at: float


class VerifySignUp(Schema):
    """POST /v1/signup/verify."""

    email: str
    code: str
    device: str | None = None


class ResendCode(Schema):
    """POST /v1/signup/resend."""

    email: str


# ── the org's identity provider ──


class PutSso(Schema):
    """PUT /v1/org/sso: the provider whole, its client secret included every time."""

    issuer: str
    client_id: str
    client_secret: str
    domains: list[str]
    role: Role | None = None
    required: bool = False


class SsoDomainProofRow(Row):
    """One domain of the org's SSO: the TXT record that proves it, and whether seen."""

    domain: str
    txt: str
    verified: bool


class SsoRow(Row):
    """GET /v1/org/sso: the org's provider, never its secret, and the redirect URI."""

    configured: bool
    issuer: str | None
    client_id: str | None
    domains: list[str]
    role: Role | None
    required: bool
    redirect_uri: str
    proofs: list[SsoDomainProofRow] = Field(default_factory=list[SsoDomainProofRow])


class DiscoverSso(Schema):
    """POST /v1/login/sso/discover."""

    email: str


class SsoOrgRow(Row):
    """An org that signs in an address's domain with its provider."""

    org: str
    slug: str
    name: str


class SsoOrgList(Row):
    """POST /v1/login/sso/discover, the answer."""

    orgs: list[SsoOrgRow]


# ── the org's mailbox ──


class PutMail(Schema):
    """PUT /v1/org/mail: the org's SMTP account, its password included every time."""

    host: str
    port: int
    security: Literal["starttls", "tls", "none"] = "starttls"
    username: str = ""
    password: str = ""
    sender: str = Field(alias="from")


class MailRow(Row):
    """GET /v1/org/mail: the mailbox, never its password, and how its last email went."""

    configured: bool
    host: str | None
    port: int | None
    security: str | None
    username: str | None
    sender: str | None = Field(alias="from", serialization_alias="from")
    verified_at: datetime | None
    last_error: str | None


class SendTestEmail(Schema):
    """POST /v1/org/mail/test."""

    to: str


class TestEmailSent(Row):
    """POST /v1/org/mail/test, the answer."""

    sent: bool
    error: str | None


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


class SsoRequired(Schema):
    """PUT /v1/ops/orgs/{named}/sso/required: whether a password may still open the org."""

    required: bool


class IssueOrgKey(Schema):
    """POST /v1/ops/orgs/{named}/keys: a key of the org, in an env, with scopes and an owner."""

    env: Env
    label: str | None = None
    scopes: list[KeyScope] | None = None
    subject: str | None = None
    name: str | None = None


class BoxMailRow(Row):
    """GET and PUT /v1/ops/mail: the box's mailbox and where it came from, never the password."""

    configured: bool
    source: Literal["stored", "environment"] | None
    host: str | None
    port: int | None
    security: str | None
    username: str | None
    sender: str | None = Field(alias="from", serialization_alias="from")
    verified_at: datetime | None
    last_error: str | None


class BoxProvider(Row):
    """One box-wide identity provider: whether it is wired, the client, the URI to register."""

    configured: bool
    client_id: str | None
    redirect_uri: str


class BoxSignIn(Row):
    """GET /v1/ops/signin: every provider the box could offer every org's people."""

    google: BoxProvider


class PutSignIn(Schema):
    """PUT /v1/ops/signin/google: the OAuth client the operator made for this gateway."""

    client_id: str
    client_secret: str


class PutBrand(Schema):
    """PUT /v1/ops/brand: a field left out keeps its value; an empty one goes to the default."""

    name: str | None = None
    logo_url: str | None = None
    accent: str | None = None
