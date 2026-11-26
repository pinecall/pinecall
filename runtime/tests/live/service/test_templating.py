"""A WhatsApp template the agent sends first: never asked of Meta in the sandbox, sent by production alone."""

import dataclasses
import secrets

import httpx
import pytest
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from runtime.actor import Actor, Scope
from runtime.compliance.service import keywords
from runtime.enums import Channel, Env, KeyScope
from runtime.exceptions import Conflict, Forbidden, NotFound, ValidationError
from runtime.live.parts import LiveParts
from runtime.live.service import templating
from runtime.live.service.templating import Templated, Templating
from runtime.telephony.repository import RouteRepository, RouteToWrite
from runtime.telephony.service import accounts
from runtime.telephony.service.whatsapp_number import WhatsappNumber
from runtime.wire.parts import Supervisor
from tests.conftest import Tenant, needs_the_database
from tests.fakes.meta import Graph, outside
from tests.fakes.twilio import Twilio
from tests.fakes.webhooks import Receiver
from tests.live.conftest import Side

CONTACT = "+5491155550134"
HANDED = ("consulta_derivada", "es_AR", ("Juan Cruz", "Marta Ruiz"))


BY = Supervisor(id="k_server", name=None)


async def sent_by(
    side: Side, session: AsyncSession, key: Actor, asked: Templating, parts: LiveParts | None = None
) -> Templated:
    """The template asked for as agent front-desk, with the key's scope, on the side's threads."""
    live = side.parts if parts is None else parts
    return await templating.send_template(session, live, side.threads, key.scope, "front-desk", asked, BY)


def a_key(tenant: Tenant, env: Env) -> Actor:
    """A server's key of the tenant, in the env."""
    return Actor(key_id="k_server", org=tenant.org, env=env, scopes=frozenset({KeyScope.talk}))


async def a_whatsapp_number(sessions: async_sessionmaker[AsyncSession], side: Side, tenant: Tenant, env: Env) -> str:
    """A number of a WhatsApp account of the tenant's, which agent front-desk answers at in the env."""
    number = f"+1555{secrets.randbelow(10**7):07d}"
    meta_id = f"10{secrets.randbelow(10**9):09d}"
    async with sessions.begin() as session:
        at_meta = WhatsappNumber(org=tenant.org, phone_number_id=meta_id, access_token="the org's token")
        await accounts.put_carrier(session, side.parts.vault, at_meta)
        route = RouteToWrite(
            org=tenant.org, number=number, agent="front-desk", channel=Channel.whatsapp, env=env, account=meta_id
        )
        await RouteRepository(session).put(route)
    return number


# The side's own client answers 404 to whatever it is asked: a template that reached Meta would raise.
@needs_the_database
async def test_the_sandbox_answers_a_template_and_asks_nothing_of_meta(
    side: Side, sessions: async_sessionmaker[AsyncSession], tenant: Tenant
) -> None:
    """With no number at all, and with one: answered `simulated`, no id, and nothing left the box."""
    key = a_key(tenant, Env.sandbox)
    async with sessions() as session:
        kept = await sent_by(side, session, key, Templating(CONTACT, *HANDED))
    assert kept == Templated(to=CONTACT, shown=None, simulated=True, message_id=None)
    number = await a_whatsapp_number(sessions, side, tenant, Env.sandbox)
    async with sessions() as session:
        kept = await sent_by(side, session, key, Templating(CONTACT, *HANDED))
    assert kept == Templated(to=CONTACT, shown=number, simulated=True, message_id=None)


@needs_the_database
async def test_production_sends_the_template_filled_from_the_agents_number_on_the_orgs_token(
    side: Side, sessions: async_sessionmaker[AsyncSession], tenant: Tenant
) -> None:
    """Meta is asked once, from the number's own id, with the variables in order; its id of the message comes back."""
    number = await a_whatsapp_number(sessions, side, tenant, Env.production)
    meta = Graph()
    async with httpx.AsyncClient(transport=outside(Twilio(), meta, Receiver())) as http:
        parts = dataclasses.replace(side.parts, http=http)
        async with sessions() as session:
            key = a_key(tenant, Env.production)
            sent = await sent_by(side, session, key, Templating(CONTACT, *HANDED), parts)
    assert sent == Templated(to=CONTACT, shown=number, simulated=False, message_id="wamid.1")
    (asked,) = meta.sent
    assert (asked["to"], asked["type"]) == ("5491155550134", "template")
    assert asked["template"] == {
        "name": "consulta_derivada",
        "language": {"code": "es_AR"},
        "components": [
            {
                "type": "body",
                "parameters": [{"type": "text", "text": "Juan Cruz"}, {"type": "text", "text": "Marta Ruiz"}],
            }
        ],
    }
    assert meta.tokens == ["Bearer the org's token"]


@needs_the_database
async def test_a_template_is_refused_before_anything_is_sent(
    side: Side, sessions: async_sessionmaker[AsyncSession], tenant: Tenant
) -> None:
    """A number that is none, an agent with no WhatsApp number in production, another's number, who stopped."""
    sandbox, production = a_key(tenant, Env.sandbox), a_key(tenant, Env.production)
    async with sessions() as session:
        with pytest.raises(ValidationError, match="not a number a template is sent to"):
            await sent_by(side, session, sandbox, Templating("1155550134", *HANDED))
        with pytest.raises(NotFound, match="answers WhatsApp at no number in the production"):
            await sent_by(side, session, production, Templating(CONTACT, *HANDED))
        with pytest.raises(ValidationError, match="not a number agent front-desk answers WhatsApp at"):
            asked = Templating(CONTACT, *HANDED, shown="+15550000000")
            await sent_by(side, session, sandbox, asked)
    async with sessions.begin() as session:
        await keywords.stop_writing_to(
            session,
            Scope(tenant.org, Env.sandbox),
            CONTACT,
            source=keywords.TEXTED_STOP,
            text="STOP",
            call=None,
            by="contact",
        )
    async with sessions() as session:
        with pytest.raises(Forbidden, match="asked for no more messages"):
            await sent_by(side, session, sandbox, Templating(CONTACT, *HANDED))


@needs_the_database
async def test_a_template_with_its_words_needs_somebody_holding_the_agent_and_one_without_them_does_not(
    side: Side, sessions: async_sessionmaker[AsyncSession], tenant: Tenant
) -> None:
    """Its words open the contact's conversation, which an app must answer on; with none it opens nothing."""
    await a_whatsapp_number(sessions, side, tenant, Env.sandbox)
    key = a_key(tenant, Env.sandbox)
    said = Templating(CONTACT, *HANDED, text="Hola Marta, recibimos tu consulta.")
    async with sessions() as session:
        with pytest.raises(Conflict, match="what they answer would reach no app"):
            await sent_by(side, session, key, said)
        kept = await sent_by(side, session, key, Templating(CONTACT, *HANDED))
    assert (kept.simulated, kept.call) == (True, None)
