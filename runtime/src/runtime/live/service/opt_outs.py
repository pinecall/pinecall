"""A contact who stops the messages: what their word does before the model reads it, and what they are told."""

import logging
from dataclasses import dataclass
from typing import Literal

import httpx

from runtime.actor import Scope
from runtime.compliance import service as compliance
from runtime.enums import Channel
from runtime.exceptions import PinecallError
from runtime.live.parts import LiveParts
from runtime.live.service.replies import Reaches, way_to
from runtime.telephony.models import Route as RouteRow
from runtime.whatsapp import service as whatsapp
from runtime.wire.parts import EndedBy

logger = logging.getLogger(__name__)

# What a message that was a word did: the contact is off the list of the written to, or back on it,
# was told who writes, or is one who stopped and is not answered.
type Taken = Literal["stop", "start", "help", "silenced"]


@dataclass(frozen=True, slots=True)
class Stop:
    """An open conversation to end, because its contact asked for no more messages."""

    # The contact's own word ended it, or the agent took them off at their asking.
    by: EndedBy
    # The words they asked with, when the agent heard them.
    note: str | None = None
    # Whether the fact is on the list already: the contact's word and the app's command write it themselves.
    written: bool = True
    # The call they asked on, kept with the fact: what the judge of an honoured stop reads.
    call: str | None = None


async def refuses_messages(live: LiveParts, scope: Scope, contact: str) -> bool:
    """Whether the contact asked, in writing, to be written to no more, and nothing lifted it since."""
    async with live.sessions.begin() as session_:
        return await compliance.refuses_messages(session_, scope, contact)


# Before the model reads it, and whoever holds the thread. A word that stops is honoured on the
# gateway it landed on; the conversation it ends may run on another, which writes nothing more to a
# contact the list names. Twilio answers these words itself on a long code and blocks the number
# for the contact: what is said here is the org's own sentence, for an account that turned that off.
async def take_word(live: LiveParts, route: RouteRow, inbound: whatsapp.Inbound, call: str | None) -> Taken | None:
    """What a text that is a word to stop, to start again or to ask who writes did; None for any other message."""
    if inbound.channel is not Channel.sms:
        return None
    scope, contact = Scope(route.org, route.env), inbound.caller
    async with live.sessions.begin() as session_:
        policy = await compliance.policy_of(session_, route.org)
        word = compliance.keyword_of(inbound.text, policy.sms_stop_words)
        stopped = await compliance.refuses_messages(session_, scope, contact)
        reaches = await way_to(session_, live, route, inbound)
        if word == "stop":
            await compliance.stop_writing_to(
                session_, scope, contact, source=compliance.TEXTED_STOP, text=inbound.text, call=call, by="contact"
            )
        elif stopped and word == "start":
            await compliance.start_writing_to(session_, scope, contact, text=inbound.text)
    if word == "stop":
        await _tell(reaches, inbound, policy.sms_stop_reply)
        return "stop"
    if stopped:
        if word != "start":
            logger.info(
                "sms: %s asked for no more messages: what it wrote to %s is not answered", contact, route.number
            )
        return "start" if word == "start" else "silenced"
    if word == "help" and policy.sms_help_reply:
        await _tell(reaches, inbound, policy.sms_help_reply)
        return "help"
    return None


# The one message a contact who stopped is still sent (47 CFR 64.1200(a)(12): a confirmation, once).
# When the agent took them off, the carrier saw no word of its own and confirmed nothing: the
# platform's sentence says it, unless the org wrote its own or wants none.
async def take_off(live: LiveParts, scope: Scope, inbound: whatsapp.Inbound, reaches: Reaches, stop: Stop) -> None:
    """Write that the contact asked the agent for no more messages, when nobody did yet, and tell them so."""
    async with live.sessions.begin() as session_:
        policy = await compliance.policy_of(session_, scope.org)
        if not stop.written:
            asked = compliance.ASKED_THE_AGENT_IN_WRITING
            await compliance.stop_writing_to(
                session_, scope, inbound.caller, source=asked, text=stop.note, call=stop.call, by="agent"
            )
    said = compliance.TAKEN_OFF if policy.sms_stop_reply is None else policy.sms_stop_reply
    if stop.by == "agent":
        await _tell(reaches, inbound, said)


async def _tell(reaches: Reaches | None, inbound: whatsapp.Inbound, sentence: str | None) -> None:
    if reaches is None or not sentence or not sentence.strip() or inbound.carrier_replied:
        return
    try:
        await reaches.send(inbound, sentence.strip())
    # The carrier that already took the word refuses the message (Twilio: 21610), which is as it should be.
    except (PinecallError, httpx.HTTPError) as refused:
        logger.info("sms: the confirmation to %s was not sent: %s", inbound.caller, refused)
