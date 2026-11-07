"""Continue with Google: the platform's own OAuth client, and whom an address Google vouched for signs in as."""

from dataclasses import dataclass

import httpx
from sqlalchemy.ext.asyncio import AsyncSession

from pinecall_runtime.accounts.models import Member
from pinecall_runtime.accounts.repository import SsoRepository
from pinecall_runtime.accounts.service import members, orgs, sso
from pinecall_runtime.accounts.service.signin import Handshake
from pinecall_runtime.enums import MemberStatus
from pinecall_runtime.exceptions import Forbidden, NotFound, ValidationError
from pinecall_runtime.kit.crypto import Vault
from pinecall_runtime.platform import service as platform

ISSUER = "https://accounts.google.com"
CALLBACK = "/v1/login/google/callback"
SETTING = "signin.google"
# Google asks which of its accounts, rather than signing in whichever the browser used last.
PROMPT = "select_account"


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


async def get_client(session: AsyncSession, vault: Vault) -> GoogleClient | None:
    """The platform's Google client; None where the operator stored none."""
    kept = await platform.get_sealed_setting(session, SETTING)
    if kept is None:
        return None
    value, sealed = kept
    return GoogleClient(client_id=str(value["client_id"]), client_secret=vault.open(sealed))


async def client_id_of(session: AsyncSession) -> str | None:
    """The client's id alone, opening no secret: what the operator's screen and the floor read."""
    value = await platform.get_setting(session, SETTING)
    return None if value is None else str(value["client_id"])


async def put_client(session: AsyncSession, vault: Vault, client: GoogleClient) -> None:
    """Keep the client whole, the secret sealed beside its id."""
    await platform.put_setting(
        session, SETTING, {"client_id": client.client_id.strip()}, ciphertext=vault.seal(client.client_secret.strip())
    )


async def delete_client(session: AsyncSession) -> bool:
    """Forget the client: the button goes from every page; whether there was one."""
    return await platform.delete_setting(session, SETTING)


async def vouched_for(http: httpx.AsyncClient, client: GoogleClient, begun: Handshake, code: str) -> Vouched:
    """The address Google signed in, refused unless Google verified it, from the code it returned."""
    claims = await sso.claims_for_code(http, client, begun, code)
    email = claims.email.strip().lower()
    return Vouched(email, (claims.name or "").strip() or email.partition("@")[0])


async def member_for(session: AsyncSession, email: str) -> Member | None:
    """
    The membership a vouched address signs in to; None for an address nobody here knows.

    The oldest it took, else the oldest it was invited to, seated — Google proved the address, as
    an org's own provider does — passing over an org that signs in only with its own provider. A
    password the person also has is left as it is: either way in opens the same account.
    """
    rows = await members.memberships_of(session, email)
    if not rows:
        return None
    enabled = [row for row in rows if row.status is not MemberStatus.disabled]
    if not enabled:
        raise Forbidden(f"{email} is disabled in {await orgs.slug_of(session, rows[0].org)}")
    taken = [row for row in enabled if row.status is MemberStatus.active] or enabled
    providers = SsoRepository(session)
    for row in taken:
        if not await providers.is_required(row.org):
            seated = await members.seat_vouched(session, row)
            if seated is not None:
                return seated
    slug = await orgs.slug_of(session, taken[0].org)
    raise Forbidden(f"{slug} signs in with its identity provider: open /v1/login/sso?org={slug}")
