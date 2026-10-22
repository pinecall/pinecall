"""The box's embedder over HTTP, OpenAI-shaped or contextual: batched, retried, validated."""

import asyncio
import base64
import logging
import math
import re
import secrets
import struct
from array import array
from collections.abc import Awaitable, Callable, Iterator, Mapping
from typing import Any

import httpx
from pydantic import BaseModel, ConfigDict
from pydantic import ValidationError as PydanticValidationError

from pinecall_runtime.exceptions import ServiceUnavailable, UpstreamError
from pinecall_runtime.providers import service as providers
from pinecall_runtime.providers.service import plugins

logger = logging.getLogger(__name__)

type Sleep = Callable[[float], Awaitable[None]]

# The cutter measures a chunk with the same estimate, so a chunk that fits its cap fits a window.
TOKENS_PER_WORD = 1.3
# The contextual endpoint counts a window's chunks together against a 32 768-token context; the
# margin is for the estimate.
WINDOW_TOKENS = 24_000
REQUEST_TOKENS = 100_000
# A contextual request carries many documents, each its own context (Perplexity: 512 at most).
MOST_DOCUMENTS = 512
# Only a refusal about size is split: halving a credential refusal fails it twice.
TOO_BIG = re.compile(
    r"exceeds maximum|too many tokens|maximum context length|reduce the length|input is too "
    r"large|max_tokens_per_request",
    re.IGNORECASE,
)
MAX_SPLITS = 5
RETRIES = 2
# The request was fine and the server was not: a timeout, a lock, a rate limit, or a 5xx.
RETRYABLE = frozenset({408, 409, 429})
FIRST_WAIT_S = 0.5
LONGEST_WAIT_S = 8.0
# A server that asks for longer is misconfigured; its hour is not waited.
LONGEST_ASKED_S = 60.0
# A push waits for a contextual window of 24 000 tokens, which outlasts any client default; a
# query keeps the client's own, and the turn's budget bounds it.
PUSH_TIMEOUT = httpx.Timeout(connect=5.0, read=120.0, write=5.0, pool=5.0)

NO_EMBEDDER = (
    "this box has no embedder: the providers row names none under `embedding`, so nothing can be "
    "pushed, searched or remembered"
)


# The sentence reaches a tenant (a lookup's error on its call's log): it names the vendor and never
# where the box asked it, which is the operator's to read in the process's log.
class EmbedderUnreachable(UpstreamError):
    """The embedder did not answer with vectors."""

    def __init__(self, vendor: str, url: str, words: str) -> None:
        super().__init__(f"{vendor} did not answer: {words}")
        self.url = url
        self.words = words


class WrongWidth(UpstreamError):
    """The embedder answered vectors of another width than the columns hold."""


class WrongModel(ServiceUnavailable):
    """A base was embedded by another model than the box runs now."""

    def __init__(self, base: str, written_by: str, running: str) -> None:
        super().__init__(
            f"base {base} was embedded by {written_by} and this box embeds with {running}: push it again "
            "so its vectors are in the model's space"
        )


class _Refusal(BaseModel):
    model_config = ConfigDict(frozen=True, extra="ignore")
    message: str = ""


class _Answer(BaseModel):
    model_config = ConfigDict(frozen=True, extra="ignore")
    error: _Refusal | str | None = None


class _Row(BaseModel):
    model_config = ConfigDict(frozen=True, extra="ignore")
    index: int | None = None
    embedding: list[float] | str


class _Rows(BaseModel):
    model_config = ConfigDict(frozen=True, extra="ignore")
    index: int | None = None
    data: list[_Row]


class _Documents(BaseModel):
    model_config = ConfigDict(frozen=True, extra="ignore")
    data: list[_Rows]


class Embedder:
    """The embedder the box's `embedding` names, on the box's key, over one HTTP client."""

    def __init__(
        self,
        embedding: providers.Embedding,
        key: plugins.Credentials,
        client: httpx.AsyncClient,
        *,
        sleep: Sleep = asyncio.sleep,
    ) -> None:
        self.embedding = embedding
        path = "embeddings" if embedding.shape == "embeddings" else "contextualizedembeddings"
        self._url = f"{embedding.url.rstrip('/')}/{path}"
        self._headers = {"Authorization": f"Bearer {_key_of(embedding.vendor, key)}"}
        self._client = client
        self._sleep = sleep

    @property
    def model(self) -> str:
        """The model's name, which every vector is kept under."""
        return self.embedding.model

    async def embed(self, texts: list[str]) -> list[list[float]]:
        """One unit vector per text, in order; on `contextual` each text is a one-chunk document."""
        waits = self._client.timeout
        if self.embedding.shape == "contextual":
            return [vectors[0] for vectors in await self._contexts([[text] for text in texts], waits)]
        return [vector for batch in _windows(texts, REQUEST_TOKENS) for vector in await self._sent(batch, waits)]

    async def embed_documents(self, documents: list[list[str]]) -> list[list[list[float]]]:
        """One list of unit vectors per document, one per chunk, in order."""
        if self.embedding.shape == "contextual":
            # A document past the context goes out as windows of it, each its own context.
            windows = [
                (at, window) for at, chunks in enumerate(documents) for window in _windows(chunks, WINDOW_TOKENS)
            ]
            answered = await self._contexts([window for _, window in windows], PUSH_TIMEOUT)
            cut: list[list[list[float]]] = [[] for _ in documents]
            for (at, _), vectors in zip(windows, answered, strict=True):
                cut[at].extend(vectors)
            return cut
        every = [chunk for chunks in documents for chunk in chunks]
        flat = [vector for batch in _windows(every, REQUEST_TOKENS) for vector in await self._sent(batch, PUSH_TIMEOUT)]
        sliced: list[list[list[float]]] = []
        for chunks in documents:
            sliced.append(flat[: len(chunks)])
            flat = flat[len(chunks) :]
        return sliced

    # Documents go out as many to a request as its tokens and its count allow.
    async def _contexts(self, documents: list[list[str]], waits: httpx.Timeout) -> list[list[list[float]]]:
        return [
            vectors
            for batch in _batches(documents, REQUEST_TOKENS, MOST_DOCUMENTS)
            for vectors in await self._sent_contexts(batch, waits)
        ]

    # A split keeps the order: the first half's documents, then the second's; one document refused
    # alone is split into two of its chunks, as a window too big for the vendor is.
    async def _sent_contexts(
        self, documents: list[list[str]], waits: httpx.Timeout, *, depth: int = 0
    ) -> list[list[list[float]]]:
        try:
            return self._contextual_vectors(await self._posted(self._contextual_body(documents), waits), documents)
        except EmbedderUnreachable as refused:
            if depth >= MAX_SPLITS or not TOO_BIG.search(refused.words):
                raise
            if len(documents) == 1 and len(documents[0]) == 1:
                raise
        if len(documents) == 1:
            [chunks] = documents
            middle = len(chunks) // 2
            first = await self._sent_contexts([chunks[:middle]], waits, depth=depth + 1)
            second = await self._sent_contexts([chunks[middle:]], waits, depth=depth + 1)
            return [[*first[0], *second[0]]]
        middle = len(documents) // 2
        first = await self._sent_contexts(documents[:middle], waits, depth=depth + 1)
        return [*first, *await self._sent_contexts(documents[middle:], waits, depth=depth + 1)]

    # A split keeps the order: the first half's vectors, then the second's.
    async def _sent(self, texts: list[str], waits: httpx.Timeout, *, depth: int = 0) -> list[list[float]]:
        try:
            return self._vectors(await self._posted(self._flat_body(texts), waits), len(texts))
        except EmbedderUnreachable as refused:
            if depth >= MAX_SPLITS or len(texts) == 1 or not TOO_BIG.search(refused.words):
                raise
        middle = len(texts) // 2
        first = await self._sent(texts[:middle], waits, depth=depth + 1)
        return [*first, *await self._sent(texts[middle:], waits, depth=depth + 1)]

    async def _posted(self, body: dict[str, Any], waits: httpx.Timeout) -> bytes:
        attempt = 0
        while True:
            try:
                answer = await self._client.post(self._url, json=body, headers=self._headers, timeout=waits)
            except httpx.TransportError as failed:
                if attempt == RETRIES:
                    raise self._unreachable(str(failed) or type(failed).__name__) from failed
                await self._sleep(_wait(attempt, {}))
                attempt += 1
                continue
            retryable = answer.status_code in RETRYABLE or answer.is_server_error
            if retryable and attempt < RETRIES:
                await self._sleep(_wait(attempt, answer.headers))
                attempt += 1
                continue
            words = _refused_by(answer)
            if words is not None:
                raise self._unreachable(words)
            return answer.content

    # The request names the encoding: the reply is decoded as asked, never guessed from its bytes.
    def _contextual_body(self, documents: list[list[str]]) -> dict[str, Any]:
        return {
            "model": self.embedding.model,
            "input": [list(chunks) for chunks in documents],
            "encoding_format": "base64_int8",
            "dimensions": self.embedding.dimensions,
        }

    def _flat_body(self, texts: list[str]) -> dict[str, Any]:
        return {
            "model": self.embedding.model,
            "input": list(texts),
            "encoding_format": "float",
            "dimensions": self.embedding.dimensions,
        }

    def _contextual_vectors(self, content: bytes, documents: list[list[str]]) -> list[list[list[float]]]:
        try:
            answered = _Documents.model_validate_json(content).data
        except PydanticValidationError as unread:
            raise self._unreachable(f"a reply that is not its vectors: {unread}") from unread
        if len(answered) != len(documents):
            raise self._unreachable(f"{len(answered)} documents for the {len(documents)} it was sent")
        cut: list[list[list[float]]] = []
        for document, chunks in zip(self._in_order(answered), documents, strict=True):
            if len(document.data) != len(chunks):
                raise self._unreachable(f"{len(document.data)} vectors for {len(chunks)} chunks")
            cut.append(self._checked([self._decoded(row.embedding) for row in self._in_order(document.data)]))
        return cut

    def _vectors(self, content: bytes, sent: int) -> list[list[float]]:
        try:
            rows = _Rows.model_validate_json(content).data
        except PydanticValidationError as unread:
            raise self._unreachable(f"a reply that is not its vectors: {unread}") from unread
        if len(rows) != sent:
            raise self._unreachable(f"{len(rows)} vectors for {sent} chunks")
        return self._checked([self._decoded(row.embedding) for row in self._in_order(rows)])

    def _checked(self, vectors: list[list[float]]) -> list[list[float]]:
        widths = sorted({len(vector) for vector in vectors})
        if widths and widths != [self.embedding.dimensions]:
            answered = " and ".join(str(width) for width in widths)
            raise WrongWidth(
                f"{self.embedding.model} answers {answered}-wide vectors; every vector column holds "
                f"{self.embedding.dimensions}"
            )
        return [_unit(vector) for vector in vectors]

    # Sorting alone is not enough: indexes 0, 0, 2 sort cleanly and give two chunks one vector,
    # or two documents one list.
    def _in_order[Indexed: (_Row, _Rows)](self, rows: list[Indexed]) -> list[Indexed]:
        if any(row.index is None for row in rows):
            return rows
        ordered = sorted(rows, key=lambda row: row.index or 0)
        indexes = [row.index for row in ordered]
        if indexes != list(range(len(rows))):
            raise self._unreachable(f"a reply indexed {indexes}, not 0 to {len(rows) - 1}")
        return ordered

    def _decoded(self, embedding: list[float] | str) -> list[float]:
        if self.embedding.shape == "embeddings":
            if isinstance(embedding, str):
                raise self._unreachable("a base64 vector where floats were asked for")
            return embedding
        if not isinstance(embedding, str):
            raise self._unreachable("floats where base64_int8 was asked for")
        # Signed: -1 travels as 0xff, and read unsigned it would be 255.
        values = array("b")
        values.frombytes(base64.b64decode(embedding))
        return [float(value) for value in values]

    def _unreachable(self, words: str) -> EmbedderUnreachable:
        logger.warning("the embedder at %s did not answer: %s", self._url, words)
        return EmbedderUnreachable(self.embedding.vendor, self._url, words)


def embedder_for(
    catalog: providers.Catalog, box_keys: Mapping[str, plugins.Credentials], client: httpx.AsyncClient
) -> Embedder | None:
    """The embedder the providers row names, on the box's key for its vendor; None when it names none."""
    if catalog.embedding is None:
        return None
    key = box_keys.get(catalog.embedding.vendor)
    if key is None:
        raise ServiceUnavailable(
            f"the providers row names {catalog.embedding.vendor} as the embedder and the box holds no key for it"
        )
    return Embedder(catalog.embedding, key, client)


def estimated_tokens(text: str) -> int:
    """The tokens a text costs, estimated as its words times 1.3; no tokenizer is loaded."""
    return round(len(text.split()) * TOKENS_PER_WORD)


# pgvector parses the text and the SQL casts it (`::halfvec`), so the driver needs no vector type.
def halfvec(vector: list[float]) -> str:
    """The vector as pgvector's text, each value rounded to IEEE half precision as the column is."""
    return "[" + ",".join(str(_half(value)) for value in vector) + "]"


def _half(value: float) -> float:
    rounded: float = struct.unpack("<e", struct.pack("<e", value))[0]
    return rounded


# A text over the budget goes alone: the vendor refuses it or cuts it, and a refusal is split.
def _windows(texts: list[str], budget: int) -> Iterator[list[str]]:
    window: list[str] = []
    tokens = 0
    for text in texts:
        cost = estimated_tokens(text)
        if window and tokens + cost > budget:
            yield window
            window, tokens = [], 0
        window.append(text)
        tokens += cost
    if window:
        yield window


# Whole documents, while their tokens fit the request and their count the vendor's; one over the
# budget goes alone.
def _batches(documents: list[list[str]], budget: int, most: int) -> Iterator[list[list[str]]]:
    batch: list[list[str]] = []
    tokens = 0
    for chunks in documents:
        cost = sum(estimated_tokens(chunk) for chunk in chunks)
        if batch and (tokens + cost > budget or len(batch) == most):
            yield batch
            batch, tokens = [], 0
        batch.append(chunks)
        tokens += cost
    if batch:
        yield batch


def _key_of(vendor: str, key: plugins.Credentials) -> str:
    if isinstance(key, str):
        return key
    named = key.get("api_key")
    if isinstance(named, str):
        return named
    raise ServiceUnavailable(f"the box's credentials for {vendor} hold no api_key")


# A gateway may refuse with a 200 and an `error` body: the words are read whatever the status.
def _refused_by(answer: httpx.Response) -> str | None:
    try:
        payload = _Answer.model_validate_json(answer.content).error
    except PydanticValidationError:
        payload = None
    if isinstance(payload, _Refusal) and payload.message:
        return payload.message
    if isinstance(payload, str) and payload:
        return payload
    if answer.is_error or payload is not None:
        return f"HTTP {answer.status_code}"
    return None


def _wait(attempt: int, headers: Mapping[str, str]) -> float:
    asked = _retry_after(headers)
    if asked is not None and 0 < asked <= LONGEST_ASKED_S:
        return asked
    backoff = min(FIRST_WAIT_S * 2.0**attempt, LONGEST_WAIT_S)
    # The jitter only shortens the wait, so the longest wait stays the longest.
    return backoff * (1 - 0.25 * secrets.SystemRandom().random())


# `retry-after-ms` first: a server that says 1500 ms is not rounded up to two seconds.
def _retry_after(headers: Mapping[str, str]) -> float | None:
    for name, scale in (("retry-after-ms", 0.001), ("retry-after", 1.0)):
        raw = headers.get(name)
        if raw is None:
            continue
        try:
            return float(raw) * scale
        except ValueError:
            continue
    return None


# Both shapes answer unnormalised vectors; a zero vector has no direction to keep.
def _unit(vector: list[float]) -> list[float]:
    length = math.sqrt(sum(value * value for value in vector))
    return vector if length == 0 else [value / length for value in vector]
