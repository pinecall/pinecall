"""The gateway as a Studio agent's app: an in-memory app socket per org and env, answering from the definition."""

import asyncio
import json
import logging
import time
from collections.abc import Coroutine
from dataclasses import dataclass, field
from typing import Any, cast

import httpx

from pinecall_runtime.calls import service as calls
from pinecall_runtime.enums import Env, KeyScope
from pinecall_runtime.exceptions import ServiceUnavailable
from pinecall_runtime.hosting import service as hosting
from pinecall_runtime.kit.auth import Actor
from pinecall_runtime.kit.dns import resolve
from pinecall_runtime.kit.text import JsonObject
from pinecall_runtime.postgres import box_task, box_wide
from pinecall_runtime.redis import Signal
from pinecall_runtime.studio.schemas import Definition
from pinecall_runtime.studio.service import definition as defined
from pinecall_runtime.studio.service import fetch
from pinecall_runtime.wire.commands import AgentRegister
from pinecall_runtime.wire.events import CallAttached, CallStarted, ToolCall
from pinecall_runtime.wire.parts import ToolResult

logger = logging.getLogger(__name__)

# Said on the signal as `org|env` whenever an org's Studio agents changed: every gateway holds them again.
CHANNEL = "studio"
# What the socket says of itself: the console lists it as the process holding the agent.
SDK = "studio"
HOST = "pinecall-studio"
KEY_PREFIX = "studio:"
LISTEN_RETRY_S = 1.0
GONE = "removed from Studio"
NO_SUCH_TOOL = "{name}: this agent has no such tool"
NOT_SERVED = "{name}: this call is no longer served"


def is_studio(actor: Actor) -> bool:
    """Whether the socket's actor is the gateway's own Studio socket, not a key anybody holds."""
    return actor.key_id.startswith(KEY_PREFIX)


def changed(signal: Signal, org: str, env: Env) -> None:
    """Tell every gateway the org's Studio agents in the env changed."""
    signal.publish(CHANNEL, f"{org}|{env.value}".encode())


@dataclass
class Run:
    """One call a Studio agent answers: its definition as it opened, the call's values, what it collected."""

    agent: str
    definition: Definition
    values: dict[str, Any]
    collected: dict[str, Any] = field(default_factory=dict[str, Any])
    transcript: list[dict[str, str]] = field(default_factory=list[dict[str, str]])
    sent: dict[str, str] = field(default_factory=dict[str, str])


class StudioSocket:
    """One org's Studio agents in one env, held on an app socket whose frames never leave the process."""

    def __init__(self, holder: "Holder", org: str, env: Env) -> None:
        """A socket that holds nothing yet."""
        self.holder = holder
        self.org = org
        self.env = env
        actor = Actor(
            key_id=f"{KEY_PREFIX}{org}:{env.value}", org=org, env=env, scopes=frozenset({KeyScope.app}), label=SDK
        )
        self.socket = calls.AppSocket(holder.serving, holder.threads, actor, self._down, self._closed, HOST)
        self.agents: dict[str, Definition] = {}
        self.runs: dict[str, Run] = {}
        self.queue: asyncio.Queue[JsonObject] = asyncio.Queue()
        self.tasks: set[asyncio.Task[None]] = set()
        self.reader: asyncio.Task[None] | None = None
        self.inbox: asyncio.Task[None] | None = None

    async def open(self) -> None:
        """Say the socket is open and start reading what the gateway sends it."""
        self.socket.connect()
        self.inbox = box_task(self.socket.listen())
        self.reader = box_task(self._read())

    async def hold(self, slug: str, definition: Definition) -> None:
        """Register the agent, or declare it again with this definition: new calls run on it."""
        first = slug not in self.agents
        self.agents[slug] = definition
        if first:
            register = AgentRegister(routes=[], sdk=SDK, host=HOST)
            await self._command("agent.register", slug, None, register.model_dump(mode="json", exclude_none=True))
        # What was set alone: a default sent (`record`) would be a setting the agent fixes for the console.
        config = defined.declaration(definition).model_dump(mode="json", exclude_unset=True, exclude_none=True)
        await self._command("agent.configure", slug, None, {"config": config})

    async def let_go(self, slug: str) -> None:
        """Stop holding the agent: its calls go where a new one would, or wait parked."""
        self.agents.pop(slug, None)
        await self.socket.kill(slug, GONE)

    async def close(self) -> None:
        """Drain every agent, and close: the calls go to another gateway's socket."""
        for slug in list(self.agents):
            await self._command("agent.drain", slug, None, {})
        await self.socket.gone()
        for task in (self.reader, self.inbox, *self.tasks):
            if task is not None:
                task.cancel()
        await asyncio.gather(*(task for task in (self.reader, self.inbox, *self.tasks) if task), return_exceptions=True)

    async def _command(self, kind: str, agent: str, call: str | None, data: JsonObject) -> None:
        await self.socket.take({"type": kind, "agent": agent, "call": call, "data": data})

    # The pump awaits this: it only queues, so a slow tool never holds the call's other entries.
    async def _down(self, frame: JsonObject) -> None:
        self.queue.put_nowait(frame)

    async def _closed(self, why: str) -> None:
        logger.info("studio socket of %s in %s closed: %s", self.org, self.env.value, why)

    async def _read(self) -> None:
        while True:
            frame = await self.queue.get()
            try:
                await self._entry(frame)
            except Exception:
                logger.exception("studio: an entry of %s was not answered", frame.get("call"))

    async def _entry(self, frame: JsonObject) -> None:
        kind, call, agent = frame.get("type"), frame.get("call"), str(frame.get("agent") or "")
        data: Any = frame.get("data") or {}
        if kind == "error":
            logger.warning("studio %s/%s: %s", self.org, agent, data.get("message"))
            return
        if not isinstance(call, str):
            return
        run = self.runs.get(call)
        match kind:
            case "call.started":
                await self._started(agent, call, CallStarted.model_validate(data), None)
            case "call.attached":
                attached = CallAttached.model_validate(data)
                await self._started(agent, call, attached.started, attached.state)
            case "tool.call":
                self._spawn(self._tool(agent, call, ToolCall.model_validate(data)))
            case "turn.user" | "turn.agent" if run is not None:
                run.transcript.append({"role": kind.removeprefix("turn."), "text": str(data.get("text", ""))})
            case "call.ended" if run is not None:
                self.runs.pop(call, None)
                self._spawn(self._ended(call, run, data))
            case _:
                return

    def _spawn(self, work: Coroutine[Any, Any, None]) -> None:
        task = box_task(work)
        self.tasks.add(task)
        task.add_done_callback(self.tasks.discard)

    # What an SDK sends at a call's start: the state, every block of the prompt, the tools visible.
    async def _started(self, agent: str, call: str, started: CallStarted, restored: dict[str, Any] | None) -> None:
        definition = self.agents.get(agent)
        if definition is None:
            return
        run = Run(agent=agent, definition=definition, values=_values(started))
        fields = {item.name for item in definition.collect.fields} if definition.collect else set[str]()
        opened = restored if restored is not None else (started.state or {})
        run.collected = {name: value for name, value in opened.items() if name in fields}
        self.runs[call] = run
        if definition.collect is not None:
            await self._command("state.set", agent, call, {"state": run.collected})
        await self._prompt(run, call, "identity", defined.identity(definition, run.values))
        await self._prompt(run, call, "tools", defined.tools_block(definition))
        await self._prompt(run, call, "view", defined.view(definition, run.collected))
        specs = [spec.model_dump(mode="json", exclude_none=True) for spec in defined.tool_specs(definition)]
        await self._command("tools.set", agent, call, {"tools": specs})

    async def _prompt(self, run: Run, call: str, name: str, text: str) -> None:
        if run.sent.get(name, "") == text:
            return
        run.sent[name] = text
        await self._command("prompt.set", run.agent, call, {"name": name, "text": text})

    async def _tool(self, agent: str, call: str, called: ToolCall) -> None:
        started = time.monotonic()
        run = self.runs.get(call)
        output: Any = None
        error: str | None = None
        if run is None:
            error = NOT_SERVED.format(name=called.name)
        elif called.name == defined.COLLECT and run.definition.collect is not None:
            output = await self._collect(run, call, called.arguments)
        else:
            tool = next((item for item in run.definition.tools if item.name == called.name), None)
            if tool is None:
                error = NO_SUCH_TOOL.format(name=called.name)
            else:
                values = {**run.values, "secrets": await self.holder.secrets(self.org, self.env)}
                request = fetch.request_of(tool, called.arguments, values)
                answer = await fetch.send(
                    self.holder.http, request, name=tool.name, timeout_s=tool.timeout_s, resolver=self.holder.resolver
                )
                output = answer.body
                if answer.error is not None:
                    error = answer.error if answer.body is None else f"{answer.error}: {_short(answer.body)}"
        result = ToolResult(
            call_id=called.call_id,
            name=called.name,
            output=output,
            error=error,
            duration_s=round(time.monotonic() - started, 3),
        )
        await self._command("tool.result", agent, call, result.model_dump(mode="json", exclude_none=True))

    async def _collect(self, run: Run, call: str, arguments: dict[str, Any]) -> JsonObject:
        collect = run.definition.collect
        assert collect is not None
        names = {item.name for item in collect.fields}
        got = {name: value for name, value in arguments.items() if name in names and value not in (None, "")}
        run.collected.update(got)
        if got:
            await self._command("state.set", run.agent, call, {"state": run.collected, "changed": sorted(got)})
        await self._prompt(run, call, "view", defined.view(run.definition, run.collected))
        missing = [item.name for item in collect.fields if item.name not in run.collected]
        return {
            "saved": sorted(got),
            "missing": missing,
            "complete": defined.is_complete(run.definition, run.collected),
        }

    async def _ended(self, call: str, run: Run, ended: Any) -> None:
        collect = run.definition.collect
        if collect is None or collect.send_to is None:
            return
        body: dict[str, Any] = {
            "agent": run.agent,
            "call": call,
            "env": self.env.value,
            "from": run.values["call"].get("from"),
            "to": run.values["call"].get("to"),
            "channel": run.values["call"].get("channel"),
            "fields": run.collected,
            "complete": defined.is_complete(run.definition, run.collected),
            "reason": cast("dict[str, Any]", ended).get("reason") if isinstance(ended, dict) else None,
            "transcript": run.transcript,
        }
        values = {**run.values, "secrets": await self.holder.secrets(self.org, self.env)}
        request = fetch.post_of(collect.send_to, collect.headers, body, values)
        answer = await fetch.send(
            self.holder.http, request, name="data collection", timeout_s=10.0, resolver=self.holder.resolver
        )
        if answer.error is not None:
            logger.warning(
                "studio %s/%s: the results of %s were not taken: %s", self.org, run.agent, call, answer.error
            )


class Holder:
    """Every Studio agent of the box, held by this gateway: a socket per org and env that has one."""

    def __init__(
        self,
        serving: calls.Serving,
        threads: calls.Threads,
        http: httpx.AsyncClient,
        resolver: fetch.Resolve = resolve,
    ) -> None:
        """Holding nothing until started."""
        self.serving = serving
        self.threads = threads
        self.http = http
        self.resolver = resolver
        self.sockets: dict[tuple[str, Env], StudioSocket] = {}
        self.listening: asyncio.Task[None] | None = None
        self.lock = asyncio.Lock()

    async def start(self) -> None:
        """Hold every Studio agent of both envs, then follow what changes."""
        self.listening = box_task(self._listen())
        try:
            for env in Env:
                async with self.serving.handles.sessions() as session:
                    with box_wide():
                        held = await hosting.studio_in(session, env)
                for org in sorted({item.org for item in held}):
                    await self.refresh(org, env)
        except Exception:
            # A box whose database lags its code (a migration still to run) starts without Studio.
            logger.exception("studio: the agents were not held at start")

    async def close(self) -> None:
        """Stop following, and let every socket go."""
        if self.listening is not None:
            self.listening.cancel()
            await asyncio.gather(self.listening, return_exceptions=True)
        for socket in list(self.sockets.values()):
            await socket.close()
        self.sockets.clear()

    async def refresh(self, org: str, env: Env) -> None:
        """Hold the org's Studio agents in the env as their newest releases say."""
        async with self.lock:
            async with self.serving.handles.sessions() as session:
                with box_wide():
                    held = await hosting.studio_in(session, env, org)
            wanted = {item.name: defined.parsed(item.definition) for item in held}
            socket = self.sockets.get((org, env))
            if not wanted:
                if socket is not None:
                    await socket.close()
                    del self.sockets[(org, env)]
                return
            if socket is None:
                socket = StudioSocket(self, org, env)
                await socket.open()
                self.sockets[(org, env)] = socket
            for slug in set(socket.agents) - set(wanted):
                await socket.let_go(slug)
            for slug, definition in wanted.items():
                if socket.agents.get(slug) != definition:
                    await socket.hold(slug, definition)

    async def secrets(self, org: str, env: Env) -> dict[str, str]:
        """The org's secrets in the env, opened: what a tool's headers may name."""
        async with self.serving.handles.sessions() as session:
            with box_wide():
                return await hosting.environment_of(session, self.serving.handles.vault, org, env)

    async def _listen(self) -> None:
        while True:
            try:
                listener = await self.serving.handles.signal.subscribe(CHANNEL)
            except ServiceUnavailable:
                await asyncio.sleep(LISTEN_RETRY_S)
                continue
            try:
                async for data in listener:
                    org, _, env = data.decode().partition("|")
                    try:
                        await self.refresh(org, Env(env))
                    except Exception:
                        logger.exception("studio: the agents of %s in %s were not held again", org, env)
            finally:
                listener.close()
            await asyncio.sleep(LISTEN_RETRY_S)


def _values(started: CallStarted) -> dict[str, Any]:
    caller = started.caller.model_dump(mode="json", exclude_none=True) if started.caller is not None else {}
    return {
        "call": {
            "from": started.from_,
            "to": started.to,
            "channel": started.channel.value,
            "direction": started.direction.value,
            "medium": started.medium or ("text" if started.channel.value == "whatsapp" else "voice"),
            "today": started.today,
        },
        "caller": caller,
        "metadata": started.state or {},
    }


def _short(body: Any) -> str:
    text = body if isinstance(body, str) else json.dumps(body, ensure_ascii=False)
    return text[:2000]
