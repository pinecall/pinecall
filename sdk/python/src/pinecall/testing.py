"""A gateway that is not there, for ring 0: a class held as a call holds it, no network, no key."""

import asyncio
import itertools
import time
from dataclasses import dataclass
from pathlib import Path
from types import TracebackType
from typing import Self, cast

from typing_extensions import override

from pinecall.agent import Agent, LastCall
from pinecall.bridge import Mounted, mount
from pinecall.client import Client, Found
from pinecall.errors import PinecallError, WireError
from pinecall.serve._loading import Served, load_served
from pinecall.wire._names import Channel, Json, JsonObject, Medium
from pinecall.wire.commands import COMMANDS
from pinecall.wire.events import EPHEMERAL_EVENTS
from pinecall.wire.frames import Entry, WireModel

QUIET_ROUNDS = 3
ROUND_S = 0.005


def load(file: str | Path) -> type[Agent]:
    """The class an agent file defines, loaded as `pinecall start` loads it: its folder a package.

    ```python
    ClinicaNorte = load(Path(__file__).parents[2] / "agents" / "clinica-norte" / "agent.py")
    ```

    A folder named `clinica-norte` cannot be imported, and the class imports its own modules
    relatively; this loads it the one way that serves both, its slug the folder's.
    """
    path = Path(file)
    return load_served(Served(path, path.resolve().parent.name))


@dataclass(frozen=True)
class Sent:
    """One command the app sent: its type, its agent and call, its data as the wire carries it."""

    type: str
    agent: str
    call: str | None
    data: JsonObject


class Gateway(Client):
    """Stands in for the gateway: records each command, answers those it would, delivers entries.

    ```python
    with Gateway() as pc:
        pc.mount(ClinicaNorte)
        call = pc.call_started(from_="+34600123456")
        call.tool("find_patient", name="Marta Ruiz", phone="+34600123456")
        assert "Marta Ruiz" in call.prompt
    ```
    """

    def __init__(self) -> None:
        """A gateway with nothing mounted, its own loop, and no network."""
        super().__init__("http://ring-zero.invalid", "pk_ring_zero")
        self.commands: list[Sent] = []
        self.searched: list[tuple[str, str, int | None]] = []
        """Every search asked of it: the call, the query, and `k`."""
        self.errors: list[Exception] = []
        """What failed with nobody waiting for it."""
        self._found: list[Found] = []
        self._mounted: list[Mounted] = []
        self._seq = itertools.count(1)
        self._loop = asyncio.new_event_loop()
        self.on_errors(self.errors.append)

    def __enter__(self) -> Self:
        """The gateway, closed when the block ends."""
        return self

    def __exit__(
        self,
        kind: type[BaseException] | None,
        error: BaseException | None,
        trace: TracebackType | None,
    ) -> None:
        """Cancel what still runs on its loop, and close it."""
        self._loop.run_until_complete(cancelled())
        self._loop.run_until_complete(self._loop.shutdown_default_executor())
        self._loop.close()

    def mount(self, cls: type[Agent], *, last: LastCall | None = None) -> Mounted:
        """Hold a class here and register it, as `pinecall start` does."""

        async def mounted() -> Mounted:
            held = mount(cls, self, last=last)
            await held.agent.open()
            return held

        held = self._loop.run_until_complete(mounted())
        self._mounted.append(held)
        return held

    def finds(self, *chunks: Found) -> Self:
        """The chunks every search answers with."""
        self._found = list(chunks)
        return self

    def call_started(
        self,
        *,
        id_: str | None = None,
        channel: Channel = "web",
        medium: Medium | None = None,
        from_: str = "+34600000000",
        state: JsonObject | None = None,
    ) -> "Fake":
        """Start a call, in the state its opener asked for when given one; its handle."""
        call = id_ or self.numbered("CA")
        started: JsonObject = {
            "channel": channel,
            "direction": "inbound",
            "from": from_,
            "to": "+34910000000",
        }
        started |= {"caller": None, "started_at": time.time()}
        started |= ({} if medium is None else {"medium": medium}) | (
            {} if state is None else {"state": state}
        )
        self.deliver("call.started", started, call=call)
        return Fake(self, call)

    def call_attached(
        self, state: JsonObject, *, id_: str | None = None, claimed: str | None = None
    ) -> "Fake":
        """Hand this process a call mid-conversation, in `state`; its handle."""
        call = id_ or self.numbered("CA")
        started: JsonObject = {"channel": "web", "direction": "inbound", "from": "+34600000000"}
        started |= {"to": "+34910000000", "caller": None, "started_at": time.time()}
        attached: JsonObject = {
            "app": "app_test",
            "started": started,
            "state": state,
            "seq": next(self._seq),
        }
        self.deliver(
            "call.attached", attached | ({} if claimed is None else {"claimed": claimed}), call=call
        )
        return Fake(self, call)

    def deliver(
        self, type_: str, data: JsonObject, *, call: str | None = None, agent: str | None = None
    ) -> None:
        """Deliver an entry to the agent, as the gateway would, and wait until it settles."""
        slug = agent or self._mounted[0].slug
        entry = Entry(
            seq=next(self._seq),
            ts=time.time(),
            call=call,
            agent=slug,
            type=type_,
            ephemeral=type_ in EPHEMERAL_EVENTS,
            data=data,
        )

        async def delivered() -> None:
            self._take(entry)

        self._loop.run_until_complete(delivered())
        self.settle()

    def numbered(self, prefix: str) -> str:
        """A new id, unique on this gateway: `tc_7`."""
        return f"{prefix}_{next(self._seq)}"

    def settle(self, within_s: float = 5.0) -> None:
        """Run the loop until nothing is running and nothing new was sent for a few rounds."""
        deadline, quiet = time.monotonic() + within_s, 0
        while quiet < QUIET_ROUNDS:
            if time.monotonic() > deadline:
                raise PinecallError(f"the agent never settled in {within_s:g}s")
            before = len(self.commands)
            self._loop.run_until_complete(asyncio.sleep(ROUND_S))
            quiet = 0 if len(self.commands) != before or self._busy() else quiet + 1

    def _busy(self) -> bool:
        lives = [live for held in self._mounted for live in held.live.values()]
        return any(held.agent.in_flight for held in self._mounted) or any(
            live.busy or not live.jobs.empty() for live in lives
        )

    # ── what a client does, done here ──

    @override
    async def connect(self) -> None:
        """Register every agent mounted; nothing is dialled."""
        for held in self._mounted:
            await held.agent.open()

    @override
    async def close(self) -> None:
        """Nothing to close."""

    @override
    async def search(self, call: str, query: str, k: int | None = None) -> list[Found]:
        """Record the search, and answer with the chunks it finds."""
        self.searched.append((call, query, k))
        return list(self._found)

    @override
    def send(self, type_: str, agent: str, call: str | None, data: WireModel, id_: str) -> None:
        """Record the command and answer it if the gateway would."""
        if not isinstance(data, COMMANDS[type_]):
            raise WireError(
                f"{type_} carries a {COMMANDS[type_].__name__}, not a {type(data).__name__}"
            )
        self.commands.append(Sent(type_, agent, call, data.written()))
        answer = answers(type_, data.written())
        if answer is not None:
            entry = Entry(
                seq=next(self._seq),
                ts=time.time(),
                call=None,
                agent=agent,
                type=answer[0],
                ephemeral=False,
                data=answer[1],
            )
            self._loop.call_soon(self._take, entry)


async def cancelled() -> None:
    """Cancel every other task on this loop, and wait until each has stopped."""
    running = asyncio.all_tasks() - {asyncio.current_task()}
    for task in running:
        task.cancel()
    await asyncio.gather(*running, return_exceptions=True)


def answers(type_: str, data: JsonObject) -> tuple[str, JsonObject] | None:
    """What the gateway answers a command with, for the three it answers."""
    if type_ == "agent.register":
        return "agent.registered", {"app": "app_test", "routes": []}
    if type_ == "agent.configure":
        names: list[Json] = [*sorted(cast("JsonObject", data["config"]))]
        changed: JsonObject = {"changed": names}
        return "agent.configured", changed
    if type_ == "agent.drain":
        return "agent.draining", {"app": "app_test", "env": "sandbox", "handed": 0, "parked": 0}
    return None


class Fake:
    """One call driven by a test: what it says, and what the app sent for it."""

    def __init__(self, gateway: Gateway, id_: str) -> None:
        """The call `id_` on `gateway`."""
        self.id = id_
        self._gateway = gateway

    def tool(self, name: str, /, **arguments: object) -> JsonObject:
        """Call a tool as the model does; the `tool.result` the app answered with."""
        call_id = self._gateway.numbered("tc")
        self._gateway.deliver(
            "tool.call",
            {"call_id": call_id, "name": name, "arguments": cast("JsonObject", arguments)},
            call=self.id,
        )
        found = self.last("tool.result", call_id=call_id)
        if found is None:
            raise PinecallError(f"{name}: the app never answered the tool call")
        return found

    def fact(
        self,
        name: str,
        data: JsonObject | None = None,
        *,
        source: str = "app",
        identity: str | None = None,
    ) -> None:
        """An outside event, from your backend (`app`) or a browser (`participant`)."""
        fact: JsonObject = {"name": name, "data": data or {}, "source": source}
        self._gateway.deliver(
            "event.received",
            fact | ({} if identity is None else {"identity": identity}),
            call=self.id,
        )

    def said(self, text: str) -> None:
        """The caller's turn."""
        turn: JsonObject = {"speech_id": self._gateway.numbered("sp"), "text": text, "metrics": {}}
        self._gateway.deliver("turn.user", turn, call=self.id)

    def ended(self, reason: str = "caller_hung_up") -> None:
        """The call ends."""
        ended: JsonObject = {
            "reason": reason,
            "ended_by": "caller",
            "ended_at": time.time(),
            "duration_s": 1.0,
        }
        self._gateway.deliver("call.ended", ended, call=self.id)

    @property
    def prompt(self) -> str:
        """The view as it was last sent."""
        return self.block("view")

    def block(self, name: str) -> str:
        """The text last sent for one block of the prompt."""
        sent = self.last("prompt.set", name=name)
        return "" if sent is None else str(sent["text"])

    @property
    def tools(self) -> list[str]:
        """The names of the tools the model sees now."""
        sent = self.last("tools.set")
        listed = cast("list[JsonObject]", [] if sent is None else sent["tools"])
        return [str(one["name"]) for one in listed]

    @property
    def state(self) -> JsonObject:
        """The state as it was last sent."""
        sent = self.last("state.set")
        return {} if sent is None else cast("JsonObject", sent["state"])

    @property
    def commands(self) -> list[Sent]:
        """Every command sent for this call, in order."""
        return [one for one in self._gateway.commands if one.call == self.id]

    def last(self, type_: str, **matching: object) -> JsonObject | None:
        """The data of the last command of this type whose fields match."""
        for one in reversed(self.commands):
            if one.type == type_ and all(
                one.data.get(key) == value for key, value in matching.items()
            ):
                return one.data
        return None
