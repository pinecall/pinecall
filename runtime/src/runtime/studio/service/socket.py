"""One org's Studio agents in one env, held on an app socket whose frames never leave the process."""

import asyncio
import contextlib
import logging
import time
from collections.abc import Coroutine
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from runtime.actor import Actor
from runtime.agents import service as agents
from runtime.calls import service as calls
from runtime.enums import Env, KeyScope
from runtime.hosting import service as hosting
from runtime.kit.crypto import Vault
from runtime.kit.text import JsonObject
from runtime.live import service as live
from runtime.scoping import box_task
from runtime.session import service as session
from runtime.studio.service import collect as collecting
from runtime.studio.service import declaring, fetch, values
from runtime.studio.service.run import Run
from runtime.wire.base import Command, Entry
from runtime.wire.commands import AgentConfigure, AgentDrain, AgentRegister
from runtime.wire.events import CallAttached, CallEnded, CallStarted, ErrorEvent, ToolCall
from runtime.wire.studio import Definition

logger = logging.getLogger(__name__)

# What the socket says of itself: the console lists it as the process holding the agent.
SDK = agents.BUILT_IN_STUDIO
HOST = "pinecall-studio"
# The socket's key is nobody's: the gateway's own, told apart by its prefix (`agents.is_studio_key`).
KEY = "studio:{org}:{env}"
GONE = "removed from Studio"
# The commands whose refusal means the agent is not held as the definition says.
HOLDING = frozenset({"agent.register", "agent.configure"})


class StudioSocket:
    """The gateway as the app of one org's Studio agents in one env: it answers each call from its definition."""

    def __init__(
        self,
        sockets: live.AppSockets,
        sessions: async_sessionmaker[AsyncSession],
        vault: Vault,
        fetcher: fetch.Fetcher,
        org: str,
        env: Env,
    ) -> None:
        """A socket that holds nothing yet."""
        self.org = org
        self.env = env
        self._sessions = sessions
        self._vault = vault
        self._fetcher = fetcher
        key = KEY.format(org=org, env=env.value)
        actor = Actor(key_id=key, org=org, env=env, scopes=frozenset({KeyScope.app}), label=SDK)
        self._socket = sockets.make(actor, self._take_down, self._say_closed, HOST)
        self._life = contextlib.AsyncExitStack()
        # The agents held as their definitions say, and the ones the socket registered at all.
        self.agents: dict[str, Definition] = {}
        self._registered: set[str] = set()
        # Why the socket refused to hold an agent, by slug, until it is asked again.
        self._refused: dict[str, str] = {}
        self._runs: dict[str, Run] = {}
        self._frames: asyncio.Queue[JsonObject] = asyncio.Queue()
        self._tasks: set[asyncio.Task[None]] = set()
        self._reader: asyncio.Task[None] | None = None
        self._secrets: dict[str, str] | None = None
        self._closed = False

    async def open(self) -> None:
        """Say the socket is open and start reading what the gateway sends it."""
        await self._life.enter_async_context(self._socket.open())
        self._reader = box_task(self._read())

    # The definition is noted once the socket took it: a register or a configure it refused (the org's
    # quota of agents, a vendor nobody keyed) is said and asked again at the next look, where it used
    # to be noted first, logged as a warning, and never sent again while the console said "saved".
    async def hold(self, slug: str, definition: Definition) -> bool:
        """Register the agent, or declare it again with this definition: new calls run on it; False when refused."""
        self._refused.pop(slug, None)
        if slug not in self._registered:
            await self._send(self._command("agent.register", slug, AgentRegister(routes=[], sdk=SDK, host=HOST)))
            if slug in self._refused:
                return False
            self._registered.add(slug)
        # What was set alone: a default sent (`record`) would be a setting the agent fixes for the console.
        config = declaring.declare(definition).model_dump(mode="json", exclude_unset=True, exclude_none=True)
        await self._send(Command(type="agent.configure", agent=slug, call=None, data={"config": config}))
        if slug in self._refused:
            return False
        self.agents[slug] = definition
        if self.env is Env.sandbox:
            await self._rehear(slug, definition)
        return True

    async def let_go(self, slug: str) -> None:
        """Stop holding the agent: its calls go where a new one would, or wait parked."""
        self.agents.pop(slug, None)
        self._registered.discard(slug)
        await self._socket.kill(slug, GONE)

    def forget_secrets(self) -> None:
        """The org's secrets may have changed: the next tool reads them again."""
        self._secrets = None

    async def close(self) -> None:
        """Drain every agent, and close: the calls go to another gateway's socket."""
        for slug in list(self._registered):
            await self._send(self._command("agent.drain", slug, AgentDrain()))
        self._closed = True
        await self._life.aclose()
        tasks = [task for task in (self._reader, *self._tasks) if task is not None]
        for task in tasks:
            task.cancel()
        await asyncio.gather(*tasks, return_exceptions=True)

    # ── what the gateway sends down ──

    # The pump awaits this: it only queues, so a slow tool never holds the call's other entries. A
    # refusal of a register or a configure is read at once, while `hold` still waits on the command.
    async def _take_down(self, frame: JsonObject) -> None:
        if frame.get("type") == "error":
            refused = ErrorEvent.parse(frame.get("data"), "an error down a Studio socket")
            if refused.command in HOLDING:
                self._refused[str(frame.get("agent") or "")] = refused.message
        self._frames.put_nowait(frame)

    async def _say_closed(self, why: str) -> None:
        logger.info("studio socket of %s in %s closed: %s", self.org, self.env.value, why)

    async def _read(self) -> None:
        while not self._closed:
            frame = await self._frames.get()
            try:
                await self._hear(Entry.parse(frame, "an entry down a Studio socket"))
            except Exception:
                logger.exception("studio: an entry of %s was not answered", frame.get("call"))

    async def _hear(self, entry: Entry) -> None:
        if entry.type == "error":
            refused = ErrorEvent.parse(entry.data, "error")
            logger.warning("studio %s/%s: %s", self.org, entry.agent, refused.message)
            return
        call = entry.call
        if call is None:
            return
        run = self._runs.get(call)
        match entry.type:
            case "call.started":
                await self._start(entry.agent, call, CallStarted.parse(entry.data, entry.type), None)
            case "call.attached":
                attached = CallAttached.parse(entry.data, entry.type)
                await self._start(entry.agent, call, attached.started, attached.state)
            case "tool.call" if run is not None:
                called = ToolCall.parse(entry.data, entry.type)
                # The session writes the hang-up's call and its result itself: a second result is a lie.
                if called.name != session.END_CALL:
                    self._spawn(self._run_tool(run, called))
            case "call.ended" if run is not None:
                self._runs.pop(call, None)
                self._spawn(self._end(run, CallEnded.parse(entry.data, entry.type)))
            case _:
                return

    # ── a call ──

    async def _start(self, agent: str, call: str, started: CallStarted, handed: dict[str, Any] | None) -> None:
        definition = self.agents.get(agent)
        if definition is None:
            return
        run = Run(agent=agent, call=call, definition=definition, values=values.read_values(started))
        self._runs[call] = run
        for command in run.open(handed if handed is not None else started.state):
            await self._send(command)

    # The console's Try it is a call, and a save is meant to be heard by it: in the sandbox the calls
    # already open take the new definition and run their next turn on it. Production's keep the one
    # they opened on, as a deploy says: the next call answers with it.
    async def _rehear(self, slug: str, definition: Definition) -> None:
        for run in list(self._runs.values()):
            if run.agent == slug:
                run.definition = definition
                for command in run.say_definition():
                    await self._send(command)

    async def _run_tool(self, run: Run, called: ToolCall) -> None:
        started = time.monotonic()
        for command in await run.run_tool(self._fetcher, await self._read_secrets(), called, started):
            await self._send(command)

    # The transcript is the call's log, not what this socket saw of it: a call handed over from another
    # process arrived here with its earlier turns already said.
    async def _end(self, run: Run, ended: CallEnded) -> None:
        collect = run.definition.collect
        if collect is None or collect.send_to is None:
            return
        async with self._sessions() as own:
            entries = await calls.read_whole(own, self._vault, run.call)
        said = [
            {"role": entry.type.removeprefix("turn."), "text": str(entry.data.get("text", ""))}
            for entry in entries
            if entry.type in ("turn.user", "turn.agent")
        ]
        body = collecting.results(
            collect,
            run.collected,
            agent=run.agent,
            call=run.call,
            env=self.env.value,
            values=run.values,
            reason=ended.reason,
            transcript=said,
        )
        filled = {**run.values, "secrets": await self._read_secrets()}
        request = fetch.fill_post(collect.send_to, collect.headers, body, filled)
        answered = await fetch.send(
            self._fetcher, request, name="data collection", timeout_s=collecting.RESULTS_TIMEOUT_S
        )
        if answered.error is not None:
            logger.warning(
                "studio %s/%s: the results of %s were not taken: %s", self.org, run.agent, run.call, answered.error
            )

    # ── private ──

    # Read once and kept until the org's apps or secrets change: a tool called in the middle of a spoken
    # turn does not wait on the database and the vault each time.
    async def _read_secrets(self) -> dict[str, str]:
        if self._secrets is None:
            async with self._sessions() as own:
                self._secrets = await hosting.environment_of(own, self._vault, self.org, self.env)
        return self._secrets

    def _spawn(self, work: Coroutine[Any, Any, None]) -> None:
        task = box_task(work)
        self._tasks.add(task)
        task.add_done_callback(self._tasks.discard)

    async def _send(self, command: Command) -> None:
        await self._socket.take(command.model_dump(mode="json"))

    def _command(self, kind: str, agent: str, body: AgentRegister | AgentDrain | AgentConfigure) -> Command:
        return Command(type=kind, agent=agent, call=None, data=body.model_dump(mode="json", exclude_none=True))
