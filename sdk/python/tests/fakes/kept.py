"""A gateway's flows doors in memory, served on a free port: the runs and events of one app."""

import copy
import json
import socket as sockets
from typing import cast

from aiohttp import web

from pinecall._app_work import AppDoor

WAITS = {"sleep": "sleeping", "wait": "waiting", "call": "calling"}
APP = "brightside"


class KeptApp:
    """The app's runs and events, and what was asked of the gateway, in order."""

    def __init__(self) -> None:
        """Nothing kept yet; `refuses` answers a call step at once, `down` fails every step."""
        self.runs: dict[str, dict[str, object]] = {}
        self.keys: dict[str, str] = {}
        self.events: list[dict[str, object]] = []
        self.heard: list[int] = []
        self.asked: list[str] = []
        self.refuses: object = None
        self.staged = 202
        self.down: str | None = None
        self._runner: web.AppRunner | None = None
        self.door = AppDoor("", "pk_test", None, APP)

    async def start(self) -> AppDoor:
        """Serve on a free port; the answer is the door to hand the app's loop."""
        app = web.Application()
        app.router.add_route("*", "/v1/apps/" + APP + "/{rest:.*}", self._app)
        app.router.add_post("/v1/calls/{call}/stages", self._stages)
        self._runner = web.AppRunner(app)
        await self._runner.setup()
        bound = sockets.socket()
        bound.bind(("127.0.0.1", 0))
        await web.SockSite(self._runner, bound).start()
        port = cast("tuple[str, int]", bound.getsockname())[1]
        self.door = AppDoor(f"http://127.0.0.1:{port}", "pk_test", None, APP)
        return self.door

    async def close(self) -> None:
        """Stop serving."""
        if self._runner is not None:
            await self._runner.cleanup()

    def wake(self, run: str, result: object) -> None:
        """The step the run waits on comes to `result`, and the run is ready again."""
        kept = self.runs[run]
        steps = cast("list[dict[str, object]]", kept["steps"])
        step = next(one for one in steps if not one["over"])
        step["over"], step["result"], kept["status"] = True, result, "ready"

    def send(self, name: str, data: dict[str, object]) -> int:
        """Keep an event for the app, as its own backend sends one."""
        event: dict[str, object] = {"id": len(self.events) + 1, "name": name, "data": data}
        self.events.append(event)
        return cast("int", event["id"])

    async def _stages(self, request: web.Request) -> web.Response:
        self.asked.append(f"POST {request.path} {await request.text()}")
        return web.json_response({"call": request.match_info["call"]}, status=self.staged)

    async def _app(self, request: web.Request) -> web.Response:  # noqa: C901, PLR0911 - one door per branch, as the gateway's
        path = "/" + request.match_info["rest"]
        body: dict[str, object] = json.loads(await request.text() or "{}")
        self.asked.append(f"{request.method} {path}")
        parts = [one for one in path.split("/") if one]
        if path == "/work":
            owed = [one for one in self.events if one["id"] not in self.heard]
            ready = [copy.deepcopy(run) for run in self.runs.values() if run["status"] == "ready"]
            return web.json_response({"events": owed, "runs": ready})
        if parts[:1] == ["events"] and parts[2:3] == ["heard"]:
            self.heard.append(int(parts[1]))
            return web.Response(status=204)
        if path == "/runs" and request.method == "POST":
            key = f"{body['flow']}:{body['key']}"
            if key in self.keys:
                return web.json_response(self.runs[self.keys[key]], status=201)
            run: dict[str, object] = {"id": f"run_{len(self.runs) + 1}", "flow": body["flow"]}
            run |= {"input": body["input"], "status": "ready", "steps": []}
            self.runs[str(run["id"])], self.keys[key] = run, str(run["id"])
            return web.json_response(run, status=201)
        if path == "/runs":
            flow, status = request.query.get("flow"), request.query.get("status")
            kept = self.runs.values()
            found: list[dict[str, object]] = [
                {**run, "steps": []}
                for run in kept
                if run["flow"] == flow and run["status"] == status
            ]
            return web.json_response({"runs": found})
        held = self.runs.get(parts[1] if len(parts) > 1 else "")
        if held is None:
            return web.json_response({"detail": "no such run"}, status=404)
        if len(parts) == 2:
            return web.json_response(copy.deepcopy(held))
        if parts[2] == "end":
            held["status"] = body["status"]
        if parts[2] == "cancel":
            held["status"] = "cancelled"
        if parts[2] == "steps":
            if self.down is not None:
                return web.json_response({"detail": self.down}, status=503)
            self._step(held, body)
        return web.json_response({**held, "steps": []})

    def _step(self, run: dict[str, object], body: dict[str, object]) -> None:
        kind = str(body["kind"])
        step: dict[str, object] = {"seq": body["seq"], "kind": kind, "over": False}
        step |= {"asked": body.get("asked") or {}, "result": None}
        if kind in ("run", "emit"):
            step["over"], step["result"] = True, body.get("result")
        elif kind == "call" and self.refuses is not None:
            step["over"], step["result"] = True, self.refuses
        else:
            run["status"] = WAITS[kind]
        if kind == "emit":
            asked = cast("dict[str, object]", step["asked"])
            self.send(str(asked["name"]), cast("dict[str, object]", asked["data"]))
        cast("list[dict[str, object]]", run["steps"]).append(step)
