"""Tests for a WhatsApp message read once: the claim, its lease, two deliveries at once, the ids forgotten."""

import asyncio
from datetime import UTC, datetime, timedelta

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from runtime.whatsapp.service import seen
from tests.conftest import Tenant, make_tenant, needs_the_database

NOW = datetime(2026, 10, 16, 12, 0, tzinfo=UTC)


async def claimed(sessions: async_sessionmaker[AsyncSession], org: str, message: str, at: datetime) -> str:
    """What claiming the message answers this delivery."""
    return await seen.claim_message(sessions, org, message, at=at)


@needs_the_database
async def test_a_message_claimed_is_reading_until_read_then_seen_for_every_later_delivery(
    sessions: async_sessionmaker[AsyncSession], tenant: Tenant
) -> None:
    """Meta delivers a message again and again: read once, every later delivery is dropped."""
    assert await claimed(sessions, tenant.org, "wamid.1", NOW) == "new"
    assert await claimed(sessions, tenant.org, "wamid.1", NOW + timedelta(seconds=1)) == "reading"
    await seen.mark_message_read(sessions, tenant.org, "wamid.1", at=NOW + timedelta(seconds=1))
    assert await claimed(sessions, tenant.org, "wamid.1", NOW + timedelta(seconds=2)) == "seen"
    assert await claimed(sessions, tenant.org, "wamid.1", NOW + seen.READING + timedelta(seconds=5)) == "seen"


@needs_the_database
async def test_one_orgs_message_id_never_shadows_anothers(
    sessions: async_sessionmaker[AsyncSession], tenant: Tenant
) -> None:
    """Two orgs may each receive a message with the same id."""
    other = await make_tenant(sessions)
    assert await claimed(sessions, tenant.org, "wamid.1", NOW) == "new"
    assert await claimed(sessions, other.org, "wamid.1", NOW) == "new"


@needs_the_database
async def test_a_claim_released_or_left_unread_past_its_lease_is_read_by_the_next_delivery(
    sessions: async_sessionmaker[AsyncSession], tenant: Tenant
) -> None:
    """A reading that failed gives the message back; one whose process died lapses after its lease."""
    assert await claimed(sessions, tenant.org, "wamid.1", NOW) == "new"
    await seen.release_message(sessions, tenant.org, "wamid.1")
    assert await claimed(sessions, tenant.org, "wamid.1", NOW + timedelta(seconds=1)) == "new"
    assert await claimed(sessions, tenant.org, "wamid.1", NOW + seen.READING) == "reading"
    assert await claimed(sessions, tenant.org, "wamid.1", NOW + seen.READING + timedelta(seconds=2)) == "new"


@needs_the_database
async def test_of_two_gateways_delivered_the_same_message_at_once_exactly_one_reads_it(
    sessions: async_sessionmaker[AsyncSession], tenant: Tenant
) -> None:
    """Twenty messages each delivered twice at once: every one is new to exactly one delivery."""
    claims = await asyncio.gather(
        *(claimed(sessions, tenant.org, f"wamid.{number}", NOW) for number in range(20) for _ in range(2))
    )
    assert claims.count("new") == 20
    assert claims.count("reading") == 20


@needs_the_database
async def test_the_ids_claimed_past_metas_seven_days_of_retries_are_forgotten(
    sessions: async_sessionmaker[AsyncSession], tenant: Tenant
) -> None:
    """Meta stops retrying after seven days: the ids older than that are let go, the newer kept."""
    old, new = f"wamid.old.{tenant.org}", f"wamid.new.{tenant.org}"
    await claimed(sessions, tenant.org, old, NOW - seen.SEEN_KEPT - timedelta(minutes=1))
    await claimed(sessions, tenant.org, new, NOW)
    async with sessions.begin() as session:
        assert await seen.forget_seen_before(session, NOW) >= 1
    assert await claimed(sessions, tenant.org, new, NOW + timedelta(seconds=1)) == "reading"
    assert await claimed(sessions, tenant.org, old, NOW + timedelta(seconds=1)) == "new"
