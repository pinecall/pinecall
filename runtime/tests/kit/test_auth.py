"""The actor is resolved before any endpoint, and a database that does not answer there is still a 503."""

from types import SimpleNamespace
from typing import Any

from fastapi.responses import JSONResponse
from sqlalchemy.exc import TimeoutError as PoolTimeout
from sqlalchemy.ext.asyncio import AsyncSession
from starlette.requests import HTTPConnection, Request
from starlette.types import Message, Receive, Scope, Send

from pinecall_runtime.exceptions import PinecallError
from pinecall_runtime.kit.auth import Actor, ActorMiddleware


class _Starved:
    """A session maker whose pool has no connection free."""

    def __call__(self) -> AsyncSession:
        raise PoolTimeout("QueuePool limit of size 1 overflow 0 reached, connection timed out, timeout 2.00")


async def _never_resolves(_request: HTTPConnection, _session: AsyncSession) -> Actor | None:
    raise AssertionError("no session was opened: nothing to resolve with")


async def _refusal(_request: Request, error: Exception) -> JSONResponse:
    status = error.status if isinstance(error, PinecallError) else 500
    return JSONResponse({"detail": str(error)}, status_code=status)


async def _not_reached(_scope: Scope, _receive: Receive, _send: Send) -> None:
    raise AssertionError("the endpoint was reached with no actor")


# The app's exception handlers never see a middleware's error: before 2026-10-21 this was
# uvicorn's 500 and a traceback in the journal.
async def test_a_pool_with_no_connection_free_is_answered_503_before_any_endpoint() -> None:
    middleware = ActorMiddleware(_not_reached, resolve=_never_resolves, refuse=_refusal)
    scope: dict[str, Any] = {
        "type": "http",
        "method": "GET",
        "path": "/v1/agents",
        "headers": [],
        "query_string": b"",
        "app": SimpleNamespace(state=SimpleNamespace(sessions=_Starved())),
    }
    sent: list[Message] = []

    async def receive() -> Message:
        return {"type": "http.request", "body": b""}

    async def send(message: Message) -> None:
        sent.append(message)

    await middleware(scope, receive, send)
    start = next(message for message in sent if message["type"] == "http.response.start")
    assert start["status"] == 503
    body = b"".join(bytes(message.get("body", b"")) for message in sent if message["type"] == "http.response.body")
    assert "no connection came free" in body.decode()
