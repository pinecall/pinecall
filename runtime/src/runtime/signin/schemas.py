"""The bodies of the sign-in endpoints: login, codes, pairings, sign-up, the org's provider, Google, the gateway."""

import httpx
from pydantic import Field

from runtime.accounts.schemas import KeyIssued, MemberRow
from runtime.enums import MemberStatus, Role
from runtime.kit.schemas import EmailAddress, Row, Schema
from runtime.platform.schemas import BrandRow

# ── the routes a sentence or a redirect names ──

# Where each provider sends the browser back: the URI an operator or an org registers there.
SSO_CALLBACK = "/v1/login/sso/callback"
GOOGLE_CALLBACK = "/v1/login/google/callback"
# The console's pages a callback lands on: its sign-in, a waiting terminal's card, and where somebody
# Google vouched for and nobody knows names their workspace.
THE_CONSOLE = "/"
THE_CARD = "/cli"
THE_SIGNUP = "/signup"


# The token Turnstile's widget yields, carried by every request a stranger makes that costs the box
# something: an account kept, an email mailed. Never a password, which a phone or a terminal types too
# (the password throttle holds those). Ignored where the box has no Turnstile.
type TurnstileToken = str | None


class Empty(Row):
    """An answer whose status says everything: `{}`."""


# ── the gateway ──


class GatewayInfo(Row):
    """GET /.well-known/pinecall: what a sign-in page reads before anybody holds a key."""

    version: str
    signup: bool
    min_password: int
    mail: bool
    brand: BrandRow
    google: bool
    # Turnstile's site key where the operator set one: the page draws the widget, and a sign-up, its
    # resend and a forgotten password carry its token. None, and no endpoint asks for one.
    turnstile: str | None


# ── signing in ──


class SignIn(Schema):
    """POST /v1/login: an address and a password (and the org when several), or a code."""

    org: str | None = None
    email: EmailAddress | None = None
    password: str | None = None
    code: str | None = None
    device: str | None = None


class SignInOrgs(Schema):
    """POST /v1/login/orgs."""

    email: EmailAddress
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

    email: EmailAddress
    turnstile: TurnstileToken = None


# ── pairings ──


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
    """POST /v1/signup: the org's slug, or its name alone and the slug is made of it."""

    org: str | None = None
    name: str | None = None
    email: EmailAddress
    person: str
    password: str
    device: str | None = None
    turnstile: TurnstileToken = None


class GoogleSignUp(Schema):
    """POST /v1/signup/google: the token Google's callback handed the page, and the workspace's name or slug."""

    token: str
    org: str | None = None
    name: str | None = None
    device: str | None = None


class GoogleNewcomer(Row):
    """GET /v1/signup/google/{token}: whom Google vouched for, whom nobody here knows yet."""

    email: str
    person: str


class CodeMailed(Row):
    """POST /v1/signup, the answer: where the code went and when it dies; never the code."""

    email: str
    code_expires_at: float


class VerifySignUp(Schema):
    """POST /v1/signup/verify."""

    email: EmailAddress
    code: str
    device: str | None = None


class ResendCode(Schema):
    """POST /v1/signup/resend."""

    email: EmailAddress
    turnstile: TurnstileToken = None


class OrgMade(KeyIssued):
    """POST /v1/signup/verify: the admin's key, the org's slug, the member, the console's code."""

    slug: str
    member: MemberRow
    code: str
    code_expires_at: float


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


class SsoRequired(Schema):
    """PUT /v1/ops/orgs/{named}/sso/required: whether a password may still open the org."""

    required: bool


class DiscoverSso(Schema):
    """POST /v1/login/sso/discover."""

    email: EmailAddress


class SsoOrgRow(Row):
    """An org that signs in an address's domain with its provider."""

    org: str
    slug: str
    name: str


class SsoOrgList(Row):
    """POST /v1/login/sso/discover, the answer."""

    orgs: list[SsoOrgRow]


# ── Google, for every org's people ──


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


# ── where a provider's callback leaves the browser ──


class Landed(Row):
    """A callback's outcome as the redirect that carries it: signed in, sent to name a workspace, or told why not."""

    login: str | None = None
    pairing: str | None = None
    refused: str | None = None
    newcomer: str | None = None

    # A login code goes to the console, or to the terminal's card when a terminal waits; a newcomer to
    # the sign-up, with the terminal's code if one waits; a refusal to the console's sign-in, which says why.
    @property
    def location(self) -> str:
        """The console's page this outcome is read on, and what it is handed in the query."""
        if self.login is not None and self.pairing is not None:
            return f"{THE_CARD}?{httpx.QueryParams({'c': self.pairing, 'login': self.login})}"
        if self.login is not None:
            return f"{THE_CONSOLE}?{httpx.QueryParams({'login': self.login})}"
        if self.newcomer is not None:
            asked = {"google": self.newcomer} if self.pairing is None else {"google": self.newcomer, "c": self.pairing}
            return f"{THE_SIGNUP}?{httpx.QueryParams(asked)}"
        return f"{THE_CONSOLE}?{httpx.QueryParams({'refused': self.refused or ''})}"
