"""The box's embedder over HTTP, in the two shapes a vendor speaks: batched, retried, its reply held to account."""

import asyncio
import base64
import logging
import math
import re
from array import array
from collections.abc import Awaitable, Callable, Iterator, Mapping
from typing import Any, Protocol

import httpx
from pydantic import BaseModel, ConfigDict
from pydantic import ValidationError as PydanticValidationError
from sqlalchemy.ext.asyncio import AsyncSession

from runtime.exceptions import ServiceUnavailable, UpstreamError
from runtime.kit.crypto import Vault
from runtime.kit.retry import retry
from runtime.kit.text import estimate_tokens
from runtime.providers import service as providers
from runtime.providers.catalog import Embedding
from runtime.providers.stage import Credentials

logger = logging.getLogger(__name__)

type Sleep = Callable[[float], Awaitable[None]]
# What finds the embedder a lookup or a hang-up runs on, in the transaction it reads the call's limits
# in: the box's (`box_embedder`), the providers row read each time; a test hands its own.
type FindEmbedder = Callable[[AsyncSession], Awaitable["Embedder | None"]]
type Vector = list[float]

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
# A server that asks for longer is misconfigured; its hour is not waited.
LONGEST_ASKED_S = 60.0
# A push waits for a contextual window of 24 000 tokens, which outlasts any client default; a
# query keeps the client's own, and the turn's budget bounds it.
PUSH_TIMEOUT = httpx.Timeout(connect=5.0, read=120.0, write=5.0, pool=5.0)


# The sentence reaches a tenant (a lookup's error on its call's log): it names the vendor and never
# where the box asked it, which is the operator's to read in the process's log.
class EmbedderUnreachable(UpstreamError):
    """The embedder did not answer with vectors."""

    def __init__(
        self,
        vendor: str,
        url: str,
        words: str,
        *,
        answered: int | None = None,
        retryable: bool = False,
        retry_after_s: float | None = None,
    ) -> None:
        super().__init__(
            f"{vendor} did not answer: {words}",
            vendor=vendor,
            answered=answered,
            retryable=retryable,
            retry_after_s=retry_after_s,
        )
        self.url = url
        self.words = words


class WrongWidth(UpstreamError):
    """The embedder answered vectors of another width than the columns hold."""


# ── the vendor's own JSON ──


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


# ── the two shapes ──


# A vendor speaks one of two: `embeddings` takes texts (OpenAI's), `contextual` takes documents of
# chunks, each chunk embedded knowing its neighbours. Chosen once, where the embedder is built: each
# shape has its own path, body, reply, decoding and way of splitting what the vendor found too big.
class Shape(Protocol):
    """One of the two formats an embeddings endpoint speaks, asked through the embedder that holds the key."""

    @property
    def path(self) -> str:
        """The endpoint's last segment, after the row's URL."""
        ...

    async def embed(self, asked: "Embedder", texts: list[str], waits: httpx.Timeout) -> list[Vector]:
        """One vector per text, in order."""
        ...

    async def embed_documents(
        self, asked: "Embedder", documents: list[list[str]], waits: httpx.Timeout
    ) -> list[list[Vector]]:
        """One list of vectors per document, one per chunk, in order."""
        ...


class Flat:
    """The `embeddings` shape: texts in, floats out, every text on its own."""

    path = "embeddings"

    async def embed(self, asked: "Embedder", texts: list[str], waits: httpx.Timeout) -> list[Vector]:
        """One vector per text, in order, as many texts to a request as its tokens allow."""
        return [vector for batch in _windows(texts, REQUEST_TOKENS) for vector in await self._send(asked, batch, waits)]

    async def embed_documents(
        self, asked: "Embedder", documents: list[list[str]], waits: httpx.Timeout
    ) -> list[list[Vector]]:
        """The documents' chunks embedded as one list of texts, then cut back into documents."""
        flat = await self.embed(asked, [chunk for chunks in documents for chunk in chunks], waits)
        sliced: list[list[Vector]] = []
        for chunks in documents:
            sliced.append(flat[: len(chunks)])
            flat = flat[len(chunks) :]
        return sliced

    # A split keeps the order: the first half's vectors, then the second's.
    async def _send(self, asked: "Embedder", texts: list[str], waits: httpx.Timeout, *, depth: int = 0) -> list[Vector]:
        try:
            return self._read(asked, await asked.post(self._body(asked.embedding, texts), waits), len(texts))
        except EmbedderUnreachable as refused:
            if depth >= MAX_SPLITS or len(texts) == 1 or not TOO_BIG.search(refused.words):
                raise
        middle = len(texts) // 2
        first = await self._send(asked, texts[:middle], waits, depth=depth + 1)
        return [*first, *await self._send(asked, texts[middle:], waits, depth=depth + 1)]

    # The request names the encoding: the reply is decoded as asked, never guessed from its bytes.
    def _body(self, embedding: Embedding, texts: list[str]) -> dict[str, Any]:
        return {
            "model": embedding.model,
            "input": list(texts),
            "encoding_format": "float",
            "dimensions": embedding.dimensions,
        }

    def _read(self, asked: "Embedder", content: bytes, sent: int) -> list[Vector]:
        try:
            rows = _Rows.model_validate_json(content).data
        except PydanticValidationError as unread:
            raise asked.unreachable(f"a reply that is not its vectors: {unread}") from unread
        if len(rows) != sent:
            raise asked.unreachable(f"{len(rows)} vectors for {sent} chunks")
        return asked.check([self._decode(asked, row.embedding) for row in _in_order(asked, rows)])

    def _decode(self, asked: "Embedder", embedding: list[float] | str) -> Vector:
        if isinstance(embedding, str):
            raise asked.unreachable("a base64 vector where floats were asked for")
        return embedding


class Contextual:
    """The `contextual` shape: documents of chunks in, signed bytes out, a chunk embedded among its neighbours."""

    path = "contextualizedembeddings"

    async def embed(self, asked: "Embedder", texts: list[str], waits: httpx.Timeout) -> list[Vector]:
        """One vector per text, in order: each text is a one-chunk document, so it shares the chunks' space."""
        return [vectors[0] for vectors in await self._embed_contexts(asked, [[text] for text in texts], waits)]

    async def embed_documents(
        self, asked: "Embedder", documents: list[list[str]], waits: httpx.Timeout
    ) -> list[list[Vector]]:
        """One list of vectors per document; a document past the context goes out as windows of it."""
        windows = [(at, window) for at, chunks in enumerate(documents) for window in _windows(chunks, WINDOW_TOKENS)]
        answered = await self._embed_contexts(asked, [window for _, window in windows], waits)
        cut: list[list[Vector]] = [[] for _ in documents]
        for (at, _), vectors in zip(windows, answered, strict=True):
            cut[at].extend(vectors)
        return cut

    # Documents go out as many to a request as its tokens and its count allow.
    async def _embed_contexts(
        self, asked: "Embedder", documents: list[list[str]], waits: httpx.Timeout
    ) -> list[list[Vector]]:
        return [
            vectors
            for batch in _batches(documents, REQUEST_TOKENS, MOST_DOCUMENTS)
            for vectors in await self._send(asked, batch, waits)
        ]

    # A split keeps the order: the first half's documents, then the second's; one document refused
    # alone is split into two of its chunks, as a window too big for the vendor is.
    async def _send(
        self, asked: "Embedder", documents: list[list[str]], waits: httpx.Timeout, *, depth: int = 0
    ) -> list[list[Vector]]:
        try:
            return self._read(asked, await asked.post(self._body(asked.embedding, documents), waits), documents)
        except EmbedderUnreachable as refused:
            if depth >= MAX_SPLITS or not TOO_BIG.search(refused.words):
                raise
            if len(documents) == 1 and len(documents[0]) == 1:
                raise
        if len(documents) == 1:
            [chunks] = documents
            middle = len(chunks) // 2
            first = await self._send(asked, [chunks[:middle]], waits, depth=depth + 1)
            second = await self._send(asked, [chunks[middle:]], waits, depth=depth + 1)
            return [[*first[0], *second[0]]]
        middle = len(documents) // 2
        first = await self._send(asked, documents[:middle], waits, depth=depth + 1)
        return [*first, *await self._send(asked, documents[middle:], waits, depth=depth + 1)]

    # The request names the encoding: the reply is decoded as asked, never guessed from its bytes.
    def _body(self, embedding: Embedding, documents: list[list[str]]) -> dict[str, Any]:
        return {
            "model": embedding.model,
            "input": [list(chunks) for chunks in documents],
            "encoding_format": "base64_int8",
            "dimensions": embedding.dimensions,
        }

    def _read(self, asked: "Embedder", content: bytes, documents: list[list[str]]) -> list[list[Vector]]:
        try:
            answered = _Documents.model_validate_json(content).data
        except PydanticValidationError as unread:
            raise asked.unreachable(f"a reply that is not its vectors: {unread}") from unread
        if len(answered) != len(documents):
            raise asked.unreachable(f"{len(answered)} documents for the {len(documents)} it was sent")
        cut: list[list[Vector]] = []
        for document, chunks in zip(_in_order(asked, answered), documents, strict=True):
            if len(document.data) != len(chunks):
                raise asked.unreachable(f"{len(document.data)} vectors for {len(chunks)} chunks")
            cut.append(asked.check([self._decode(asked, row.embedding) for row in _in_order(asked, document.data)]))
        return cut

    def _decode(self, asked: "Embedder", embedding: list[float] | str) -> Vector:
        if not isinstance(embedding, str):
            raise asked.unreachable("floats where base64_int8 was asked for")
        # Signed: -1 travels as 0xff, and read unsigned it would be 255.
        values = array("b")
        values.frombytes(base64.b64decode(embedding))
        return [float(value) for value in values]


def shape_of(embedding: Embedding) -> Shape:
    """The shape the row says its embedder speaks."""
    match embedding.shape:
        case "embeddings":
            return Flat()
        case "contextual":
            return Contextual()


# ── the embedder ──


class Embedder:
    """The embedder the box's `embedding` names, on the box's key, over one HTTP client."""

    def __init__(
        self,
        embedding: Embedding,
        key: Credentials,
        client: httpx.AsyncClient,
        *,
        sleep: Sleep = asyncio.sleep,
    ) -> None:
        self.embedding = embedding
        self._shape = shape_of(embedding)
        self._url = f"{embedding.url.rstrip('/')}/{self._shape.path}"
        self._headers = {"Authorization": f"Bearer {_key_of(embedding.vendor, key)}"}
        self._client = client
        self._sleep = sleep

    @property
    def model(self) -> str:
        """The model's name, which every vector is kept under."""
        return self.embedding.model

    async def embed(self, texts: list[str]) -> list[Vector]:
        """One unit vector per text, in order; on `contextual` each text is a one-chunk document."""
        return await self._shape.embed(self, texts, self._client.timeout)

    async def embed_documents(self, documents: list[list[str]]) -> list[list[Vector]]:
        """One list of unit vectors per document, one per chunk, in order."""
        return await self._shape.embed_documents(self, documents, PUSH_TIMEOUT)

    # ── what its shape asks of it ──

    # Asked again while the failure says it may help (`kit.retry`): the wait the server asked for,
    # else one that grows. Said in the log once, when it is given up.
    async def post(self, body: dict[str, Any], waits: httpx.Timeout) -> bytes:
        """The vendor's reply to one request; EmbedderUnreachable, in its own words, when it gives none."""
        try:
            return await retry(lambda: self._post_once(body, waits), retries=RETRIES, sleep=self._sleep)
        except EmbedderUnreachable as failed:
            logger.warning("the embedder at %s did not answer: %s", self._url, failed.words)
            raise

    def unreachable(self, words: str) -> EmbedderUnreachable:
        """The refusal of a reply that is not the vectors asked for, said in the log as it is made."""
        logger.warning("the embedder at %s did not answer: %s", self._url, words)
        return EmbedderUnreachable(self.embedding.vendor, self._url, words)

    def check(self, vectors: list[Vector]) -> list[Vector]:
        """The vectors at unit length, once each is as wide as the columns; WrongWidth otherwise."""
        widths = sorted({len(vector) for vector in vectors})
        if widths and widths != [self.embedding.dimensions]:
            answered = " and ".join(str(width) for width in widths)
            raise WrongWidth(
                f"{self.embedding.model} answers {answered}-wide vectors; every vector column holds "
                f"{self.embedding.dimensions}"
            )
        return [_unit(vector) for vector in vectors]

    async def _post_once(self, body: dict[str, Any], waits: httpx.Timeout) -> bytes:
        vendor = self.embedding.vendor
        try:
            answer = await self._client.post(self._url, json=body, headers=self._headers, timeout=waits)
        except httpx.TransportError as failed:
            silence = str(failed) or type(failed).__name__
            raise EmbedderUnreachable(vendor, self._url, silence, retryable=True) from failed
        refusal = _refusal_in(answer)
        if refusal is None:
            return answer.content
        retryable = answer.status_code in RETRYABLE or answer.is_server_error
        raise EmbedderUnreachable(
            vendor,
            self._url,
            refusal,
            answered=answer.status_code,
            retryable=retryable,
            retry_after_s=_wait_asked(answer.headers) if retryable else None,
        )


# Built per request from the row and the box's keys, so an edited row takes from the next request. Until
# 2026-11 the gateway built the one its calls used once, as it started, and kept it: a box that started
# with no embedder and was given one pushed at once and no call searched or remembered until the gateway
# was restarted, and a row edited to another model made every lookup refuse the bases pushed since.
def box_embedder(vault: Vault, http: httpx.AsyncClient) -> FindEmbedder:
    """The box's embedder, as the providers row names it at the moment it is asked for."""

    async def find(session: AsyncSession) -> Embedder | None:
        return await embedder_of(session, vault, http)

    return find


async def embedder_of(session: AsyncSession, vault: Vault, http: httpx.AsyncClient) -> Embedder | None:
    """The embedder the providers row names, on the box's key for its vendor; None when it names none."""
    catalog = await providers.get_catalog(session)
    if catalog.embedding is None:
        return None
    key = (await providers.box_credentials(session, vault)).get(catalog.embedding.vendor)
    if key is None:
        raise ServiceUnavailable(
            f"the providers row names {catalog.embedding.vendor} as the embedder and the box holds no key for it"
        )
    return Embedder(catalog.embedding, key, http)


# ── private ──


# Sorting alone is not enough: indexes 0, 0, 2 sort cleanly and give two chunks one vector,
# or two documents one list.
def _in_order[Indexed: (_Row, _Rows)](asked: Embedder, rows: list[Indexed]) -> list[Indexed]:
    if any(row.index is None for row in rows):
        return rows
    ordered = sorted(rows, key=lambda row: row.index or 0)
    indexes = [row.index for row in ordered]
    if indexes != list(range(len(rows))):
        raise asked.unreachable(f"a reply indexed {indexes}, not 0 to {len(rows) - 1}")
    return ordered


# A text over the budget goes alone: the vendor refuses it or cuts it, and a refusal is split.
def _windows(texts: list[str], budget: int) -> Iterator[list[str]]:
    window: list[str] = []
    tokens = 0
    for text in texts:
        cost = estimate_tokens(text)
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
        cost = sum(estimate_tokens(chunk) for chunk in chunks)
        if batch and (tokens + cost > budget or len(batch) == most):
            yield batch
            batch, tokens = [], 0
        batch.append(chunks)
        tokens += cost
    if batch:
        yield batch


def _key_of(vendor: str, key: Credentials) -> str:
    if isinstance(key, str):
        return key
    named = key.get("api_key")
    if isinstance(named, str):
        return named
    raise ServiceUnavailable(f"the box's credentials for {vendor} hold no api_key")


# A gateway may refuse with a 200 and an `error` body: the words are read whatever the status.
def _refusal_in(answer: httpx.Response) -> str | None:
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


# `retry-after-ms` first: a server that says 1500 ms is not rounded up to two seconds. A wait out of
# bounds is no wait asked: the retry falls back to its own.
def _wait_asked(headers: Mapping[str, str]) -> float | None:
    for name, scale in (("retry-after-ms", 0.001), ("retry-after", 1.0)):
        raw = headers.get(name)
        if raw is None:
            continue
        try:
            asked = float(raw) * scale
        except ValueError:
            continue
        return asked if 0 < asked <= LONGEST_ASKED_S else None
    return None


# Both shapes answer unnormalised vectors; a zero vector has no direction to keep.
def _unit(vector: Vector) -> Vector:
    length = math.sqrt(sum(value * value for value in vector))
    return vector if length == 0 else [value / length for value in vector]
