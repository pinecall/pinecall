"""The agent writes first on WhatsApp: a template approved at Meta, its words said on the contact's conversation."""

import re
from collections.abc import Mapping
from dataclasses import dataclass, field

from sqlalchemy.ext.asyncio import AsyncSession

from runtime.actor import Scope
from runtime.calls.context import new_call_id
from runtime.compliance import service as compliance
from runtime.enums import Channel, Env
from runtime.exceptions import Conflict, Forbidden, NotFound, ValidationError
from runtime.kit.text import Json
from runtime.live.holders import NoApp
from runtime.live.parts import LiveParts
from runtime.live.service.desk import Supervising, send_verb
from runtime.live.service.whatsapp import FirstMessage, Threads
from runtime.telephony import service as telephony
from runtime.telephony.models import Route
from runtime.whatsapp import service as whatsapp
from runtime.wire.commands import SayVerb
from runtime.wire.parts import Supervisor

# A number as it is dialled from anywhere: a plus, the country's code, the number.
E164 = re.compile(r"\+[1-9]\d{7,14}")


@dataclass(frozen=True, slots=True)
class Templating:
    """A template asked for: the contact, the template approved at Meta, its language, what fills it, where from.

    `text`: what the template says once filled. Given, it is the first turn of the contact's conversation,
    which `metadata` opens with, as a text's does; left out, the template is sent and said nowhere.
    """

    to: str
    template: str
    language: str
    # What fills the body's {{1}}, {{2}}…, in order.
    variables: tuple[str, ...] = ()
    shown: str | None = None
    text: str | None = None
    metadata: Mapping[str, Json] = field(default_factory=dict[str, Json])


@dataclass(frozen=True, slots=True)
class Templated:
    """A template on its way, or kept: the contact, the number it left from, and Meta's id of the message.

    `simulated`: the sandbox's answer. Nothing was asked of Meta, and there is no id. `call`: the
    conversation its words were said on, when they were given and the agent answers WhatsApp at a number.
    """

    to: str
    shown: str | None
    simulated: bool
    message_id: str | None = None
    call: str | None = None


# A template is the one message Meta charges for, on the account of whoever owns the number, and it
# reaches a person's phone. The sandbox is where an agent is tried, by goldens that hand a call over
# dozens of times a run: on 2026-11-26 one such run sent 27 paid messages from a client's account.
# So the sandbox asks nothing of Meta: it answers as production would, marked `simulated`, and the
# app's code is the same in both. A contact who asked for no more messages is written to in neither.
#
# With its words given, they open the contact's conversation, as a text's do: until 2026-11-26 a
# template was said nowhere, so the contact's "sí" opened a call that began on it, the agent knew
# what it had asked only by what its app kept, and the console showed a conversation with no first
# message. The template goes first, for Meta's refusal to open nothing; then the conversation, whose
# first turn is those words and is sent by nobody (`FirstSaid`). A contact whose conversation has
# idle time left wrote within Meta's 24 hours: the words are one more message of it, no template sent.
async def send_template(
    session: AsyncSession, live: LiveParts, threads: Threads, scope: Scope, slug: str, asked: Templating, by: Supervisor
) -> Templated:
    """Send the contact one WhatsApp template as the agent, its words on their conversation; never from the sandbox."""
    if E164.fullmatch(asked.to) is None:
        raise ValidationError(f"{asked.to} is not a number a template is sent to: +, the country's code, the number")
    if await compliance.refuses_messages(session, scope, asked.to):
        raise Forbidden(f"{asked.to} asked for no more messages: only their own START lifts it")
    routes = await telephony.list_routes(session, scope.org, scope.env, agent=slug, channel=Channel.whatsapp)
    route = next((one for one in routes if asked.shown in (None, one.number)), None)
    if route is None and asked.shown is not None:
        raise ValidationError(f"{asked.shown} is not a number agent {slug} answers WhatsApp at in the {scope.env}")
    simulated = scope.env is Env.sandbox
    if route is None:
        if simulated:
            return Templated(to=asked.to, shown=None, simulated=True)
        raise NotFound(
            f"agent {slug} answers WhatsApp at no number in the {scope.env}: "
            f"`pinecall numbers import <number> --agent {slug} --channel whatsapp` gives it one"
        )
    if asked.text is None:
        message_id = None if simulated else await _send(session, live, route, asked)
        return Templated(to=asked.to, shown=route.number, simulated=simulated, message_id=message_id)
    registration = live.holders.find_ring_taker(scope, slug, asked.to)
    if registration is None:
        raise Conflict(f"{NoApp(slug)}: what they answer would reach no app")
    contact = _contact_of(route, asked.to)
    going = await threads.find_going(registration.scope, slug, contact)
    message_id = None if simulated or going is not None else await _send(session, live, route, asked)
    first = FirstMessage(going or new_call_id(), asked.metadata, said=going is None)
    call = await threads.open_to(registration, route, contact, first)
    await send_verb(live, Supervising(call, by), SayVerb(text=asked.text))
    return Templated(to=asked.to, shown=route.number, simulated=simulated, message_id=message_id, call=call)


async def _send(session: AsyncSession, live: LiveParts, route: Route, asked: Templating) -> str:
    # A WhatsApp number's account is Meta's id of the number, which is what a message is sent from.
    token = None
    if route.account is not None:
        token = await telephony.meta_token_for(session, live.vault, route.org, route.account)
    if route.account is None or token is None:
        raise Conflict(f"{route.number} has no WhatsApp account of the org to send a template from")
    filled = whatsapp.Template(asked.template, asked.language, asked.variables)
    return await whatsapp.send_template(live.http, token, route.account, asked.to, filled)


# The contact as a message of theirs would name them: what keys their thread, so their answer lands on it.
def _contact_of(route: Route, to: str) -> whatsapp.Inbound:
    return whatsapp.Inbound(
        number=route.number or "",
        phone_number_id=route.account or "",
        wa_id=to.lstrip("+"),
        name=None,
        message_id="",
        kind="text",
        text=None,
        channel=Channel.whatsapp,
    )
