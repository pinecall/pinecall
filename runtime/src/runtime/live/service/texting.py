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
class Texted:
    """A text a key asked for, said on its conversation: the call it is, and the number it left from."""

    call: str
    to: str
    shown: str


# A contact who asked for no more messages is written to by nobody, in either env: only their own
# START lifts it. A conversation that has idle time left is the contact's own doing, and the text is
# one more message of it; a cold one passes every guard a dial does (a stranger, the consent, the
# hours, the pace), on one row of the same ledger. The words are said as a supervisor's are, so the
# log names who asked, and they reach the contact by the conversation's own reply tap.
async def text_as_agent(
    session: AsyncSession, live: LiveParts, threads: Threads, actor: Actor, slug: str, text: Text, at: datetime
) -> Texted:
    """Send the contact one SMS as the agent, on the conversation going or a new one; the call it was said on."""
    scope = actor.scope
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
        await _guard(session, live, actor, slug, text, route.number, call, at)
    call = await threads.open_to(registration, route, contact, call)
    by = Supervisor(id=actor.asked_by, name=None if actor.person is None else actor.person.name)
    await send_verb(live, Supervising(call, by), SayVerb(text=text.text))
    return Texted(call=call, to=text.to, shown=route.number)


async def _guard(
    session: AsyncSession, live: LiveParts, actor: Actor, slug: str, text: Text, shown: str, call: str, at: datetime
) -> None:
    scope = actor.scope
    own_phone = text.to in live.holders.phones_of(actor.env, actor.asked_by)
    ask = compliance.DialAsk(
        scope, slug, text.to, shown, actor.asked_by, call, at, own_phone=own_phone, consent=text.consent
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
