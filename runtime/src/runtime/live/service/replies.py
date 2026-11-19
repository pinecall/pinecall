"""How a written conversation reaches its contact: WhatsApp through Meta, an SMS through Twilio, an email by SMTP."""

import logging
from dataclasses import dataclass
from typing import Protocol

import httpx
from sqlalchemy.ext.asyncio import AsyncSession

from runtime.actor import Scope
from runtime.agents import service as agents
from runtime.enums import Channel
from runtime.exceptions import PinecallError
from runtime.live.parts import LiveParts
from runtime.providers import service as providers
from runtime.providers.catalog import Catalog
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


# Heard by the ears the agent's calls hear with, on the same keys: the ones for the languages its
# callers speak, where it says them. Until 2026-11-18 a note was heard by the default's ears told no
# language, and one in Arabic came back as English that sounds alike. The keys and the agent are
# read in a transaction that is over before the note is heard.
@dataclass(frozen=True, slots=True)
class Ears:
    """Whose keys a voice note is heard on, the agent it was sent to, and where they are read."""

    live: LiveParts
    scope: Scope
    agent: str | None = None

    async def hear(self, media: whatsapp.Media) -> str | None:
        """What the audio says; None for audio that says nothing."""
        note = providers.read_note(media.data, media.mime_type)
        async with self.live.sessions.begin() as session_:
            catalog = await providers.get_catalog(session_)
            keys = await providers.keys_of(session_, self.live.vault, self.scope)
            asked = providers.Asked(language=await self._find_language(session_, catalog))
            ears = providers.ears_for(asked, catalog, keys)
        return (await providers.transcribe(ears, note)).text or None

    async def _find_language(self, session_: AsyncSession, catalog: Catalog) -> str | None:
        if self.agent is None:
            return None
        try:
            of_its_class = (await agents.agent_of(session_, self.scope, self.agent)).whole
        except agents.NoSuchAgent:
            return None
        return (await agents.resolve_for_call(session_, of_its_class, self.scope, catalog)).declaration.language


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


@dataclass(frozen=True, slots=True)
class ByEmail:
    """The org's own mailbox: the reply set as the org sets its emails, threaded under what it answers, sent by SMTP."""

    account: telephony.EmailAccount
    layout: telephony.Layout

    async def send(self, to: whatsapp.Inbound, text: str) -> None:
        """Answer the email `to` from the address it was written to."""
        await telephony.send_reply(self.account, telephony.compose_reply(self.account, self.layout, to, text))

    async def mark_read(self, message: whatsapp.Inbound, *, typing: bool) -> None:
        """Nothing: the inbox marked it read when it was read."""

    async def hear_note(self, message: whatsapp.Inbound) -> str | None:
        """None: an email's attachments are not read."""


# The one place that tells the channels apart for a reply.
async def way_to(session_: AsyncSession, live: LiveParts, route: RouteRow, inbound: whatsapp.Inbound) -> Reaches | None:
    """How the contact who wrote is answered; None when the box holds nothing to answer with."""
    if inbound.channel is Channel.email:
        mailbox = await telephony.email_account_of(session_, live.vault, route.org, route.account)
        layout = await telephony.layout_of(session_, route.org)
        return None if mailbox is None else ByEmail(mailbox, layout)
    if inbound.channel is Channel.sms:
        account = await telephony.sms_account_of(session_, live.vault, route)
        status_to = telephony.sms_status_url(live.vault, live.settings.base_url, inbound.number)
        return (
            None
            if account is None
            else BySms(live.http, account, status_to, Ears(live, Scope(route.org, route.env), route.agent))
        )
    token = await telephony.meta_token_for(session_, live.vault, route.org, inbound.phone_number_id)
    return None if token is None else ByWhatsapp(live.http, token, Ears(live, Scope(route.org, route.env), route.agent))
