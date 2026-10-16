"""An org's carrier accounts (Twilio, a SIP peer, WhatsApp at Meta), sealed; the box's Twilio."""

import json
import logging
from dataclasses import dataclass, replace

import httpx
from pydantic import ValidationError as PydanticValidationError
from sqlalchemy.ext.asyncio import AsyncSession

from pinecall_runtime.channels import service as channels
from pinecall_runtime.enums import CarrierKind
from pinecall_runtime.exceptions import (
    Conflict,
    NotFound,
    ServiceUnavailable,
    UpstreamError,
    ValidationError,
)
from pinecall_runtime.kit.crypto import Vault
from pinecall_runtime.providers import service as providers
from pinecall_runtime.telephony.models import Carrier
from pinecall_runtime.telephony.repository import CarrierRepository
from pinecall_runtime.telephony.schemas import (
    SealedCarrier,
    SipPeer,
    Termination,
    TwilioAccount,
    WhatsappAccount,
)
from pinecall_runtime.telephony.service import records, twilio

logger = logging.getLogger(__name__)

# The box's own Twilio account, sealed in box_settings as credentials/twilio.
BOX_ACCOUNT = "twilio"
NO_CARRIER = "the org has no carrier account: PUT /v1/carrier brings a Twilio account or a SIP peer"
NO_BOX_TWILIO = "this box buys no numbers: it has no Twilio account of its own. Bring a carrier and import one"


@dataclass(frozen=True, slots=True)
class CarrierAccount:
    """One account of the org at an outside party that holds its numbers."""

    org: str
    account: TwilioAccount | SipPeer | WhatsappAccount
    # Twilio only, written by provisioning: Twilio shows a credential's password once.
    outbound: Termination | None = None

    @property
    def id(self) -> str:
        """The account's own id: Twilio's SID, the peer's username, Meta's phone number id."""
        match self.account:
            case TwilioAccount():
                return self.account.account_sid
            case SipPeer():
                return self.account.username
            case WhatsappAccount():
                return self.account.phone_number_id

    @property
    def kind(self) -> CarrierKind:
        """Which kind of account it is."""
        return CarrierKind(self.account.kind)


async def carriers_of(session: AsyncSession, vault: Vault, org: str) -> list[CarrierAccount]:
    """The org's carrier accounts, oldest first, opened; one sealed under a lost key is skipped."""
    opened = (_open_carrier(vault, row) for row in await CarrierRepository(session).of_org(org))
    return [carrier for carrier in opened if carrier is not None]


async def carrier_named(session: AsyncSession, vault: Vault, org: str, account: str | None = None) -> CarrierAccount:
    """The account named, or the org's only one; NotFound or Conflict otherwise."""
    if account is not None:
        row = await CarrierRepository(session).get(org, account)
        found = None if row is None else _open_carrier(vault, row)
        if found is None:
            raise NotFound(f"the org has no carrier account {account}")
        return found
    carriers = await carriers_of(session, vault, org)
    if not carriers:
        raise NotFound(NO_CARRIER)
    if len(carriers) > 1:
        named = ", ".join(carrier.id for carrier in carriers)
        raise Conflict(f"the org has {len(carriers)} carrier accounts ({named}): name one of them")
    return carriers[0]


async def put_carrier(
    session: AsyncSession, vault: Vault, org: str, account: TwilioAccount | SipPeer | WhatsappAccount
) -> CarrierAccount:
    """Keep the account; bringing it again replaces its secret and keeps its termination."""
    kept = CarrierAccount(org=org, account=account)
    was = next((carrier for carrier in await carriers_of(session, vault, org) if carrier.id == kept.id), None)
    # The termination stays with the account it was made on: only a Twilio account holds one.
    if was is not None and was.account.kind == account.kind:
        kept = replace(kept, outbound=was.outbound)
    await seal_carrier(session, vault, kept)
    return kept


async def drop_carrier(session: AsyncSession, vault: Vault, org: str, account: str | None = None) -> str:
    """Forget the account; its numbers stay routed until each is let go."""
    gone = await carrier_named(session, vault, org, account)
    await CarrierRepository(session).drop(org, gone.id)
    return gone.id


async def seal_carrier(session: AsyncSession, vault: Vault, carrier: CarrierAccount) -> None:
    """Write the account sealed, its termination with it."""
    secret = SealedCarrier(account=carrier.account, outbound=carrier.outbound)
    await CarrierRepository(session).put(
        carrier.org,
        carrier.id,
        kind=carrier.kind,
        label=carrier.account.label,
        ciphertext=vault.seal(secret.model_dump_json()),
    )


async def box_twilio(session: AsyncSession, vault: Vault) -> TwilioAccount:
    """The box's own Twilio account, or ServiceUnavailable when it holds none."""
    credentials = (await providers.box_credentials(session, vault)).get(BOX_ACCOUNT)
    try:
        return TwilioAccount.model_validate(credentials)
    except PydanticValidationError:
        raise ServiceUnavailable(NO_BOX_TWILIO) from None


# A number the box bought lives in the box's account; an imported one in the account it came
# from; a hooked or typed one, or one whose account was dropped, in no account anyone knows.
async def twilio_account_of(session: AsyncSession, vault: Vault, org: str, number: str) -> str | None:
    """The Twilio account a call to the org's number must come from; None where none is known."""
    record = await records.record_of(session, org, number)
    if record is None:
        return None
    try:
        if record.route.managed:
            return (await box_twilio(session, vault)).account_sid
        if record.route.account is None:
            return None
        found = await carrier_named(session, vault, org, record.route.account)
    except (ServiceUnavailable, NotFound):
        return None
    return found.account.account_sid if isinstance(found.account, TwilioAccount) else None


async def put_box_twilio(session: AsyncSession, vault: Vault, account: TwilioAccount) -> None:
    """Keep the account the box buys numbers on, sealed; it replaces the one held."""
    await providers.put_box_credentials(session, vault, BOX_ACCOUNT, account.model_dump(mode="json"))


async def drop_box_twilio(session: AsyncSession) -> bool:
    """Forget it: the box buys no numbers from now on; whether it held one."""
    return await providers.drop_box_credentials(session, BOX_ACCOUNT)


# The box's own account, then each org's, an account two orgs brought counted once.
async def every_twilio_account(session: AsyncSession, vault: Vault) -> list[TwilioAccount]:
    """Every Twilio account the box or an org holds, once each."""
    found: dict[str, TwilioAccount] = {}
    # A box with no Twilio account of its own has only the orgs'.
    try:
        boxs = await box_twilio(session, vault)
        found[boxs.account_sid] = boxs
    except ServiceUnavailable:
        pass
    for row in await CarrierRepository(session).every():
        carrier = _open_carrier(vault, row)
        if carrier is not None and isinstance(carrier.account, TwilioAccount):
            found.setdefault(carrier.account.account_sid, carrier.account)
    return list(found.values())


# Twilio is the one carrier with an API the box drives; a peer is SIP terms and nothing more.
def control_of(http: httpx.AsyncClient, carrier: CarrierAccount) -> twilio.Twilio | None:
    """The account's API the box can list, point and provision numbers through, if it has one."""
    match carrier.account:
        case TwilioAccount():
            return twilio.twilio_of(http, carrier.account)
        case SipPeer() | WhatsappAccount():
            return None


def meta_of(carrier: CarrierAccount) -> WhatsappAccount | None:
    """The WhatsApp number at Meta the account is, if it is one."""
    return carrier.account if isinstance(carrier.account, WhatsappAccount) else None


async def verify_account(http: httpx.AsyncClient, account: TwilioAccount | SipPeer | WhatsappAccount) -> None:
    """Refuse an account its carrier does not open with what was given; a peer is not asked."""
    match account:
        case TwilioAccount():
            await twilio.verify(http, account)
        case WhatsappAccount():
            await _whatsapp_opens(http, account)
        case SipPeer():
            return


async def meta_token_for(session: AsyncSession, vault: Vault, org: str, phone_number_id: str) -> str | None:
    """The org's own Meta token for the number, else the box's, else None."""
    for carrier in await carriers_of(session, vault, org):
        account = carrier.account
        if isinstance(account, WhatsappAccount) and account.phone_number_id == phone_number_id:
            return account.access_token
    try:
        return (await channels.box_meta_app(session, vault)).access_token
    except ServiceUnavailable:
        return None


# Meta is asked for the number the id names, as the inbox asks it: a token that does not open it
# is refused here, in Meta's words, and not on the first message.
async def _whatsapp_opens(http: httpx.AsyncClient, account: WhatsappAccount) -> None:
    try:
        await channels.display_number(http, account.access_token, account.phone_number_id)
    except UpstreamError as refused:
        raise ValidationError(
            f"Meta does not open WhatsApp number {account.phone_number_id} with this token: {refused}"
        ) from refused


def _open_carrier(vault: Vault, row: Carrier) -> CarrierAccount | None:
    try:
        kept = SealedCarrier.model_validate(json.loads(vault.open(row.ciphertext)))
    except (ServiceUnavailable, PydanticValidationError, ValueError):
        logger.warning("org %s's carrier account %s is not one this box reads", row.org, row.account)
        return None
    return CarrierAccount(org=row.org, account=kept.account, outbound=kept.outbound)
