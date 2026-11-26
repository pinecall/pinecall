"""The agent writes first on WhatsApp: a template approved at Meta, sent in production, never from the sandbox."""

import re
from dataclasses import dataclass

from sqlalchemy.ext.asyncio import AsyncSession

from runtime.actor import Scope
from runtime.compliance import service as compliance
from runtime.enums import Channel, Env
from runtime.exceptions import Conflict, Forbidden, NotFound, ValidationError
from runtime.live.parts import LiveParts
from runtime.telephony import service as telephony
from runtime.telephony.models import Route
from runtime.whatsapp import service as whatsapp

# A number as it is dialled from anywhere: a plus, the country's code, the number.
E164 = re.compile(r"\+[1-9]\d{7,14}")


@dataclass(frozen=True, slots=True)
class Templating:
    """A template asked for: the contact, the template approved at Meta, its language, what fills it, where from."""

    to: str
    template: str
    language: str
    # What fills the body's {{1}}, {{2}}…, in order.
    variables: tuple[str, ...] = ()
    shown: str | None = None


@dataclass(frozen=True, slots=True)
class Templated:
    """A template on its way, or kept: the contact, the number it left from, and Meta's id of the message.

    `simulated`: the sandbox's answer. Nothing was asked of Meta, and there is no id.
    """

    to: str
    shown: str | None
    simulated: bool
    message_id: str | None = None


# A template is the one message Meta charges for, on the account of whoever owns the number, and it
# reaches a person's phone. The sandbox is where an agent is tried, by goldens that hand a call over
# dozens of times a run: on 2026-11-26 one such run sent 27 paid messages from a client's account.
# So the sandbox asks nothing of Meta: it answers as production would, marked `simulated`, and the
# app's code is the same in both. A contact who asked for no more messages is written to in neither.
async def send_template(
    session: AsyncSession, live: LiveParts, scope: Scope, slug: str, asked: Templating
) -> Templated:
    """Send the contact one WhatsApp template as the agent; in the sandbox, answered and never sent."""
    if E164.fullmatch(asked.to) is None:
        raise ValidationError(f"{asked.to} is not a number a template is sent to: +, the country's code, the number")
    if await compliance.refuses_messages(session, scope, asked.to):
        raise Forbidden(f"{asked.to} asked for no more messages: only their own START lifts it")
    routes = await telephony.list_routes(session, scope.org, scope.env, agent=slug, channel=Channel.whatsapp)
    route = next((one for one in routes if asked.shown in (None, one.number)), None)
    if route is None and asked.shown is not None:
        raise ValidationError(f"{asked.shown} is not a number agent {slug} answers WhatsApp at in the {scope.env}")
    if scope.env is Env.sandbox:
        return Templated(to=asked.to, shown=None if route is None else route.number, simulated=True)
    if route is None:
        raise NotFound(
            f"agent {slug} answers WhatsApp at no number in the {scope.env}: "
            f"`pinecall numbers import <number> --agent {slug} --channel whatsapp` gives it one"
        )
    message_id = await _send(session, live, route, asked)
    return Templated(to=asked.to, shown=route.number, simulated=False, message_id=message_id)


async def _send(session: AsyncSession, live: LiveParts, route: Route, asked: Templating) -> str:
    # A WhatsApp number's account is Meta's id of the number, which is what a message is sent from.
    token = None
    if route.account is not None:
        token = await telephony.meta_token_for(session, live.vault, route.org, route.account)
    if route.account is None or token is None:
        raise Conflict(f"{route.number} has no WhatsApp account of the org to send a template from")
    filled = whatsapp.Template(asked.template, asked.language, asked.variables)
    return await whatsapp.send_template(live.http, token, route.account, asked.to, filled)
