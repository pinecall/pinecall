"""The cache of verified keys hears every gateway's revocations: one it cannot read does not deafen it."""

import asyncio
import time
from collections.abc import AsyncIterator
from types import SimpleNamespace
from typing import cast

import pytest
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from pinecall_runtime.accounts.models import ApiKey
from pinecall_runtime.accounts.service.keys import FORGET_CHANNEL, KeyCache
from pinecall_runtime.redis import LocalSignal
from tests.conftest import until


def a_cache(signal: LocalSignal) -> KeyCache:
    """A gateway's cache of keys, nothing behind it: only revocations are heard."""
    return KeyCache(cast(async_sessionmaker[AsyncSession], None), signal)


@pytest.fixture
async def signal() -> AsyncIterator[LocalSignal]:
    """The in-process signal two gateways' caches are told on."""
    yield LocalSignal()


# A revocation that raised ended the listener, and every key revoked afterwards on another gateway
# stayed trusted here for as long as the cache kept it.
async def test_a_revocation_that_cannot_be_read_does_not_leave_a_revoked_key_trusted(
    signal: LocalSignal, caplog: pytest.LogCaptureFixture
) -> None:
    hearing, revoking = a_cache(signal), a_cache(signal)
    await hearing.start()
    try:
        await until(lambda: bool(signal._listening.get(FORGET_CHANNEL)))
        key = cast(ApiKey, SimpleNamespace(subject="m_1"))
        hearing._kept["a-fingerprint"] = (key, None, time.monotonic() + 60)
        signal.publish(FORGET_CHANNEL, b"this is not a revocation")
        signal.publish(FORGET_CHANNEL, b'{"fingerprint": 7}')
        revoking.forget(fingerprint_="a-fingerprint")
        await until(lambda: "a-fingerprint" not in hearing._kept)
        assert "reading a revocation of another gateway failed" in caplog.text
    finally:
        await asyncio.wait_for(hearing.close(), 5)
