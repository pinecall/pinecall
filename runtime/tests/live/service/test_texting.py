"""The agent writes first: who is refused before anything is sent, and the number a text leaves from."""

import secrets
from datetime import UTC, datetime

import pytest
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from runtime.actor import Actor, Scope
from runtime.compliance.service import keywords
from runtime.enums import Channel, Env, KeyScope
from runtime.exceptions import Conflict, Forbidden, NotFound, ValidationError
from runtime.live.service import texting
from runtime.live.service.texting import Text
from runtime.telephony.repository import RouteRepository, RouteToWrite
from tests.conftest import Tenant, needs_the_database
from tests.live.conftest import Side

CONTACT = "+59899000001"
NOON = datetime(2026, 11, 18, 15, 0, tzinfo=UTC)


def a_key(tenant: Tenant) -> Actor:
    """A server's key of the tenant, in the sandbox."""
    return Actor(key_id="k_server", org=tenant.org, env=Env.sandbox, scopes=frozenset({KeyScope.talk}))


@pytest.fixture
async def number(sessions: async_sessionmaker[AsyncSession], tenant: Tenant) -> str:
    """A number agent riley answers SMS at in the sandbox."""
    number = f"+1555{secrets.randbelow(10**7):07d}"
    route = RouteToWrite(org=tenant.org, number=number, agent="riley", channel=Channel.sms, env=Env.sandbox)
    async with sessions.begin() as session:
        await RouteRepository(session).put(route)
    return number


@needs_the_database
@pytest.mark.usefixtures("number")
async def test_an_agent_that_answers_sms_at_no_number_writes_to_nobody(
    side: Side, sessions: async_sessionmaker[AsyncSession], tenant: Tenant
) -> None:
    """A text leaves from a number the agent answers SMS at: none, or another's, is said before anything else."""
    async with sessions() as session:
        with pytest.raises(NotFound, match="answers SMS at no number"):
            await texting.text_as_agent(
                session, side.parts, side.threads, a_key(tenant), "nobody", Text(CONTACT, "hola"), NOON
            )
        with pytest.raises(ValidationError, match="not a number agent riley answers SMS at"):
            asked = Text(CONTACT, "hola", shown="+15550000000")
            await texting.text_as_agent(session, side.parts, side.threads, a_key(tenant), "riley", asked, NOON)


@needs_the_database
@pytest.mark.usefixtures("number")
async def test_a_contact_who_stopped_the_messages_is_written_to_by_nobody_and_an_agent_nobody_holds_writes_nothing(
    side: Side, sessions: async_sessionmaker[AsyncSession], tenant: Tenant
) -> None:
    """Their STOP stands against a key too, whatever consent it brings; and with no app, no text."""
    scope = Scope(tenant.org, Env.sandbox)
    async with sessions() as session:
        with pytest.raises(Conflict, match="no app holds agent riley"):
            await texting.text_as_agent(
                session, side.parts, side.threads, a_key(tenant), "riley", Text(CONTACT, "hola"), NOON
            )
    async with sessions.begin() as session:
        await keywords.stop_writing_to(
            session, scope, CONTACT, source=keywords.TEXTED_STOP, text="STOP", call=None, by="contact"
        )
    async with sessions() as session:
        with pytest.raises(Forbidden, match="asked for no more messages"):
            await texting.text_as_agent(
                session, side.parts, side.threads, a_key(tenant), "riley", Text(CONTACT, "hola"), NOON
            )
