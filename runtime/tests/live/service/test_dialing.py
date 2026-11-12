"""A call placed: the number shown, the org's account, the guards, the log, the room offered; once a call id."""

import os
import secrets
from collections.abc import AsyncIterator
from datetime import UTC, datetime

import httpx
import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from runtime.actor import Scope
from runtime.calls.service import call_id_of
from runtime.compliance.models import Dial
from runtime.compliance.service import dial_guards
from runtime.compliance.service.dial_guards import Guards
from runtime.enums import Env
from runtime.fleet.models import Offer
from runtime.kit.crypto import Vault
from runtime.live.parts import LiveParts
from runtime.live.service import Placement, place_call
from runtime.scoping import box_wide
from runtime.telephony.service import number_hook, outbound
from runtime.telephony.service.number_hook import NumberImport
from tests.conftest import Tenant, needs_the_services
from tests.fakes.livekit import per_world
from tests.fakes.meta import Graph, outside
from tests.fakes.twilio import Twilio
from tests.fakes.webhooks import Receiver
from tests.telephony.conftest import NAMES, Line, a_number

AGENT = "recordatorios"
HER_PHONE = "+59899000001"


@pytest.fixture
async def line(sessions: async_sessionmaker[AsyncSession], tenant: Tenant) -> AsyncIterator[Line]:
    """The tenant's org with a Twilio account nobody brought yet, its LiveKits of its own."""
    twilio, graph, servers = Twilio(), Graph(number=a_number()), per_world()
    vault = Vault(os.environ["PINECALL_VAULT_KEY"])
    async with httpx.AsyncClient(transport=outside(twilio, graph, Receiver())) as http:
        yield Line(sessions, vault, http, NAMES, tenant.org, twilio, graph, servers)
    for server in servers.values():
        await server.aclose()


async def ready_to_dial(line: Line) -> str:
    """The org's account brought and made dialable, a number of it the agent answers at, any number dialled."""
    number = a_number()
    await line.brought()
    line.twilio.owns(number)
    scope = line.scope(Env.sandbox)
    async with line.sessions.begin() as session:
        await number_hook.import_number(
            session, line.vault, line.http, line.livekits, line.names, NumberImport(scope, AGENT, number)
        )
        await outbound.provision_outbound(session, line.vault, line.http, line.names, scope, None)
        await dial_guards.put_guards(session, line.org, Guards(dial_anywhere=True))
    return number


def placement_of(line: Line, tenant: Tenant, call: str) -> Placement:
    """A flow's call step: the agent dialling her from its number, the call named by the run and the step."""
    return Placement(
        scope=Scope(line.org, Env.sandbox),
        agent=AGENT,
        to=HER_PHONE,
        shown=None,
        asked_by=tenant.member,
        at=datetime.now(UTC),
        call=call,
    )


# A dial whose answer was lost (the step's commit, 2026-11 defect 1 of flows) is asked again with the
# same call id: the second is answered with the first's call, and nothing is dialled again.
@needs_the_services
async def test_a_dial_asked_twice_with_one_call_id_places_one_call(
    live: LiveParts, line: Line, tenant: Tenant, sessions: async_sessionmaker[AsyncSession]
) -> None:
    number = await ready_to_dial(line)
    call = call_id_of(f"run_{secrets.token_hex(4)}/1")
    async with sessions.begin() as session:
        first = await place_call(session, live, placement_of(line, tenant, call))
    async with sessions.begin() as session:
        again = await place_call(session, live, placement_of(line, tenant, call))
    assert first == again
    assert (first.call, first.shown) == (call, number)
    dialing = [entry for entry in await live.store.whole_of(call) if entry.type == "call.dialing"]
    assert len(dialing) == 1
    async with sessions() as session:
        with box_wide():
            offers = (await session.scalars(select(Offer).where(Offer.room == call))).all()
            dials = (await session.scalars(select(Dial).where(Dial.call == call))).all()
    assert len(offers) == 1
    assert len(dials) == 1
