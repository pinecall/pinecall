"""What the gateways tell each other: a call's commands, a socket's messages, who holds what."""

from dataclasses import dataclass

from pydantic import TypeAdapter

from pinecall_runtime.exceptions import ServiceUnavailable
from pinecall_runtime.kit.auth import Scope
from pinecall_runtime.kit.shared_state import SharedState
from pinecall_runtime.redis import Signal
from pinecall_runtime.wire.base import Command
from pinecall_runtime.wire.commands import DevAnswer
from pinecall_runtime.wire.signal import Bound, ForApp

# One channel per call: every gateway that serves the call listens on it while it does.
COMMANDS_CHANNEL = "cmd:{call}"
# The one verb a desk sends, which a written call's session takes as a supervisor's.
SUPERVISOR_VERB = "supervisor.verb"
# The caller's own hang-up, said at the gateway's door: whatever runs the call ends it at once. Not
# an app's command: the gateway's alone, so no app can hang up in the caller's name.
CALLER_HUNG_UP = "caller.hung_up"
# Each app socket's inbox, listened to by the gateway holding it while it is open.
APP_CHANNEL = "app:{app}"
# Where a dev.request's answer goes back to the gateway that asked it.
ANSWER_CHANNEL = "answer:{id}"
# Every gateway says the app sockets it holds here, for the org's list of apps.
SOCKETS_CHANNEL = "sockets"
# Each gateway says the written calls it runs and the threads it holds here, merged by each.
OWNED_CHANNEL = "owned"
# Where a gateway hands a WhatsApp message on to the one holding its contact's thread.
THREAD_CHANNEL = "thread:{gateway}"
# What every gateway hears about the sockets that take an agent and the ones that let a call go.
HANDOFF_CHANNEL = "handoff"


@dataclass(frozen=True)
class SocketRow:
    """An app socket another gateway holds, as the org's list of apps shows it."""

    app: str
    scope: Scope
    address: str | None
    connected_at: float
    host: str | None = None


@dataclass(frozen=True)
class Owned:
    """One gateway's share: the written calls whose sessions run there, the threads it holds."""

    texts: tuple[str, ...] = ()
    threads: tuple[str, ...] = ()


@dataclass(frozen=True)
class Taking:
    """A socket took an agent in a scope: the calls parked for it, on any gateway, are its to take."""

    app: str
    scope: Scope
    agent: str


@dataclass(frozen=True)
class Unbound:
    """A socket let a call go on the gateway that held it: the gateway that opened the call hands it on."""

    call: str
    app: str


@dataclass(frozen=True)
class Handoff:
    """One message of the handoff channel: a socket that took an agent, or a call a socket let go."""

    taking: Taking | None = None
    unbound: Unbound | None = None


_ROWS: TypeAdapter[tuple[SocketRow, ...]] = TypeAdapter(tuple[SocketRow, ...])
_OWNED: TypeAdapter[Owned] = TypeAdapter(Owned)
_HANDOFF: TypeAdapter[Handoff] = TypeAdapter(Handoff)


class Elsewhere:
    """The app sockets the other gateways hold, as each says them."""

    def __init__(self, signal: Signal) -> None:
        """Nothing heard yet."""
        self.shared = SharedState(signal, SOCKETS_CHANNEL, _ROWS, (), lambda: None)

    async def start(self) -> None:
        """Hear the others, and say this gateway's."""
        await self.shared.start()

    async def close(self) -> None:
        """Stop hearing and saying."""
        await self.shared.close()

    def rows_of(self, org: str, env: str) -> list[SocketRow]:
        """The org's sockets in the env on every other gateway."""
        return [
            row
            for heard in self.shared.theirs.values()
            for row in heard.share
            if row.scope.org == org and row.scope.env == env
        ]


# A session and a thread live where they were opened: another gateway takes one up only once its
# owner fell silent, when the owner is forgotten (kit/shared_state.py).
class Owners:
    """This gateway's written calls and threads, and every other gateway's as it says them."""

    def __init__(self, signal: Signal) -> None:
        """Nothing run and nothing held yet."""
        self.shared = SharedState(signal, OWNED_CHANNEL, _OWNED, Owned(), self._merge)
        self.texts: set[str] = set()
        self.threads: set[str] = set()
        self._texts_elsewhere: set[str] = set()
        # Each thread another live gateway holds, and that gateway's name on the signal.
        self.threads_elsewhere: dict[str, str] = {}

    @property
    def id(self) -> str:
        """This gateway's name on the signal."""
        return self.shared.id

    async def start(self) -> None:
        """Hear the other gateways, and say what runs here."""
        await self.shared.start()

    async def close(self) -> None:
        """Stop hearing and saying."""
        await self.shared.close()

    def running(self, call: str, *, here: bool) -> None:
        """A written call's session started here, or ended."""
        if (call in self.texts) == here:
            return
        if here:
            self.texts.add(call)
        else:
            self.texts.discard(call)
        self._say()

    def holding(self, thread: str, *, here: bool) -> None:
        """A contact's thread opened here, or closed."""
        if (thread in self.threads) == here:
            return
        if here:
            self.threads.add(thread)
        else:
            self.threads.discard(thread)
        self._say()

    def text_elsewhere(self, call: str) -> bool:
        """Whether a live gateway other than this one runs the written call."""
        return call in self._texts_elsewhere

    def _say(self) -> None:
        self.shared.put(Owned(texts=tuple(sorted(self.texts)), threads=tuple(sorted(self.threads))))

    def _merge(self) -> None:
        heard = self.shared.theirs.items()
        self._texts_elsewhere = {call for _, share in heard for call in share.share.texts}
        self.threads_elsewhere = {thread: gateway for gateway, share in heard for thread in share.share.threads}


# Lossy, as the signal is: nobody hearing it is the refusal the sender gives, and a Redis that is
# away is a ServiceUnavailable the app can try again after.
async def send_command(signal: Signal, command: Command) -> bool:
    """Tell the gateways that serve the call; False when none does."""
    return await signal.published(COMMANDS_CHANNEL.format(call=command.call), command.model_dump_json().encode()) > 0


# Lossy, as the signal is: a bound call whose notice was lost is told again when its worker asks
# a tool, and parked calls are handed on at every pass of the reaper.
def tell_bound(signal: Signal, app: str, bound: Bound) -> None:
    """Tell the gateway holding the socket that the call is bound to it, from this seq."""
    signal.publish(APP_CHANNEL.format(app=app), ForApp(bound=bound).model_dump_json().encode())


# Lossy, as the signal is: a call whose notice was lost is handed on at the reaper's next pass.
def tell_handoff(signal: Signal, message: Handoff) -> None:
    """Tell every gateway that a socket took an agent, or that one let a call go."""
    signal.publish(HANDOFF_CHANNEL, _HANDOFF.dump_json(message, exclude_none=True))


def heard_handoff(data: bytes) -> Handoff:
    """One message of the handoff channel, read."""
    return _HANDOFF.validate_json(data)


async def tell_app(signal: Signal, app: str, message: ForApp) -> bool:
    """Hand the message to the gateway holding the socket; False when none does."""
    try:
        return await signal.published(APP_CHANNEL.format(app=app), message.model_dump_json().encode()) > 0
    except ServiceUnavailable:
        return False


async def answer_back(signal: Signal, answer: DevAnswer) -> bool:
    """Hand a dev.answer to the gateway that asked it; False when none waits."""
    try:
        return await signal.published(ANSWER_CHANNEL.format(id=answer.id), answer.model_dump_json().encode()) > 0
    except ServiceUnavailable:
        return False
