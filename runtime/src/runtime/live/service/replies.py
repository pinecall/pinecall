"""How a written conversation reaches its contact: WhatsApp through Meta, an SMS through Twilio."""

import logging
from dataclasses import dataclass
from typing import Protocol

import httpx
from sqlalchemy.ext.asyncio import AsyncSession

from runtime.actor import Scope
from runtime.enums import Channel
from runtime.exceptions import PinecallError
from runtime.live.parts import LiveParts
from runtime.providers import service as providers
from runtime.telephony import service as telephony
from runtime.telephony.models import Route as RouteRow
from runtime.whatsapp import service as whatsapp

logger = logging.getLogger(__name__)


class Reaches(Protocol):
    """One channel's way to a contact: a reply sent, their message marked read, what a voice note says."""

    async def send(self, to: whatsapp.Inbound, text: str) -> None:
        """Send the text to the contact from the number they wrote to; the channel's refusal raises."""
        ...

    async def mark_read(self, message: whatsapp.Inbound, *, typing: bool) -> None:
        """Tell the contact their message was read, and that a reply is being written when one is."""
        ...

    async def hear_note(self, message: whatsapp.Inbound) -> str | None:
        """What a voice note says; None for a message that carries none, or one that could not be heard."""
        ...


# Heard by the ears the org's calls hear with, on the same keys. The keys are read in a transaction
# that is over before the note is heard.
@dataclass(frozen=True, slots=True)
class Ears:
    """Whose keys a voice note is heard on, and where they are read."""

    live: LiveParts
    scope: Scope

    async def hear(self, media: whatsapp.Media) -> str | None:
        """What the audio says; None for audio that says nothing."""
        note = providers.read_note(media.data, media.mime_type)
        async with self.live.sessions.begin() as session_:
            keys = await providers.keys_of(session_, self.live.vault, self.scope)
            ears = providers.ears_for(providers.Asked(), await providers.get_catalog(session_), keys)
        return (await providers.transcribe(ears, note)).text or None


@dataclass(frozen=True, slots=True)
class ByWhatsapp:
    """Meta's Graph, on the number's token."""

    http: httpx.AsyncClient
    token: str
    ears: Ears

    async def send(self, to: whatsapp.Inbound, text: str) -> None:
        """Send the text through Meta, as several when it is long."""
        await whatsapp.send_text(self.http, self.token, to, text)

    async def mark_read(self, message: whatsapp.Inbound, *, typing: bool) -> None:
        """The two blue ticks, and "typing…" when a reply is being written."""
        await whatsapp.mark_read(self.http, self.token, message, typing=typing)

    async def hear_note(self, message: whatsapp.Inbound) -> str | None:
        """What a voice note says; None for one that could not be fetched or heard, or that says nothing."""
        if message.media_id is None:
            return None
        try:
            return await self.ears.hear(await whatsapp.read_media(self.http, self.token, message.media_id))
        except (PinecallError, httpx.HTTPError):
            logger.warning("whatsapp: a voice note to %s was not heard", message.number, exc_info=True)
            return None


@dataclass(frozen=True, slots=True)
class BySms:
    """Twilio's messages, on the account the number lives in."""

    http: httpx.AsyncClient
    account: telephony.TwilioAccount
    # Where Twilio says how each reply stands.
    status_to: str
    # None hears no audio: what an MMS carries is then dropped.
    ears: Ears | None = None

    async def send(self, to: whatsapp.Inbound, text: str) -> None:
        """Send the text from the number written to, as several when it is long."""
        await telephony.send_sms(self.http, self.account, to.number, to.caller, text, status_to=self.status_to)

    async def mark_read(self, message: whatsapp.Inbound, *, typing: bool) -> None:
        """Nothing: an SMS is neither marked read nor answered with a typing sign."""

    # An MMS's audio is the SMS network's voice note (an iPhone's "audio message" to a number that is
    # not on iMessage). A format the ears cannot read is said in the log, and the message says nothing.
    async def hear_note(self, message: whatsapp.Inbound) -> str | None:
        """What the audio of an MMS says; None for a message with none, or audio that could not be heard."""
        if message.media_id is None or self.ears is None:
            return None
        try:
            return await self.ears.hear(await telephony.read_sms_media(self.http, self.account, message.media_id))
        except (PinecallError, httpx.HTTPError):
            logger.warning("sms: the audio of an MMS to %s was not heard", message.number, exc_info=True)
            return None


# The one place that tells the two channels apart for a reply.
async def way_to(session_: AsyncSession, live: LiveParts, route: RouteRow, inbound: whatsapp.Inbound) -> Reaches | None:
    """How the contact who wrote is answered; None when the box holds nothing to answer with."""
    if inbound.channel is Channel.sms:
        account = await telephony.sms_account_of(session_, live.vault, route)
        status_to = telephony.sms_status_url(live.vault, live.settings.base_url, inbound.number)
        return (
            None if account is None else BySms(live.http, account, status_to, Ears(live, Scope(route.org, route.env)))
        )
    token = await telephony.meta_token_for(session_, live.vault, route.org, inbound.phone_number_id)
    return None if token is None else ByWhatsapp(live.http, token, Ears(live, Scope(route.org, route.env)))
