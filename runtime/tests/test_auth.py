"""The actor is resolved before any endpoint, and a database that does not answer there is still a 503."""

from typing import Any

from fastapi.responses import JSONResponse
from sqlalchemy.ext.asyncio import AsyncSession
from starlette.requests import HTTPConnection, Request
from starlette.types import Message, Receive, Scope, Send

from runtime.actor import Actor
from runtime.auth import ActorMiddleware
from runtime.config import load_settings
from runtime.exceptions import PinecallError
from runtime.postgres import create_engine, session_maker
from tests.conftest import needs_the_database


# A session takes its connection at its first statement: the key's lookup, here.
async def _asks_the_database(_request: HTTPConnection, session: AsyncSession) -> Actor | None:
    await session.connection()
    raise AssertionError("a connection came free: the pool was not starved")


async def _refusal(_request: Request, error: Exception) -> JSONResponse:
    status = error.status if isinstance(error, PinecallError) else 500
    return JSONResponse({"detail": str(error)}, status_code=status)


async def _not_reached(_scope: Scope, _receive: Receive, _send: Send) -> None:
    raise AssertionError("the endpoint was reached with no actor")


# The app's exception handlers never see a middleware's error: before 2026-10-21 this was
# uvicorn's 500 and a traceback in the journal. The pool is a real one of one connection, held: the
# middleware waits its turn for the pool's own two seconds and is told there is none.
@needs_the_database
async def test_a_pool_with_no_connection_free_is_answered_503_before_any_endpoint() -> None:
    engine = create_engine(load_settings(), pool_size=1)
    starved = session_maker(engine)
    middleware = ActorMiddleware(
        _not_reached, resolve=_asks_the_database, refuse=_refusal, find_sessions=lambda _request: starved
    )
    scope: dict[str, Any] = {"type": "http", "method": "GET", "path": "/v1/agents", "headers": [], "query_string": b""}
    sent: list[Message] = []

    async def receive() -> Message:
        return {"type": "http.request", "body": b""}

    async def send(message: Message) -> None:
        sent.append(message)

    async with engine.connect():
        await middleware(scope, receive, send)
    await engine.dispose()
    start = next(message for message in sent if message["type"] == "http.response.start")
    assert start["status"] == 503
    body = b"".join(bytes(message.get("body", b"")) for message in sent if message["type"] == "http.response.body")
    assert "no connection came free" in body.decode()
