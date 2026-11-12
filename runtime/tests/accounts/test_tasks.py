"""The cache of verified keys hears every gateway's revocations: one it cannot read does not deafen it."""

import asyncio
import contextlib
import time
from types import SimpleNamespace
from typing import cast

import pytest
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from runtime.accounts.models import ApiKey
from runtime.accounts.service.actor import Verified
from runtime.accounts.service.key_cache import FORGET_CHANNEL, KeyCache, Remembered
from runtime.accounts.tasks import hear_revocations
from runtime.signal import LocalSignal
from tests.conftest import until


def a_cache(signal: LocalSignal) -> KeyCache:
    """A gateway's cache of keys, nothing behind it: only revocations are heard."""
    return KeyCache(cast(async_sessionmaker[AsyncSession], None), signal)


# A revocation that raised ended the listener, and every key revoked afterwards on another gateway
# stayed trusted here for as long as the cache kept it.
async def test_a_revocation_that_cannot_be_read_does_not_leave_a_revoked_key_trusted(
    caplog: pytest.LogCaptureFixture,
) -> None:
    signal = LocalSignal()
    hearing, revoking = a_cache(signal), a_cache(signal)

    async def listen() -> None:
        await hear_revocations.each(hearing, signal)

    listening = asyncio.create_task(listen())
    try:
        await until(lambda: bool(signal._listening.get(FORGET_CHANNEL)))
        key = cast(ApiKey, SimpleNamespace(subject="m_1", expires_at=None))
        hearing._kept["a-fingerprint"] = Remembered(Verified(key), time.monotonic() + 60)
        signal.publish(FORGET_CHANNEL, b"this is not a revocation")
        signal.publish(FORGET_CHANNEL, b'{"fingerprint": 7}')
        revoking.forget(fingerprint="a-fingerprint")
        await until(lambda: "a-fingerprint" not in hearing._kept)
        assert "reading a revocation of another gateway failed" in caplog.text
    finally:
        listening.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await listening
