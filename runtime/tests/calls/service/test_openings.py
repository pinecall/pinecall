"""Tests for what a call carries on: the earlier conversations' turns, as a judge is shown them."""

import os
from datetime import date

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from runtime.agents.declaration import Declaration
from runtime.calls.context import CallContext, Route, new_call_id
from runtime.calls.log.store import Store
from runtime.calls.log.writer import Writer
from runtime.calls.service.openings import CARRIED_READ_AT_MOST, keep_opening, read_carried
from runtime.enums import Channel, Direction, Env
from runtime.kit.crypto import Vault
from tests.calls.factories import GOLDEN
from tests.conftest import Tenant, needs_the_services


def _opened(tenant: Tenant, agent: str, call: str, continues: str | None = None) -> CallContext:
    route = Route(org=tenant.org, agent=agent, channel=Channel.whatsapp, env=Env.sandbox, number="+5491100000000")
    return CallContext(
        call, Channel.whatsapp, Direction.inbound, "+34600000000", route, date.today(), continues=continues
    )


@needs_the_services
async def test_a_call_that_carries_on_another_is_said_its_turns_line_by_line_and_one_of_its_own_nothing(
    tenant: Tenant, agent: str, sessions: async_sessionmaker[AsyncSession]
) -> None:
    vault = Vault(os.environ["PINECALL_VAULT_KEY"])
    first, second = new_call_id(), new_call_id()
    ticks = iter(entry.ts for entry in GOLDEN)
    store = Store(sessions, Writer(sessions), clock=lambda: next(ticks))
    for entry in GOLDEN:
        await store.write("entry", first, agent, entry.type, entry.data, ephemeral=entry.ephemeral)
    await store.writer.drain()
    async with sessions.begin() as session:
        await keep_opening(session, tenant.org, _opened(tenant, agent, first), Declaration(slug=agent))
        await keep_opening(session, tenant.org, _opened(tenant, agent, second, first), Declaration(slug=agent))
    said_turns = [
        f"{'Agent' if entry.type == 'turn.agent' else 'Contact'}: {str(entry.data['text']).strip()}"
        for entry in GOLDEN
        if entry.type in ("turn.user", "turn.agent") and str(entry.data.get("text") or "").strip()
    ]
    async with sessions() as session:
        carried = await read_carried(session, vault, second)
        alone = await read_carried(session, vault, first)
    assert said_turns, "the golden call has turns"
    expected = "\n".join(said_turns)
    assert carried == (expected if len(expected) <= CARRIED_READ_AT_MOST else "…\n" + expected[-CARRIED_READ_AT_MOST:])
    assert alone == ""
