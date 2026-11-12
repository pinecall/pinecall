"""The cache of verified keys hears every gateway's revocations: one it cannot read does not deafen it."""

import asyncio
import contextlib

import pytest
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from runtime.accounts.service import keys
from runtime.accounts.service.key_cache import FORGET_CHANNEL, REMEMBERED_FOR_S, KeyCache
from runtime.accounts.tasks import hear_revocations
from runtime.kit.crypto import fingerprint
from runtime.signal import LocalSignal
from tests.conftest import Tenant, needs_the_database

# Well inside what a cache keeps a key for: a key forgotten within it was forgotten because it was told.
TOLD_WITHIN_S = REMEMBERED_FOR_S / 2


def test_the_revocations_are_heard_by_a_loop_the_process_starts() -> None:
    assert hear_revocations.name == "revocations"


# A revocation that raised ended the listener, and every key revoked afterwards on another gateway
# stayed trusted here for as long as the cache kept it. Two gateways' caches on one signal: the key
# is the tenant's own, verified here, then revoked there, in the database, as an endpoint does it.
@needs_the_database
async def test_a_revocation_that_cannot_be_read_does_not_leave_a_revoked_key_trusted(
    sessions: async_sessionmaker[AsyncSession], tenant: Tenant, caplog: pytest.LogCaptureFixture
) -> None:
    signal = LocalSignal()
    hearing, revoking = KeyCache(sessions, signal), KeyCache(sessions, signal)
    listening = asyncio.ensure_future(hear_revocations.each(hearing, signal))
    try:
        # The listener is there once a message has somebody to hear it; neither of these can be read.
        while await signal.publish_now(FORGET_CHANNEL, b"this is not a revocation") == 0:
            await asyncio.sleep(0.01)
        signal.publish(FORGET_CHANNEL, b'{"fingerprint": 7}')
        assert await hearing.verify(tenant.server_key) is not None
        async with sessions.begin() as session:
            await keys.revoke_fingerprint(session, revoking, fingerprint(tenant.server_key))
        async with asyncio.timeout(TOLD_WITHIN_S):
            while await hearing.verify(tenant.server_key) is not None:
                await asyncio.sleep(0.02)
        assert "reading a revocation of another gateway failed" in caplog.text
    finally:
        listening.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await listening
