"""A WhatsApp message read once: claimed by the delivery that reads it, dropped by the later ones."""

import logging
from collections.abc import Awaitable, Callable
from datetime import datetime, timedelta

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from runtime.whatsapp.models import Claim
from runtime.whatsapp.repository import WhatsappSeenRepository

logger = logging.getLogger(__name__)

# Meta retries a webhook not answered 200 with decreasing frequency for up to 7 days
# (developers.facebook.com/docs/whatsapp/cloud-api/guides/set-up-webhooks): an id is kept as long.
SEEN_KEPT = timedelta(days=7)
# Longer than a delivery is ever read in (the route, and opening the conversation at worst): a
# claim still unread past it is a process that died reading it, and the next delivery reads it.
READING = timedelta(minutes=10)


# Meta delivers a message again when it thinks it unanswered. The row is claimed before the
# message is read, so of two deliveries at once only one reads it; it is marked read once the
# message is queued or kept, and a reading that fails gives the claim back, so Meta's next
# delivery reads it again. A process that dies mid-reading leaves a claim its lease expires.
#
# Each of the three is a transaction of its own, committed before the next thing happens. Until
# 2026-11 they ran on the session of the webhook's request, which commits when the route returns: a
# second delivery never saw `reading` (its insert waited on the first one's row lock, holding a
# connection, until that request ended or the statement timed out), and a claim lasted only as long
# as the request did not fail.
async def read_once(
    sessions: async_sessionmaker[AsyncSession],
    org: str,
    message_id: str,
    read: Callable[[], Awaitable[None]],
    *,
    at: datetime,
) -> bool:
    """Read the org's message unless a delivery read it before; False while another is reading it."""
    claim = await claim_message(sessions, org, message_id, at=at)
    if claim is not Claim.new:
        logger.info("whatsapp: message %s delivered again, dropped: %s", message_id, claim)
        return claim is Claim.seen
    try:
        await read()
    except Exception:
        await release_message(sessions, org, message_id)
        raise
    await mark_message_read(sessions, org, message_id, at=at)
    return True


# The insert is the check: of two deliveries at once, one inserts and the other finds the row.
async def claim_message(
    sessions: async_sessionmaker[AsyncSession], org: str, message_id: str, *, at: datetime
) -> Claim:
    """Claim the org's message for this delivery, unless another has read it or is reading it."""
    async with sessions.begin() as session:
        repository = WhatsappSeenRepository(session)
        if await repository.claim(org, message_id, at=at, stale_before=at - READING):
            return Claim.new
        row = await repository.find(org, message_id)
    # A row gone between the two is a claim released: the delivery that held it failed.
    return Claim.seen if row is not None and row.read_at is not None else Claim.reading


async def mark_message_read(
    sessions: async_sessionmaker[AsyncSession], org: str, message_id: str, *, at: datetime
) -> None:
    """The claimed message is read: every later delivery of it is dropped."""
    async with sessions.begin() as session:
        await WhatsappSeenRepository(session).mark_read(org, message_id, at=at)


async def release_message(sessions: async_sessionmaker[AsyncSession], org: str, message_id: str) -> None:
    """Give up the claim of a message whose reading failed, so Meta's next delivery reads it."""
    async with sessions.begin() as session:
        await WhatsappSeenRepository(session).release(org, message_id)


async def forget_seen_before(session: AsyncSession, now: datetime) -> int:
    """Forget the message ids claimed longer ago than Meta retries; how many."""
    return await WhatsappSeenRepository(session).delete_before(now - SEEN_KEPT)
