"""What every suite shares: a fake gateway and a fake app's doors, each on a free port."""

from collections.abc import AsyncIterator

import pytest

from pinecall._app_work import AppDoor
from tests.fakes.gateway import FakeGateway
from tests.fakes.kept import KeptApp


@pytest.fixture
async def gateway() -> AsyncIterator[FakeGateway]:
    fake = FakeGateway()
    await fake.start()
    yield fake
    await fake.close()


@pytest.fixture
async def kept() -> AsyncIterator[KeptApp]:
    fake = KeptApp()
    await fake.start()
    yield fake
    await fake.close()


@pytest.fixture
def door(kept: KeptApp) -> AppDoor:
    return kept.door
