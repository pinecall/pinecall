"""What the knowledge tests share: an embedder on a fake vendor, a tenant's scope, the models built."""

from collections.abc import AsyncIterator

import httpx
import pytest

from runtime.actor import Scope
from runtime.enums import Env
from runtime.knowledge.service.embedder import Embedder
from runtime.providers.catalog import Embedding
from tests.conftest import Tenant
from tests.fakes import acme
from tests.fakes.acme import AcmeLLM
from tests.fakes.embeddings import Embeddings

# Every vector the fake vendor answers is the same: the vectors tie, and the words decide (BM25).
FLAT = Embedding(vendor="openrouter", url="https://embed.test/v1", model="embed-flat-1", shape="embeddings")


@pytest.fixture
def vendor() -> Embeddings:
    """The fake embeddings vendor, which keeps every request."""
    return Embeddings()


@pytest.fixture
async def embedder(vendor: Embeddings) -> AsyncIterator[Embedder]:
    """The box's embedder on a fake vendor that answers every text with the same unit vector."""
    async with httpx.AsyncClient(transport=vendor.transport()) as client:
        yield Embedder(FLAT, "a-key", client)


@pytest.fixture
def scope(tenant: Tenant) -> Scope:
    """The tenant's org, in the sandbox, as its own."""
    return Scope(tenant.org, Env.sandbox)


@pytest.fixture
def models() -> list[AcmeLLM]:
    """Every acme model the runtime builds while the test runs, in order."""
    acme.BUILT.clear()
    return acme.BUILT
