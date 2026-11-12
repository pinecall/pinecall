"""An org's carrier accounts, sealed and opened by their kind, and the account the box buys numbers on."""

import json
import logging
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any

import httpx
from sqlalchemy.ext.asyncio import AsyncSession

from runtime.exceptions import Conflict, NotFound, ServiceUnavailable, ValidationError
from runtime.kit.crypto import Vault
from runtime.kit.text import a_mapping
from runtime.kit.time import now
from runtime.platform import service as platform
from runtime.postgres import BoxSession
from runtime.providers import service as providers
from runtime.scoping import box_wide
from runtime.telephony.models import Carrier as CarrierRow
from runtime.telephony.models import CarrierKind
from runtime.telephony.repository import CarrierRepository, RouteRepository
from runtime.telephony.service import networks, twilio
from runtime.telephony.service.carrier import Carrier
from runtime.telephony.service.sip_peer import SipPeer
from runtime.telephony.service.twilio import TwilioAccount
from runtime.telephony.service.twilio_carrier import TwilioCarrier, dump_account, read_account
from runtime.telephony.service.whatsapp_number import WhatsappNumber
from runtime.whatsapp import service as whatsapp

logger = logging.getLogger(__name__)

# The box's own Twilio account, sealed in box_settings as credentials/twilio, beside the vendors' keys:
# the release before 2026-11 reads the same row, so it stays under that name until that release is gone.
BOX_ACCOUNT = "twilio"

# The one place that reads which kind an account is: a new kind is a module, and a line here.
CARRIERS: dict[CarrierKind, type[Carrier]] = {
    CarrierKind.twilio: TwilioCarrier,
    CarrierKind.sip: SipPeer,
    CarrierKind.whatsapp: WhatsappNumber,
}


@dataclass(frozen=True, slots=True)
class CarrierListed:
    """An account of the org as it is listed: named, never its secret, with the networks it asked 5060 opened to."""

    kind: str
    account: str
    label: str
    # A SIP peer's networks, each waiting, approved or refused; none for an account that names none.
    networks: Sequence[networks.NetworkListed]


# ── an org's accounts ──


# A row sealed under a lost key, or one this build no longer reads, is skipped and said: one stale row
# must not take the org's other accounts with it. Its numbers are admitted from nowhere until the
# account is brought again (`carrier.fence_route`).
def carrier_of(vault: Vault, row: CarrierRow) -> Carrier | None:
    """The account a row seals, opened as its kind; None for one this box does not read."""
    try:
        kept: object = json.loads(vault.open(row.ciphertext))
        if not a_mapping(kept):
            raise ValueError("the row seals no object")
        account, outbound = kept.get("account"), kept.get("outbound")
        if not a_mapping(account) or (outbound is not None and not a_mapping(outbound)):
            raise ValueError("the row seals no account")
        return CARRIERS[row.kind].read(row.org, account, outbound)
    except (ServiceUnavailable, ValueError):
        logger.warning("org %s's carrier account %s is not one this box reads", row.org, row.account)
        return None


def read_carrier(org: str, brought: Mapping[str, Any]) -> Carrier:
    """The account a body brings, opened as its kind; ValidationError when it is not one."""
    kind = str(brought.get("kind"))
    try:
        return CARRIERS[CarrierKind(kind)].read(org, brought, None)
    except ValueError as wrong:
        raise ValidationError(f"this is no {kind} account: {wrong}") from None


async def list_carriers(session: AsyncSession, vault: Vault, org: str) -> list[Carrier]:
    """The org's carrier accounts, oldest first, opened; one sealed under a lost key is skipped."""
    opened = (carrier_of(vault, row) for row in await CarrierRepository(session).list_of_org(org))
    return [carrier for carrier in opened if carrier is not None]


async def get_carrier(session: AsyncSession, vault: Vault, org: str, account: str | None = None) -> Carrier:
    """The account named, or the org's only one; NotFound or Conflict otherwise."""
    if account is not None:
        row = await CarrierRepository(session).find(org, account)
        found = None if row is None else carrier_of(vault, row)
        if found is None:
            raise NotFound(f"the org has no carrier account {account}")
        return found
    carriers = await list_carriers(session, vault, org)
    if not carriers:
        raise NotFound("the org has no carrier account: PUT /v1/carrier brings a Twilio account or a SIP peer")
    if len(carriers) > 1:
        named = ", ".join(carrier.id for carrier in carriers)
        raise Conflict(f"the org has {len(carriers)} carrier accounts ({named}): name one of them")
    return carriers[0]


async def describe_carrier(session: AsyncSession, carrier: Carrier) -> CarrierListed:
    """The account as the org's list shows it, with the networks it asked for."""
    asked = await networks.list_of_source(session, carrier.org, carrier.id)
    return CarrierListed(kind=carrier.kind.value, account=carrier.id, label=carrier.label, networks=asked)


async def describe_carriers(session: AsyncSession, vault: Vault, org: str) -> list[CarrierListed]:
    """Every account of the org, oldest first, as its list shows them."""
    return [await describe_carrier(session, carrier) for carrier in await list_carriers(session, vault, org)]


async def put_carrier(session: AsyncSession, vault: Vault, brought: Carrier) -> Carrier:
    """Keep the account; bringing it again replaces its secret and keeps what the box made on it."""
    carriers = await list_carriers(session, vault, brought.org)
    was = next((carrier for carrier in carriers if carrier.id == brought.id), None)
    kept = brought if was is None else brought.keep_from(was)
    await seal_carrier(session, vault, kept)
    return kept


async def delete_carrier(session: AsyncSession, vault: Vault, org: str, account: str | None = None) -> str:
    """Forget the account; its numbers stay routed until each is let go."""
    gone = await get_carrier(session, vault, org, account)
    await CarrierRepository(session).delete_of(org, gone.id)
    return gone.id


async def seal_carrier(session: AsyncSession, vault: Vault, carrier: Carrier) -> None:
    """Write the account sealed, with what the box made on it."""
    await CarrierRepository(session).put(
        carrier.org,
        carrier.id,
        kind=carrier.kind,
        label=carrier.label,
        ciphertext=vault.seal(json.dumps(carrier.dump())),
        at=now(),
    )


# A number the box bought lives in the box's account; an imported one in the account it came
# from; a hooked or typed one, or one whose account was let go, in no account anyone knows.
async def twilio_account_of(session: AsyncSession, vault: Vault, org: str, number: str) -> str | None:
    """The Twilio account a call to the org's number must come from; None where none is known."""
    numbered = await RouteRepository(session).find(org, number)
    if numbered is None:
        return None
    route = numbered.route
    try:
        if route.managed:
            return (await box_twilio(session, vault)).account_sid
        if route.account is None:
            return None
        found = await get_carrier(session, vault, org, route.account)
    except (ServiceUnavailable, NotFound):
        return None
    return found.id if isinstance(found, TwilioCarrier) else None


# WhatsApp's replies go out with the org's own token for the number, else the box's Meta app's.
async def meta_token_for(session: AsyncSession, vault: Vault, org: str, phone_number_id: str) -> str | None:
    """The org's own Meta token for the number, else the box's, else None."""
    for carrier in await list_carriers(session, vault, org):
        if isinstance(carrier, WhatsappNumber) and carrier.phone_number_id == phone_number_id:
            return carrier.access_token
    try:
        return (await whatsapp.box_meta_app(session, vault)).access_token
    except ServiceUnavailable:
        return None


# ── the account the box buys numbers on ──


async def find_box_twilio(session: AsyncSession, vault: Vault) -> TwilioAccount | None:
    """The box's own Twilio account, or None when it holds none it can read."""
    credentials = (await providers.box_credentials(session, vault)).get(BOX_ACCOUNT)
    if not a_mapping(credentials):
        return None
    try:
        return read_account(credentials)
    except ValueError:
        return None


async def box_twilio(session: AsyncSession, vault: Vault) -> TwilioAccount:
    """The box's own Twilio account, or ServiceUnavailable when it holds none."""
    account = await find_box_twilio(session, vault)
    if account is None:
        raise ServiceUnavailable(
            "this box buys no numbers: it has no Twilio account of its own. Bring a carrier and import one"
        )
    return account


async def sells_numbers(session: AsyncSession, vault: Vault) -> bool:
    """Whether the box sells numbers: it holds an account to buy them on."""
    return await find_box_twilio(session, vault) is not None


async def get_numbers_account(session: AsyncSession, vault: Vault) -> TwilioAccount:
    """The account the box buys numbers on, for its operator; NotFound when it holds none."""
    account = await find_box_twilio(session, vault)
    if account is None:
        raise NotFound("this box holds no Twilio account to buy numbers on: PUT one here")
    return account


# Tried against Twilio before it is kept, as an org's account is: a pair Twilio refuses is never
# the account a purchase fails on later.
async def put_box_twilio(
    session: BoxSession, vault: Vault, http: httpx.AsyncClient, account: TwilioAccount
) -> TwilioAccount:
    """Keep the account the box buys numbers on, verified, sealed; it replaces the one held."""
    await twilio.verify(http, account)
    await providers.put_box_credentials(session, vault, BOX_ACCOUNT, dump_account(account))
    return account


def _no_value(_value: Mapping[str, Any]) -> None:
    return None


def _empty(_value: None) -> dict[str, Any]:
    return {}


# The row the account is sealed in, as providers writes it: `providers.drop_box_key` forgets a
# vendor's key and refuses a name that is no vendor of a call, so this one row is forgotten by its name.
BOX_TWILIO_ROW: platform.Setting[None] = platform.Setting(f"credentials/{BOX_ACCOUNT}", _no_value, _empty)


async def delete_box_twilio(session: BoxSession) -> None:
    """Forget it: the box buys no numbers from now on, and the ones it bought keep ringing."""
    if not await platform.delete_setting(session, BOX_TWILIO_ROW):
        raise NotFound("this box holds no Twilio account to buy numbers on: PUT one here")


# The box's own account, then each org's, an account two orgs brought counted once.
async def list_twilio_accounts(session: AsyncSession, vault: Vault) -> list[TwilioAccount]:
    """Every Twilio account the box or an org holds, once each."""
    found: dict[str, TwilioAccount] = {}
    boxs = await find_box_twilio(session, vault)
    if boxs is not None:
        found[boxs.account_sid] = boxs
    with box_wide():
        rows = await CarrierRepository(session).list_every()
    for row in rows:
        carrier = carrier_of(vault, row)
        if isinstance(carrier, TwilioCarrier):
            found.setdefault(carrier.account.account_sid, carrier.account)
    return list(found.values())
