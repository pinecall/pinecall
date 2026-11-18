"""A contact's calls with an agent: the newest of them, on a channel, and the newest that is over."""

import secrets

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from runtime.actor import Scope
from runtime.calls.models.call_fact import CallFact
from runtime.calls.models.call_log_head import CallLogHead
from runtime.calls.service import inbox
from runtime.enums import Channel, Env
from tests.conftest import Tenant, needs_the_database


@needs_the_database
async def test_the_call_a_new_conversation_carries_on_is_the_newest_that_is_over(
    sessions: async_sessionmaker[AsyncSession], tenant: Tenant
) -> None:
    """Two email threads at once: the open one is the newest, and the one carried on is the ended one before it."""
    scope, contact = Scope(tenant.org, Env.sandbox), f"ana-{secrets.token_hex(3)}@example.org"
    ended, open_now = f"call_{secrets.token_hex(16)}", f"call_{secrets.token_hex(16)}"
    async with sessions.begin() as session:
        for call, at, sealed in ((ended, 1.0, True), (open_now, 2.0, False)):
            session.add(
                CallLogHead(
                    log=call,
                    agent="front-desk",
                    call=call,
                    started_at=at,
                    org=tenant.org,
                    env=Env.sandbox,
                    holder="",
                    sealed=sealed,
                )
            )
            session.add(CallFact(call=call, contact=contact, channel=Channel.email.value))
    async with sessions() as session:
        assert await inbox.find_newest_call_with(session, scope, "front-desk", contact) == open_now
        assert await inbox.find_newest_call_with(session, scope, "front-desk", contact, ended=True) == ended
        assert await inbox.find_newest_call_with(session, scope, "front-desk", contact, Channel.sms) is None
