"""Continue with Google: the box's own OAuth client, a sign-in through it, and whom a vouched address signs in as."""

from collections.abc import Callable, Mapping
from dataclasses import asdict, dataclass
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from runtime.accounts import service as accounts
from runtime.enums import MemberStatus
from runtime.exceptions import Forbidden, NotFound, PinecallError, ValidationError
from runtime.kit.crypto import Vault
from runtime.kit.time import epoch
from runtime.platform import service as platform
from runtime.signin.repository import SsoRepository
from runtime.signin.service.codes import LoginCodes, holder_of_member
from runtime.signin.service.oidc import Answer, Handshake, Landing, NoSuchSignIn, Oidc
from runtime.signin.service.one_time import Kind, OneTimeSecrets

ISSUER = "https://accounts.google.com"
# Google asks which of its accounts, rather than signing in whichever the browser used last.
PROMPT = "select_account"
# What Google says when the person closed its page or said no.
CANCELLED = "access_denied"
# Somebody Google vouched for whom nobody knows, between its callback and the workspace they name.
NEWCOMER = Kind("gs_", 10 * 60.0)


class NoGoogle(NotFound):
    """The platform keeps no Google client."""

    def __init__(self) -> None:
        super().__init__(
            "this platform has no Google sign-in: its operator stores an OAuth client at /v1/ops/signin/google"
        )


@dataclass(frozen=True, slots=True)
class GoogleClient:
    """The OAuth client the operator made at Google for this platform, its secret opened."""

    client_id: str
    client_secret: str
    issuer: str = ISSUER

    def __post_init__(self) -> None:
        if not self.client_id.strip() or not self.client_secret.strip():
            raise ValidationError("a Google client carries its id and its secret")


@dataclass(frozen=True, slots=True)
class Vouched:
    """Whom Google vouched for: a verified address, and the name to seat them under."""

    email: str
    person: str


@dataclass(frozen=True, slots=True)
class Newcomer:
    """Somebody Google vouched for whom nobody here knows: their address, their name, a terminal waiting."""

    email: str
    person: str
    pairing: str | None = None


def _load_newcomer(value: Mapping[str, Any]) -> Newcomer:
    return Newcomer(email=str(value["email"]), person=str(value["person"]), pairing=value.get("pairing"))


class Newcomers(OneTimeSecrets[Newcomer]):
    """The people Google vouched for whom nobody here knows yet, each for ten minutes."""

    def __init__(
        self, sessions: async_sessionmaker[AsyncSession], vault: Vault, clock: Callable[[], float] = epoch
    ) -> None:
        super().__init__(NEWCOMER, sessions, vault, load=_load_newcomer, dump=asdict, clock=clock)


@dataclass(frozen=True, slots=True)
class BoxWiring:
    """The box's Google client as its operator's screen shows it: the id, never the secret, the URI to register."""

    client_id: str | None
    redirect_uri: str

    @property
    def configured(self) -> bool:
        """Whether the operator stored a client."""
        return self.client_id is not None


# ── the box's client ──


def _load_client_id(value: Mapping[str, Any]) -> str:
    return str(value["client_id"])


def _dump_client_id(client_id: str) -> dict[str, Any]:
    return {"client_id": client_id}


# The box_settings row the client is kept in: its id in the value, its secret sealed beside it.
GOOGLE_CLIENT: platform.Setting[str] = platform.Setting("signin.google", _load_client_id, _dump_client_id)


async def find_client(session: AsyncSession, vault: Vault) -> GoogleClient | None:
    """The platform's Google client; None where the operator stored none."""
    kept = await platform.find_sealed_setting(session, GOOGLE_CLIENT)
    if kept is None:
        return None
    client_id, sealed = kept
    return GoogleClient(client_id=client_id, client_secret=vault.open(sealed))


async def client_id_of(session: AsyncSession) -> str | None:
    """The client's id alone, opening no secret: what the operator's screen and the sign-in page read."""
    return await platform.find_setting(session, GOOGLE_CLIENT)


async def wiring_of(session: AsyncSession, *, redirect_uri: str) -> BoxWiring:
    """The box's Google client as its operator reads it, and the redirect URI to register at Google."""
    return BoxWiring(await client_id_of(session), redirect_uri)


async def put_client(session: AsyncSession, vault: Vault, client: GoogleClient, *, redirect_uri: str) -> BoxWiring:
    """Keep the client whole, the secret sealed beside its id: "Continue with Google" shows on every page."""
    client_id = client.client_id.strip()
    await platform.put_setting(session, GOOGLE_CLIENT, client_id, ciphertext=vault.seal(client.client_secret.strip()))
    return BoxWiring(client_id, redirect_uri)


async def delete_client(session: AsyncSession) -> None:
    """Forget the client: the button goes from every page; NotFound where there was none."""
    if not await platform.delete_setting(session, GOOGLE_CLIENT):
        raise NotFound("this box keeps no Google client")


# ── signing in through it ──


async def begin(
    session: AsyncSession,
    vault: Vault,
    oidc: Oidc,
    attempts: platform.AttemptThrottle,
    *,
    client: str,
    redirect_uri: str,
    pairing: str | None,
) -> str:
    """Where the browser goes to sign in at Google, with a state, a nonce and a PKCE challenge."""
    at_google = await find_client(session, vault)
    if at_google is None:
        raise NoGoogle()
    await attempts.check(f"{client} google", "sign-ins from here")
    return await oidc.begin(session, at_google, redirect_uri, org=None, pairing=pairing, prompt=PROMPT)


async def exchange_code(oidc: Oidc, client: GoogleClient, begun: Handshake, code: str) -> Vouched:
    """The address Google signed in, refused unless Google verified it, from the code it returned."""
    claims = await oidc.claims_for_code(client, begun, code)
    return Vouched(claims.email, (claims.name or "").strip() or claims.email.partition("@")[0])


# The oldest seat they took, else the oldest they were invited to, seated: Google proved the address,
# as an org's own provider does, so `accounts.seat_vouched` ends whatever was set while it was unproven.
# An org that signs in only with its own provider is passed over. A password a proven person also has
# is left as it is: either way in opens the same account.
async def member_for(session: AsyncSession, cache: accounts.KeyCache, email: str) -> accounts.Membership | None:
    """The membership a vouched address signs in to; None for an address nobody here knows."""
    person = await accounts.find_person(session, email)
    if person is None:
        return None
    seats = await accounts.memberships_of(session, person)
    if not seats:
        return None
    enabled = [seat for seat in seats if seat.status is not MemberStatus.disabled]
    if not enabled:
        raise Forbidden(f"{email} is disabled in {await accounts.slug_of(session, seats[0].org)}")
    taken = [seat for seat in enabled if seat.status is MemberStatus.active] or enabled
    providers = SsoRepository(session)
    for seat in taken:
        if not await providers.is_required(seat.org):
            seated = await accounts.seat_vouched(session, cache, accounts.Membership(seat, person))
            if seated is not None:
                return seated
    slug = await accounts.slug_of(session, taken[0].org)
    raise Forbidden(f"{slug} signs in with its identity provider: open /v1/login/sso?org={slug}")


# What refuses a person here is shown to them by the console, as an org's own provider's callback does.
async def finish(
    session: AsyncSession,
    cache: accounts.KeyCache,
    vault: Vault,
    oidc: Oidc,
    codes: LoginCodes,
    newcomers: Newcomers,
    answer: Answer,
    *,
    signups_open: bool,
) -> Landing:
    """The whole callback: signed in with a login code, sent to name a workspace, or told why not."""
    begun = await oidc.resume(answer.state)
    # An org's own provider began with its org named, and finishes at its own callback.
    if begun.org is not None:
        raise NoSuchSignIn()
    if answer.error == CANCELLED:
        return Landing(refused="the sign-in with Google was not finished")
    if answer.error is not None:
        return Landing(refused=f"Google refused the sign-in: {answer.error}")
    if not answer.code:
        return Landing(refused="Google sent no authorization code back")
    try:
        at_google = await find_client(session, vault)
        if at_google is None:
            raise NoGoogle()
        vouched = await exchange_code(oidc, at_google, begun, answer.code)
        membership = await member_for(session, cache, vouched.email)
    except PinecallError as refusal:
        return Landing(refused=str(refusal))
    if membership is not None:
        minted = await codes.mint_on(session, holder_of_member(membership))
        return Landing(login=minted.code, pairing=begun.pairing)
    if not signups_open:
        return Landing(
            refused=(
                f"nobody here answers to {vouched.email}, and this platform takes no sign-ups: "
                "ask an admin of your workspace to invite you"
            )
        )
    kept = await newcomers.mint_on(session, Newcomer(vouched.email, vouched.person, begun.pairing))
    return Landing(newcomer=kept.code, pairing=begun.pairing)
