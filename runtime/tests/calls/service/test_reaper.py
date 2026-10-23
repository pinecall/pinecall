"""How long a reaped call lasted: from its start to its last entry, and nothing for one that never started."""

import time

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from pinecall_runtime.calls.repository.heads import Claim, HeadRepository, Unsealed
from pinecall_runtime.calls.repository.openings import OpeningRepository
from pinecall_runtime.calls.service import reaper
from pinecall_runtime.calls.store import Store
from pinecall_runtime.enums import Env
from pinecall_runtime.kit.auth import Scope
from tests.conftest import Tenant, needs_the_database


def orphan(started_at: float | None, last_at: float) -> Unsealed:
    """A quiet call the reaper found, started or not."""
    return Unsealed(
        call="call_x", agent="clinica-norte", started_at=started_at, last_at=last_at, channel=None, env=None
    )


def test_a_started_call_lasted_from_its_start_to_its_last_entry() -> None:
    assert reaper.lasted(orphan(1_000.0, 1_153.5)) == 153.5
    assert reaper.lasted(orphan(1_000.0, 990.0)) == 0.0


def test_a_call_that_never_started_lasted_nothing_not_every_second_since_1970() -> None:
    assert reaper.lasted(orphan(None, 1_792_760_955.0)) == 0.0


@needs_the_database
async def test_an_opening_nobody_joined_is_found_quiet_with_no_start(
    store: Store, sessions: async_sessionmaker[AsyncSession], tenant: Tenant, call: str, agent: str
) -> None:
    await store.claim(call, agent, tenant.org, Claim(Scope(tenant.org, Env.sandbox)))
    async with sessions.begin() as session:
        await OpeningRepository(session).keep(call, tenant.org, {}, "hash")
    async with sessions() as session:
        quiet = await HeadRepository(session).unsealed_spoken(time.time() + 60, limit=1_000)
    found = next(one for one in quiet if one.call == call)
    assert found.started_at is None
    assert reaper.lasted(found) == 0.0
