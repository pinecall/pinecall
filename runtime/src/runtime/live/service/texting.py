"""The agent writes first: an SMS or an email to a contact, past the guards a dial passes, on its conversation."""

from collections.abc import Mapping
from dataclasses import dataclass, field
from datetime import datetime

from sqlalchemy.ext.asyncio import AsyncSession

from runtime.actor import Actor, Scope
from runtime.agents import service as agents
from runtime.calls import service as calls
from runtime.calls.context import new_call_id
from runtime.compliance import service as compliance
from runtime.enums import Channel
from runtime.exceptions import Conflict, Forbidden, NotFound, ValidationError
from runtime.kit.text import Json, parse_email
from runtime.live.holders import NoApp
from runtime.live.parts import LiveParts
from runtime.live.service.desk import Supervising, send_verb
from runtime.live.service.dialing import INSTRUCTION
from runtime.live.service.whatsapp import FirstMessage, Threads
from runtime.providers import service as providers
from runtime.telephony import service as telephony
from runtime.telephony.models import Route
from runtime.whatsapp import service as whatsapp
from runtime.wire.commands import SayVerb
from runtime.wire.parts import Supervisor

# What each channel's refusals name it by, and what the agent answers at on it.
_SAID = {Channel.sms: ("SMS", "number", "a number"), Channel.email: ("email", "address", "an address")}


@dataclass(frozen=True, slots=True)
class Text:
    """What a key asks a text with: the contact, the words, the number or address it is sent from, the consent.

    An email's alone: its subject, and its words, which the agent writes itself when none are given.
    `metadata` and `instruction` are a dial's: what the call.started carries, what the call is for.
    """

    to: str
    text: str | None
    shown: str | None = None
    consent: compliance.Consent | None = None
    subject: str | None = None
    metadata: Mapping[str, Json] = field(default_factory=dict[str, Json])
    instruction: str | None = None


@dataclass(frozen=True, slots=True)
class Texting:
    """A text asked for: the scope, the agent, what is asked, who asked and when."""

    scope: Scope
    agent: str
    asked: Text
    by: Supervisor
    at: datetime
    # The contact is the asker's own verified phone: a test, held to no contact's hours.
    own_phone: bool = False


@dataclass(frozen=True, slots=True)
class Texted:
    """A text said on its conversation: the call it is, the contact, and the number or address it left from."""

    call: str
    to: str
    shown: str


# Asked with a key, for one of its agents, as a dial is.
async def text_as_agent(
    session: AsyncSession, live: LiveParts, threads: Threads, actor: Actor, slug: str, text: Text, at: datetime
) -> Texted:
    """Send the contact one SMS or email as the agent for whoever holds the key; the call it was said on."""
    by = Supervisor(id=actor.asked_by, name=None if actor.person is None else actor.person.name)
    own_phone = text.to in live.holders.phones_of(actor.env, actor.asked_by)
    return await send_text(session, live, threads, Texting(actor.scope, slug, text, by, at, own_phone))


# A contact who asked for no more messages is written to by nobody, in either env: only their own
# START lifts it. A conversation that has idle time left is the contact's own doing, and the text is
# one more message of it; a cold one passes every guard a dial does (a stranger, the consent, the
# hours, the pace), on one row of the same ledger: under the TCPA a text is a call. The words are
# said as a supervisor's are, so the log names who asked, and they reach the contact by the
# conversation's own reply tap. An email always opens a thread of its own, keyed by the id its first
# message goes out under, so the contact's reply lands on this call; with no words given the agent
# writes that first email itself, as a dialled call with no greeting opens.
async def send_text(session: AsyncSession, live: LiveParts, threads: Threads, texting: Texting) -> Texted:
    """Send the contact one SMS or email as the agent, on the conversation going or a new one; the call said on."""
    scope, slug, text = texting.scope, texting.agent, texting.asked
    channel, to = _channel_of(text)
    route = await _find_route_shown(session, scope, slug, channel, text.shown)
    if await compliance.refuses_messages(session, scope, to):
        raise Forbidden(f"{to} asked for no more messages: only their own START lifts it")
    registration = live.holders.find_ring_taker(scope, slug, to)
    if registration is None:
        raise Conflict(f"{NoApp(slug)}: what they answer would reach no app")
    contact = _contact_of(route, to, channel, text.subject)
    going = await threads.find_going(registration.scope, slug, contact)
    call = going or new_call_id()
    if going is None:
        zone = await _zone_of(session, scope, slug) if channel.is_by_email else None
        await _guard(session, live, texting, _Reached(to, route.number or "", channel, zone), call)
    metadata = {**text.metadata, **({INSTRUCTION: text.instruction} if text.instruction else {})}
    first = FirstMessage(call, metadata, opens_itself=text.text is None)
    call = await threads.open_to(registration, route, contact, first)
    if text.text is not None:
        await send_verb(live, Supervising(call, texting.by), SayVerb(text=text.text))
    return Texted(call=call, to=to, shown=route.number or "")


@dataclass(frozen=True, slots=True)
class _Reached:
    to: str
    shown: str
    channel: Channel
    zone: str | None


async def _guard(session: AsyncSession, live: LiveParts, texting: Texting, reached: _Reached, call: str) -> None:
    scope, text = texting.scope, texting.asked
    ask = compliance.DialAsk(
        scope,
        texting.agent,
        reached.to,
        reached.shown,
        texting.by.id,
        call,
        texting.at,
        own_phone=texting.own_phone,
        consent=text.consent,
        channel=reached.channel,
        zone=reached.zone,
    )

    async def has_reached(destination: str) -> bool:
        return await calls.has_reached(session, scope.org, scope.env, destination)

    await compliance.guard_dial(session, live.sessions, ask, has_reached)


# A number and an address are told apart by the `@`. An address is lowercased, as the inbox reads
# its sender, and its thread needs a subject; words are what an SMS is, and the agent's own opening
# is an email's alone.
def _channel_of(text: Text) -> tuple[Channel, str]:
    if "@" in text.to:
        if not (text.subject or "").strip():
            raise ValidationError("an email needs a `subject`: it is the thread's, and every reply's after it")
        return Channel.email, parse_email(text.to)
    if text.subject is not None:
        raise ValidationError(f"{text.to} is a number, and an SMS has no `subject`: only an email to an address does")
    if text.text is None:
        raise ValidationError("an SMS needs its `text`: only an email's first words are the agent's own to write")
    return Channel.sms, text.to


# The number or address named, when the agent answers on the channel there; else the first it does.
async def _find_route_shown(
    session: AsyncSession, scope: Scope, slug: str, channel: Channel, shown: str | None
) -> Route:
    said, at, one_of = _SAID[channel]
    routes = await telephony.list_routes(session, scope.org, scope.env, agent=slug, channel=channel)
    if not routes:
        raise NotFound(
            f"agent {slug} answers {said} at no {at} in the {scope.env}: "
            f"`pinecall numbers import <{at}> --agent {slug} --channel {channel.value}` gives it one"
        )
    route = next((one for one in routes if shown in (None, one.number)), None)
    if route is None:
        raise ValidationError(f"{shown} is not {one_of} agent {slug} answers {said} at in the {scope.env}")
    return route


# The zone an address's hours are kept in: its agent's own, as its settings set it over its class.
async def _zone_of(session: AsyncSession, scope: Scope, slug: str) -> str | None:
    try:
        whole = (await agents.agent_of(session, scope, slug)).whole
    except agents.NoSuchAgent:
        return None
    catalog = await providers.get_catalog(session)
    return (await agents.resolve_for_call(session, whole, scope, catalog)).declaration.timezone


# The contact as a message of theirs would name them: what keys their thread and says who is written
# to. An email's thread is a new one, named by the `Message-ID` its first email goes out under.
def _contact_of(route: Route, to: str, channel: Channel, subject: str | None) -> whatsapp.Inbound:
    first = telephony.new_message_id(route.number or "") if channel.is_by_email else ""
    return whatsapp.Inbound(
        number=route.number or "",
        phone_number_id="",
        wa_id=to.lstrip("+"),
        name=None,
        message_id=first,
        kind="text",
        text=None,
        channel=channel,
        subject=None if subject is None else subject.strip(),
        thread=first,
    )
