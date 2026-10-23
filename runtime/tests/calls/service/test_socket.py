"""An app's socket outlives a database that does not answer: the frame is answered as busy, not the socket closed."""

import asyncio
import os
from types import SimpleNamespace
from typing import cast

import pytest
from sqlalchemy import text

from pinecall_runtime.calls.service.live import Live
from pinecall_runtime.calls.service.peers import APP_CHANNEL
from pinecall_runtime.calls.service.serving import Serving
from pinecall_runtime.calls.service.socket import BUSY, AppSocket
from pinecall_runtime.calls.service.threads import Threads
from pinecall_runtime.config import load_settings
from pinecall_runtime.enums import Env, KeyScope
from pinecall_runtime.kit.auth import Actor
from pinecall_runtime.kit.text import JsonObject
from pinecall_runtime.postgres import create_engine, session_maker
from pinecall_runtime.wire.base import Entry
from pinecall_runtime.wire.signal import ForApp
from tests.conftest import needs_the_database, until

pytestmark = needs_the_database

AN_APP = Actor(key_id="k_app", org="org_acme", env=Env.sandbox, scopes=frozenset({KeyScope.app}))
REGISTER: JsonObject = {
    "type": "agent.register",
    "agent": "recepcion",
    "call": None,
    "id": "r1",
    "data": {"routes": []},
}


class _Registry:
    """A registry holding nothing: every frame is answered down the socket alone."""

    holders: dict[object, object] = {}

    def on_socket(self, app: str, env: Env, slug: str) -> None:
        return None

    def slugs_of(self, org: str) -> frozenset[str]:
        return frozenset()


# On 2026-10-21 a pool with no connection free cut an app's socket at the frame it was sending.
# The one connection of this pool is held for the whole frame, as every connection was then.
@pytest.mark.skipif("DATABASE_URL" not in os.environ, reason="the test database")
async def test_a_frame_the_database_did_not_answer_is_refused_as_busy_and_the_socket_stays() -> None:
    engine = create_engine(load_settings(), pool_size=1)
    sessions = session_maker(engine)
    sent: list[JsonObject] = []
    closed: list[str] = []

    async def send(frame: JsonObject) -> None:
        sent.append(frame)

    async def close(why: str) -> None:
        closed.append(why)

    handles = SimpleNamespace(sessions=sessions)
    serving = cast(Serving, SimpleNamespace(handles=handles, live=Live(), registry=_Registry()))
    socket = AppSocket(serving, cast(Threads, None), AN_APP, send, close, None)
    try:
        async with sessions.begin() as held:
            await held.execute(text("select 1"))
            await asyncio.wait_for(socket.take(REGISTER), timeout=10)
    finally:
        await engine.dispose()
    [error] = sent
    assert error["type"] == "error"
    data = cast(JsonObject, error["data"])
    assert data["code"] == BUSY and data["recoverable"] is True
    assert (data["command"], data["id"]) == ("agent.register", "r1")
    assert "no connection came free" in str(data["message"])
    assert closed == []


# What another gateway tells a socket arrives on its inbox; a message that cannot be read, or applied,
# ended the loop that heard it, and the socket was deaf for its whole life (it is said now).
async def test_a_message_of_the_inbox_that_cannot_be_read_does_not_leave_the_socket_deaf() -> None:
    sent: list[JsonObject] = []

    async def send(frame: JsonObject) -> None:
        sent.append(frame)

    async def close(_why: str) -> None:
        return None

    live = Live()
    serving = cast(Serving, SimpleNamespace(live=live, registry=_Registry()))
    socket = AppSocket(serving, cast(Threads, None), AN_APP, send, close, None)
    listening = asyncio.create_task(socket.listen())
    try:
        await asyncio.wait_for(socket.listening.wait(), 5)
        live.signal.publish(APP_CHANNEL.format(app=socket.id), b"this is not a message for a socket")
        told = Entry.unstored("recepcion", "error", {"code": "killed", "message": "x", "recoverable": False})
        live.signal.publish(APP_CHANNEL.format(app=socket.id), ForApp(entry=told).model_dump_json().encode())
        await until(lambda: bool(sent))
        assert sent[0]["type"] == "error"
        assert not listening.done()
    finally:
        listening.cancel()
        await asyncio.gather(listening, return_exceptions=True)
