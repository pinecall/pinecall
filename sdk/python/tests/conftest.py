"""What every suite shares: a fake gateway on a free port, started and stopped around a test."""

from collections.abc import AsyncIterator

import pytest

from tests.fakes.gateway import FakeGateway


@pytest.fixture
async def gateway() -> AsyncIterator[FakeGateway]:
    fake = FakeGateway()
    await fake.start()
    yield fake
    await fake.close()
