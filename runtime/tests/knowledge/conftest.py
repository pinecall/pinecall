"""What the knowledge tests share: an embedder on a fake vendor, a tenant's scope, the models built."""

import sys
from collections.abc import AsyncIterator

import httpx
import pytest

from pinecall_runtime.enums import Env
from pinecall_runtime.kit.auth import Scope
from pinecall_runtime.knowledge.service.embedder import Embedder
from pinecall_runtime.providers.schemas import Embedding
from pinecall_runtime.providers.service import plugins
from tests.conftest import Tenant
from tests.fakes.acme import ACME, MODEL, AcmeLLM
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
def models(monkeypatch: pytest.MonkeyPatch) -> list[AcmeLLM]:
    """Every acme model the runtime builds while the test runs, in order."""
    built: list[AcmeLLM] = []

    # The plugin is handed what its constructor names, so the signature is the plugin's own.
    class Kept(AcmeLLM):
        def __init__(
            self,
            *,
            api_key: str,
            model: str = MODEL,
            temperature: float = 1.0,
            replies: list[list[str | dict[str, object]]] | None = None,
        ) -> None:
            super().__init__(api_key=api_key, model=model, temperature=temperature, replies=replies)
            built.append(self)

    monkeypatch.setattr(sys.modules[f"{plugins.PLUGINS}.{ACME}"], "LLM", Kept)
    return built
