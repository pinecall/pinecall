"""SMS through Twilio: the address a number's messages are posted to, a message read off it, a reply sent, a receipt."""

import logging
from collections.abc import Mapping

import httpx
from sqlalchemy.ext.asyncio import AsyncSession

from runtime.enums import Channel
from runtime.exceptions import Conflict, Forbidden, NotFound, ServiceUnavailable
from runtime.kit.crypto import Vault
from runtime.kit.text import cut_in_parts
from runtime.telephony.models import Route
from runtime.telephony.repository import RouteRepository
from runtime.telephony.service import accounts, twilio
from runtime.telephony.service.carrier import Carrier, Step
from runtime.telephony.service.twilio import TwilioAccount
from runtime.telephony.service.twilio_carrier import TwilioCarrier
from runtime.whatsapp import service as whatsapp

logger = logging.getLogger(__name__)

PATH = "/v1/sms/twilio"
# What a number's mark is the vault's on.
MARK_OF = "sms of "
# A post of Twilio's is a few hundred bytes.
LONGEST_POST = 64 * 1024
# What Twilio is answered so that it says nothing to the contact itself: the reply is the agent's.
NOTHING_TO_SAY = '<?xml version="1.0" encoding="UTF-8"?><Response></Response>'
# Twilio takes 1,600 characters a message (twilio.com/docs/messaging/api/message-resource); a
# longer reply goes out as several.
LONGEST_TEXT = 1600
# What a number newly bought posts to, which is nobody's: it is pointed here without being asked.
TWILIOS_OWN = "https://demo.twilio.com/"
# The word Twilio says of a message nobody will get, with the code that says why.
FAILED = frozenset({"failed", "undelivered"})


# Twilio signs a webhook with the account's auth token, and an org brings an API key, which signs
# nothing. So the address itself is the proof: it carries the vault's mark on the number, set on the
# number at Twilio by this box and known to nobody who cannot read that account's numbers.
def sms_hook_url(vault: Vault, base_url: str, number: str) -> str:
    """The address Twilio posts the number's messages to."""
    return f"{base_url}{PATH}/{vault.sign(MARK_OF + number)}"


def sms_status_url(vault: Vault, base_url: str, number: str) -> str:
    """The address Twilio posts to as a reply from the number moves."""
    return f"{sms_hook_url(vault, base_url, number)}/status"


def refuse_another_mark(vault: Vault, number: str, mark: str) -> None:
    """Forbidden unless the address is the one this box gave Twilio for the number."""
    if not vault.is_signed(MARK_OF + number, mark):
        raise Forbidden("this is not the address this box gave Twilio for that number")


# ── a number's messages pointed here ──


def refuse_what_sends_no_sms(carrier: Carrier | None) -> TwilioCarrier:
    """The Twilio account an SMS number lives in; Conflict for any other, or none."""
    if not isinstance(carrier, TwilioCarrier):
        raise Conflict(
            "SMS comes through a Twilio account, which sends and receives a number's messages: `pinecall "
            "carriers add twilio` first, then `pinecall numbers import <number> --channel sms`"
        )
    return carrier


# Where the number's messages go now is another service's when it is neither empty, Twilio's own
# placeholder nor this box: taking them is said, never done by the way.
async def survey_messages(
    http: httpx.AsyncClient, account: TwilioAccount, url: str, number: str, *, move: bool
) -> list[Step]:
    """The step that has Twilio post the number's messages here, or that it already does."""
    api = twilio.twilio_of(http, account)
    owned = await api.find_number(number)
    if owned is None:
        raise NotFound(f"{number} is not a number of Twilio account {api.sid}")
    taken = owned.sms_url and owned.sms_url != url and not owned.sms_url.startswith(TWILIOS_OWN)
    if taken and not move:
        raise Conflict(
            f"{number}'s messages go to {owned.sms_url} now: pointing them here takes them off there, so say move"
        )

    async def point() -> None:
        await api.point_messages(owned.sid, url)

    return [Step(f"twilio: {number}'s messages posted to this box", stands=owned.sms_url == url, write=point)]


# ── a message in, a reply out ──


def read_message(form: Mapping[str, str]) -> whatsapp.Inbound:
    """One message as Twilio posts it: who wrote, to which number, what."""
    return whatsapp.Inbound(
        number=form.get("To", ""),
        phone_number_id=form.get("AccountSid", ""),
        wa_id=form.get("From", "").lstrip("+"),
        name=None,
        message_id=form.get("MessageSid") or form.get("SmsSid") or "",
        kind="text",
        text=form.get("Body") or None,
        channel=Channel.sms,
    )


def read_receipt(form: Mapping[str, str]) -> whatsapp.Receipt:
    """Where a reply stands as Twilio posts it: `From` is the box's number, `To` the contact."""
    status = form.get("MessageStatus") or form.get("SmsStatus") or ""
    code = form.get("ErrorCode")
    return whatsapp.Receipt(
        number=form.get("From", ""),
        phone_number_id=form.get("AccountSid", ""),
        wa_id=form.get("To", "").lstrip("+"),
        message_id=form.get("MessageSid") or form.get("SmsSid") or "",
        status=status,
        error=f"Twilio error {code}" if status in FAILED and code else None,
        channel=Channel.sms,
    )


async def sms_account_of(session: AsyncSession, vault: Vault, route: Route) -> TwilioAccount | None:
    """The Twilio account an SMS route's replies go out on: the org's own, or the box's for a number it bought."""
    try:
        if route.account is not None:
            found = await accounts.get_carrier(session, vault, route.org, route.account)
            return found.account if isinstance(found, TwilioCarrier) else None
        return await accounts.box_twilio(session, vault)
    except (NotFound, ServiceUnavailable):
        return None


# A number the box bought lives in the box's account: its SMS route names no account, as its phone's does not.
async def is_bought_here(session: AsyncSession, org: str, number: str) -> bool:
    """Whether the org's number is one the box bought on its own account."""
    on_the_phone = await RouteRepository(session).find(org, number, Channel.phone)
    return on_the_phone is not None and on_the_phone.route.managed


async def send_sms(
    http: httpx.AsyncClient, account: TwilioAccount, sender: str, to: str, text: str, *, status_to: str | None
) -> None:
    """Send the text to the contact from the number they wrote to, as several when it is long."""
    api = twilio.twilio_of(http, account)
    for part in cut_in_parts(text, LONGEST_TEXT):
        await api.send_message(sender, to, part, status_to=status_to)


# ── what the webhook is handed ──


async def receive(threads: whatsapp.Threads, message: whatsapp.Inbound) -> str:
    """The message onto its contact's conversation; what Twilio is answered. 503 while another post reads it."""
    if not await threads.receive(message):
        raise ServiceUnavailable("this message is being read by another delivery: send it again")
    return NOTHING_TO_SAY


async def note(threads: whatsapp.Threads, receipt: whatsapp.Receipt) -> str:
    """Where a reply stands, said on its contact's open conversation; what Twilio is answered."""
    if receipt.message_id and receipt.status:
        await threads.note(receipt)
    return NOTHING_TO_SAY
