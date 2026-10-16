"""The operator's client: a verb over the gateway's `/v1/ops/*` endpoints, each answer read as its schema."""

import contextlib
from collections.abc import Mapping
from http import HTTPStatus
from types import TracebackType
from typing import Any, Self

import httpx
from pydantic import BaseModel, TypeAdapter

from pinecall_runtime.exceptions import GatewayUnavailable
from pinecall_runtime.kit.text import a_mapping

# The operator's endpoints read tables; five seconds means the database is down.
TIMEOUT_S = 5.0

type Params = Mapping[str, str | int | float | bool]


class OpsClient:
    """The gateway as the operator asks it, with the box's own key."""

    def __init__(self, url: str, key: str) -> None:
        """A client to the gateway at the URL, the key in the header and never the URL."""
        self.http = httpx.AsyncClient(base_url=url, headers={"Authorization": f"Bearer {key}"}, timeout=TIMEOUT_S)

    @property
    def base_url(self) -> str:
        """Where the gateway is."""
        return str(self.http.base_url).rstrip("/")

    async def __aenter__(self) -> Self:
        """Open."""
        return self

    async def __aexit__(
        self, kind: type[BaseException] | None, error: BaseException | None, trace: TracebackType | None
    ) -> None:
        """Closed."""
        await self.http.aclose()

    async def read[T](
        self, method: str, path: str, shape: type[T], *, body: object = None, params: Params | None = None
    ) -> T:
        """Ask, and read the answer as the shape: a schema, or `list[Schema]`."""
        answer = await self._answered(method, path, body, params)
        return TypeAdapter(shape).validate_python(answer.json())

    async def send(self, method: str, path: str, *, body: object = None, params: Params | None = None) -> None:
        """Ask, and expect no body back."""
        await self._answered(method, path, body, params)

    # A refusal is the gateway's own sentence; a gateway that is not there is said as such.
    async def _answered(self, method: str, path: str, body: object, params: Params | None) -> httpx.Response:
        try:
            answer = await self.http.request(method, path, json=_plain(body), params=dict(params or {}))
        except httpx.HTTPError as unreachable:
            raise GatewayUnavailable(f"{method} {path}: {self.base_url} did not answer ({unreachable})") from None
        if answer.is_success:
            return answer
        detail = answer.text.strip()
        with contextlib.suppress(ValueError, KeyError, TypeError):
            detail = str(answer.json()["detail"])
        status = HTTPStatus(answer.status_code).phrase if answer.status_code in HTTPStatus else ""
        raise GatewayUnavailable(f"{answer.status_code} {status}: {detail}".rstrip(), answered=answer.status_code)


def _plain(body: object) -> Any:
    if body is None:
        return None
    if a_mapping(body):
        return dict(body)
    if isinstance(body, BaseModel):
        return body.model_dump(mode="json", by_alias=True, exclude_none=True)
    raise TypeError(f"a body is a schema or a dict, not {type(body).__name__}")
