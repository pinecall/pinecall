"""The agent writes first: one SMS to a contact, after the guards a dial passes, on the conversation it opens."""

from dataclasses import dataclass
from datetime import datetime

from sqlalchemy.ext.asyncio import AsyncSession

from runtime.actor import Actor, Scope
from runtime.calls import service as calls
from runtime.calls.context import new_call_id
from runtime.compliance import service as compliance
from runtime.enums import Channel
from runtime.exceptions import Conflict, Forbidden, NotFound, ValidationError
from runtime.live.holders import NoApp
from runtime.live.parts import LiveParts
from runtime.live.service.desk import Supervising, send_verb
from runtime.live.service.whatsapp import Threads
from runtime.telephony import service as telephony
from runtime.telephony.models import Route
from runtime.whatsapp import service as whatsapp
from runtime.wire.commands import SayVerb
from runtime.wire.parts import Supervisor


@dataclass(frozen=True, slots=True)
class Text:
    """What a key asks a text with: the contact, the words, the number it is sent from, the consent."""

    to: str
    text: str
    shown: str | None = None
    consent: compliance.Consent | None = None


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
    """A text said on its conversation: the call it is, and the number it left from."""

    call: str
    to: str
    shown: str


# Asked with a key, for one of its agents, as a dial is.
async def text_as_agent(
    session: AsyncSession, live: LiveParts, threads: Threads, actor: Actor, slug: str, text: Text, at: datetime
) -> Texted:
    """Send the contact one SMS as the agent for whoever holds the key; the call it was said on."""
    by = Supervisor(id=actor.asked_by, name=None if actor.person is None else actor.person.name)
    own_phone = text.to in live.holders.phones_of(actor.env, actor.asked_by)
    return await send_text(session, live, threads, Texting(actor.scope, slug, text, by, at, own_phone))


# A contact who asked for no more messages is written to by nobody, in either env: only their own
# START lifts it. A conversation that has idle time left is the contact's own doing, and the text is
# one more message of it; a cold one passes every guard a dial does (a stranger, the consent, the
# hours, the pace), on one row of the same ledger: under the TCPA a text is a call. The words are
# said as a supervisor's are, so the log names who asked, and they reach the contact by the
# conversation's own reply tap.
async def send_text(session: AsyncSession, live: LiveParts, threads: Threads, texting: Texting) -> Texted:
    """Send the contact one SMS as the agent, on the conversation going or a new one; the call it was said on."""
    scope, slug, text = texting.scope, texting.agent, texting.asked
    route = await _find_route_shown(session, scope, slug, text.shown)
    if await compliance.refuses_messages(session, scope, text.to):
        raise Forbidden(f"{text.to} asked for no more messages: only their own START lifts it")
    registration = live.holders.find_ring_taker(scope, slug, text.to)
    if registration is None:
        raise Conflict(f"{NoApp(slug)}: what they answer would reach no app")
    contact = _contact_of(route, text.to)
    going = await threads.find_going(registration.scope, slug, contact)
    call = going or new_call_id()
    if going is None:
        await _guard(session, live, texting, route.number or "", call)
    call = await threads.open_to(registration, route, contact, call)
    await send_verb(live, Supervising(call, texting.by), SayVerb(text=text.text))
    return Texted(call=call, to=text.to, shown=route.number or "")


async def _guard(session: AsyncSession, live: LiveParts, texting: Texting, shown: str, call: str) -> None:
    scope, text = texting.scope, texting.asked
    ask = compliance.DialAsk(
        scope,
        texting.agent,
        text.to,
        shown,
        texting.by.id,
        call,
        texting.at,
        own_phone=texting.own_phone,
        consent=text.consent,
    )

    async def has_reached(destination: str) -> bool:
        return await calls.has_reached(session, scope.org, scope.env, destination)

    await compliance.guard_dial(session, live.sessions, ask, has_reached)


# The number named, when the agent answers SMS at it; else the first it answers SMS at.
async def _find_route_shown(session: AsyncSession, scope: Scope, slug: str, shown: str | None) -> Route:
    routes = await telephony.list_routes(session, scope.org, scope.env, agent=slug, channel=Channel.sms)
    if not routes:
        raise NotFound(
            f"agent {slug} answers SMS at no number in the {scope.env}: "
            f"`pinecall numbers import <number> --agent {slug} --channel sms` gives it one"
        )
    route = next((one for one in routes if shown in (None, one.number)), None)
    if route is None:
        raise ValidationError(f"{shown} is not a number agent {slug} answers SMS at in the {scope.env}")
    return route


# The contact as a message of theirs would name them: what keys their thread and says who is written to.
def _contact_of(route: Route, to: str) -> whatsapp.Inbound:
    return whatsapp.Inbound(
        number=route.number or "",
        phone_number_id="",
        wa_id=to.lstrip("+"),
        name=None,
        message_id="",
        kind="text",
        text=None,
        channel=Channel.sms,
    )
