"""A gateway that is not there: a real socket and a lookup door on 127.0.0.1, for the tests."""

import asyncio
import itertools
import json
import socket as sockets
import time
from collections.abc import Callable, Mapping
from typing import cast

from aiohttp import WSCloseCode, WSMsgType, web

KEY = "pk_test_fake"


class FakeGateway:
    """Answers register, configure, ping and drain as the gateway does; records every command."""

    def __init__(
        self,
        *,
        taken: frozenset[str] = frozenset(),
        refuses_with: int | None = None,
        holds_drain: bool = False,
    ) -> None:
        """A gateway refusing the slugs `taken`, closing with `refuses_with`, holding a drain."""
        self.taken = taken
        self.refuses_with = refuses_with
        self.holds_drain = holds_drain
        self.received: list[dict[str, object]] = []
        self.searched: list[dict[str, object]] = []
        self.chunks: list[dict[str, object]] = []
        self.headers: list[dict[str, str]] = []
        self.logs: dict[str, list[dict[str, object]]] = {}
        self.resumed_from: list[str | None] = []
        self._sockets: list[web.WebSocketResponse] = []
        self._holders: dict[str, web.WebSocketResponse] = {}
        self._seq = itertools.count(1)
        self._apps = itertools.count(1)
        self._runner: web.AppRunner | None = None
        self.url = ""

    async def start(self) -> str:
        """Serve on a free port; the answer is the base URL to hand a client."""
        app = web.Application()
        app.router.add_get("/v1/apps", self._apps_socket)
        app.router.add_post("/v1/calls/{call}/lookup", self._lookup)
        app.router.add_get("/v1/calls/{call}/events", self._log)
        self._runner = web.AppRunner(app)
        await self._runner.setup()
        bound = sockets.socket()
        bound.bind(("127.0.0.1", 0))
        await web.SockSite(self._runner, bound).start()
        port = cast("tuple[str, int]", bound.getsockname())[1]
        self.url = f"http://127.0.0.1:{port}"
        return self.url

    async def close(self) -> None:
        """Stop serving."""
        for socket in list(self._sockets):
            await socket.close()
        if self._runner is not None:
            await self._runner.cleanup()

    def commands_of(self, type_: str) -> list[dict[str, object]]:
        """Every command of one type received so far."""
        return [one for one in self.received if one["type"] == type_]

    def data_of(self, type_: str) -> list[dict[str, object]]:
        """The data of every command of one type received so far."""
        return [cast("dict[str, object]", one["data"]) for one in self.commands_of(type_)]

    async def emit(
        self, agent: str, call: str | None, type_: str, data: Mapping[str, object]
    ) -> None:
        """Write an entry to the socket holding `agent`."""
        await self._holders[agent].send_str(self._entry(agent, call, type_, data))

    async def cut(self) -> None:
        """Drop every socket as a gateway that went away does."""
        for socket in list(self._sockets):
            await socket.close(code=WSCloseCode.GOING_AWAY)

    async def stop(self, why: str) -> None:
        """A person stopped the app: the `stopped` error, for no agent."""
        for socket in list(self._sockets):
            await socket.send_str(
                self._entry(
                    "", None, "error", {"code": "stopped", "message": why, "recoverable": False}
                )
            )

    async def until(self, holds: Callable[[], bool], within_s: float = 5.0) -> None:
        """Wait until `holds()` is true."""
        deadline = time.monotonic() + within_s
        while not holds():
            if time.monotonic() > deadline:
                raise TimeoutError("the fake gateway never saw it")
            await asyncio.sleep(0.01)

    def write(self, call: str, type_: str, data: Mapping[str, object]) -> None:
        """Append an entry to a call's log, as the store keeps it."""
        self.logs.setdefault(call, []).append(json.loads(self._entry("clinica", call, type_, data)))

    def _entry(self, agent: str, call: str | None, type_: str, data: Mapping[str, object]) -> str:
        entry = {"seq": next(self._seq), "ts": time.time(), "call": call, "agent": agent}
        return json.dumps(entry | {"type": type_, "ephemeral": False, "data": data})

    async def _apps_socket(self, request: web.Request) -> web.StreamResponse:
        self.headers.append(dict(request.headers))
        if request.headers.get("authorization") != f"Bearer {KEY}":
            return web.Response(status=403, text="that key opens nothing here")
        socket = web.WebSocketResponse()
        await socket.prepare(request)
        if self.refuses_with is not None:
            await socket.close(code=self.refuses_with, message=b"this key may not hold an agent")
            return socket
        self._sockets.append(socket)
        async for message in socket:
            if message.type is WSMsgType.TEXT:
                await self._answer(socket, json.loads(message.data))
        self._sockets.remove(socket)
        return socket

    async def _answer(self, socket: web.WebSocketResponse, command: dict[str, object]) -> None:
        self.received.append(command)
        agent, type_, data = str(command["agent"]), command["type"], command["data"]
        if type_ == "agent.register":
            if agent in self.taken:
                refused = {"code": "refused", "message": f"{agent} is taken", "id": command["id"]}
                await socket.send_str(
                    self._entry(agent, None, "error", refused | {"recoverable": False})
                )
                return
            self._holders[agent] = socket
            registered: dict[str, object] = {
                "routes": [],
                "app": f"app_{next(self._apps)}",
                "sdk": cast("dict[str, object]", data).get("sdk"),
            }
            await socket.send_str(self._entry(agent, None, "agent.registered", registered))
        elif type_ == "agent.configure":
            config = cast("dict[str, object]", cast("dict[str, object]", data)["config"])
            await socket.send_str(
                self._entry(agent, None, "agent.configured", {"changed": sorted(config)})
            )
        elif type_ == "ping":
            await socket.send_str(self._entry(agent, None, "pong", {"ts": time.time()}))
        elif type_ == "agent.drain" and not self.holds_drain:
            drained = {"app": "app_1", "env": "sandbox", "handed": 1, "parked": 0}
            await socket.send_str(self._entry(agent, None, "agent.draining", drained))

    async def _lookup(self, request: web.Request) -> web.Response:
        if request.headers.get("authorization") != f"Bearer {KEY}":
            return web.json_response({"detail": "that key opens nothing here"}, status=403)
        self.searched.append(await request.json() | {"call": request.match_info["call"]})
        return web.json_response({"output": {"chunks": self.chunks}})

    # A page as JSON, or the entries after the cursor as server-sent events and then a drop.
    async def _log(self, request: web.Request) -> web.StreamResponse:
        if request.headers.get("authorization") != f"Bearer {KEY}":
            return web.Response(status=403, text="that key opens nothing here")
        after = int(request.query.get("after", "0"))
        entries = [
            one
            for one in self.logs.get(request.match_info["call"], [])
            if cast("int", one["seq"]) > after
        ]
        if request.headers.get("accept") != "text/event-stream":
            last = cast("int", entries[-1]["seq"]) if entries else after
            return web.json_response({"entries": entries, "live": True, "next": last})
        self.resumed_from.append(request.headers.get("last-event-id"))
        answer = web.StreamResponse(headers={"content-type": "text/event-stream"})
        await answer.prepare(request)
        await answer.write(b": keep-alive\n\n")
        for one in entries:
            await answer.write(f"id: {one['seq']}\ndata: {json.dumps(one)}\n\n".encode())
        return answer
