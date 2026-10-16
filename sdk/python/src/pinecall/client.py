"""`Client`: one socket to the gateway, the agents held on it, leaving, and a search for a call."""

import asyncio
import contextlib
import socket
import sys
import typing
from collections.abc import AsyncIterator, Callable, Sequence
from dataclasses import dataclass

import httpx

from pinecall._agent_socket import ANSWER_WITHIN_S, AgentSocket, Role, Tool
from pinecall._calls import Call
from pinecall._connection import Backoff, Connection, Handlers
from pinecall._endpoints import lookup_url, signed
from pinecall._listeners import AnyListener, Listener, Listeners
from pinecall._version import __version__
from pinecall.errors import NotConnected, PinecallError, Refused, WireError
from pinecall.observe import Observation, Page, Reader, history, observe
from pinecall.wire._names import Env
from pinecall.wire.commands import COMMANDS
from pinecall.wire.events import ErrorEvent, event_of
from pinecall.wire.frames import Command, Entry, WireModel
from pinecall.wire.parts import AgentConfig

# The `error` code a person's stop sends (`POST /v1/apps/{app}/stop`): the client never dials
# again after it, or the stop would undo itself.
STOPPED = "stopped"

# Within a process manager's shutdown grace.
TOOLS_WITHIN_S = 30.0


@dataclass(frozen=True)
class Found:
    """One chunk a search found: the file it came from, its heading, its text."""

    path: str
    heading: str | None
    text: str


@dataclass(frozen=True)
class Drained:
    """What a drain did: calls handed over or parked, tools that were running, and that finished."""

    handed: int
    parked: int
    tools: int
    finished: int


class Client:
    """One app's socket to Pinecall, and the agents held on it.

    It reads nothing from the environment: `url`, `api_key` and `env` are given, so a stale
    variable never picks another org's key. The serve entry reads them, once.
    """

    def __init__(
        self,
        url: str,
        api_key: str,
        env: Env | None = None,
        *,
        ping_s: float = 30.0,
        backoff: Backoff = Backoff(),  # noqa: B008 - frozen, so one default is shared safely
    ) -> None:
        """A client of the gateway at `url`, with this key, in this world.

        Args:
            url: the gateway, `https://cloud.pinecall.io`.
            api_key: the key; sent as a header, never in a URL.
            env: the world, `sandbox` or `production`; left out, the key's own.
            ping_s: how often each agent asks whether the socket is alive.
            backoff: how long to wait before dialling again after a drop.
        """
        self.url = url
        self.env = env
        self.sdk = f"pinecall-python/{__version__}"
        """How this app is named in the org's list of processes."""
        self.host = socket.gethostname()
        self._signing = (api_key, env)
        self._agents: dict[str, AgentSocket] = {}
        self._entries: list[Callable[[Entry], None]] = []
        self._errors: list[Callable[[Exception], None]] = []
        self._connected: list[Callable[[], None]] = []
        self._stopped: list[Callable[[str], None]] = []
        self._listeners: Listeners[Call | None] = Listeners(self.on_error)
        handlers = Handlers(self._declare_all, self._take, self.on_error, self._ping_all)
        self._connection = Connection(url, self._signing, handlers, ping_s=ping_s, backoff=backoff)

    def agent(
        self,
        slug: str,
        config: AgentConfig | None = None,
        tools: Sequence[Tool] = (),
        *,
        takes_unclaimed: bool = True,
        answers_dev: bool = False,
    ) -> AgentSocket:
        """Hold an agent on this socket; nothing is sent until `connect`.

        Args:
            slug: the agent's name.
            config: what the agent declares; its `tools` are the tools' specs.
            tools: each tool's spec and what runs when the model calls it.
            takes_unclaimed: a call that names no app may come here; a console's process says no.
            answers_dev: this socket answers the console's asks for the agent, and declares nothing.
        """
        role = Role(takes_unclaimed=takes_unclaimed, answers_dev=answers_dev)
        held = AgentSocket(slug, self, config or AgentConfig(), tools, role)
        self._agents[slug] = held
        return held

    async def connect(self) -> None:
        """Open the socket and register every agent; raises when the first try fails."""
        await self._connection.start()

    @property
    def connected(self) -> bool:
        """Whether the socket is up."""
        return self._connection.open

    async def drain(
        self, *, answer_within_s: float = ANSWER_WITHIN_S, tools_within_s: float = TOOLS_WITHIN_S
    ) -> Drained:
        """Leave without cutting a call: each agent hands its calls over, and running tools finish.

        Args:
            answer_within_s: how long each agent waits for the gateway to say where its calls went.
            tools_within_s: how long the tools still running have to send their result.
        """
        self._connection.leaving()
        agents = list(self._agents.values())
        if not self.connected:
            return Drained(0, 0, 0, 0)
        handed = parked = 0
        for answer in await asyncio.gather(
            *(agent.drain(answer_within_s) for agent in agents), return_exceptions=True
        ):
            if isinstance(answer, BaseException):
                self.on_error(
                    answer if isinstance(answer, Exception) else PinecallError(str(answer))
                )
                continue
            handed, parked = handed + answer.handed, parked + answer.parked
        running = sum(agent.in_flight for agent in agents)
        with contextlib.suppress(TimeoutError):
            await asyncio.wait_for(
                asyncio.gather(*(agent.settled() for agent in agents)), tools_within_s
            )
        left = sum(agent.in_flight for agent in agents)
        return Drained(handed, parked, running, running - left)

    async def close(self) -> None:
        """Close the socket for good."""
        await self._connection.close()

    # ── listening ──

    def on(self, type_: str, listener: Listener[Call | None]) -> Callable[[], None]:
        """Listen for one type of event across every agent on this client."""
        return self._listeners.on(type_, listener)

    def on_any(self, listener: AnyListener[Call | None]) -> Callable[[], None]:
        """Listen for every event across every agent."""
        return self._listeners.on_any(listener)

    def on_entries(self, listener: Callable[[Entry], None]) -> Callable[[], None]:
        """Every entry the socket receives, as the gateway wrote it, before any agent takes it."""
        return _kept(self._entries, listener)

    def on_errors(self, listener: Callable[[Exception], None]) -> Callable[[], None]:
        """What fails with nobody waiting for it: a bad frame, a listener, a drop."""
        return _kept(self._errors, listener)

    def on_connected(self, listener: Callable[[], None]) -> Callable[[], None]:
        """After every (re)connect, once every agent is declared."""
        return _kept(self._connected, listener)

    def on_stopped(self, listener: Callable[[str], None]) -> Callable[[], None]:
        """A person of the org stopped this app: the socket is closed for good."""
        return _kept(self._stopped, listener)

    # ── reading a log ──

    async def history(
        self, *, call: str | None = None, agent: str | None = None, after: int = 0
    ) -> Page:
        """One page of a call's log, or an agent's own, after the cursor, and its folded state."""
        return await history(self._reader(), call=call, agent=agent, after=after)

    def observe(
        self, *, call: str | None = None, agent: str | None = None, after: int = 0
    ) -> AsyncIterator[Observation]:
        """A call's log, or an agent's own, from the cursor on, each entry with the state so far."""
        return observe(self._reader(), call=call, agent=agent, after=after)

    def _reader(self) -> Reader:
        return Reader(self.url, *self._signing)

    # ── a search for a call ──

    async def search(self, call: str, query: str, k: int | None = None) -> list[Found]:
        """Search the agent's bases for a call this client serves; the gateway runs and logs it."""
        body = {"tool": "search", "input": {"query": query} | ({} if k is None else {"k": k})}
        async with httpx.AsyncClient() as http:
            answered = await http.post(
                lookup_url(self.url, call), json=body, headers=signed(*self._signing)
            )
        if answered.is_error:
            raise Refused(str(answered.status_code), detail_of(answered))
        chunks = typing.cast("list[dict[str, str | None]]", answered.json()["output"]["chunks"])
        return [Found(str(one["path"]), one.get("heading"), str(one["text"])) for one in chunks]

    # ── what the agents send through ──

    def send(self, type_: str, agent: str, call: str | None, data: WireModel, id_: str) -> None:
        """Send one command, checked against its shape before it leaves."""
        if not isinstance(data, COMMANDS[type_]):
            raise WireError(
                f"{type_} carries a {COMMANDS[type_].__name__}, not a {type(data).__name__}"
            )
        command = Command(type=type_, agent=agent, call=call, id=id_, data=data.written())
        self._connection.send(command.written_json())

    def seen(self, type_: str, event: WireModel, call: Call | None) -> None:
        """Hand an event an agent took to the client's own listeners."""
        self._listeners.emit(type_, event, call)

    def on_error(self, error: Exception) -> None:
        """Say an error nobody waits for; to stderr when nobody listens."""
        if not self._errors:
            print(f"pinecall: {error}", file=sys.stderr)  # noqa: T201 - an unheard error is not lost
            return
        for listener in list(self._errors):
            listener(error)

    def _take(self, entry: Entry) -> None:
        for listener in list(self._entries):
            try:
                listener(entry)
            except Exception as failed:  # noqa: BLE001 - a listener's failure is said, never raised
                self.on_error(failed)
        if entry.type == "error" and entry.agent == "":
            said = event_of(entry)
            if isinstance(said, ErrorEvent) and said.code == STOPPED:
                asyncio.ensure_future(self._stop(said.message))  # noqa: RUF006 - it closes the socket that holds it
                return
        held = self._agents.get(entry.agent)
        if held is not None:
            held.take(entry)

    async def _stop(self, why: str) -> None:
        await self._connection.close()
        if not self._stopped:
            self.on_error(NotConnected(why))
        for listener in list(self._stopped):
            listener(why)

    async def _declare_all(self) -> None:
        for held in self._agents.values():
            await held.open()
        for listener in list(self._connected):
            try:
                listener()
            except Exception as failed:  # noqa: BLE001 - a listener's failure is said, never raised
                self.on_error(failed)

    def _ping_all(self) -> None:
        for held in self._agents.values():
            try:
                held.ping()
            except NotConnected as failed:
                self.on_error(failed)


def _kept(
    listeners: list[Callable[..., None]], listener: Callable[..., None]
) -> Callable[[], None]:
    listeners.append(listener)
    return lambda: listeners.remove(listener)


def detail_of(answered: httpx.Response) -> str:
    """The `detail` the gateway wrote, or its whole body."""
    try:
        said: object = answered.json()
    except ValueError:
        return answered.text
    if isinstance(said, dict):
        detail = typing.cast("dict[str, object]", said).get("detail")
        if isinstance(detail, str):
            return detail
    return answered.text
