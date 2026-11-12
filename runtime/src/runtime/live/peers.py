"""What the gateways tell each other of the live calls: each channel of the signal as a value, and who runs what."""

import asyncio
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import override

from runtime.enums import Env
from runtime.exceptions import ServiceUnavailable
from runtime.kit.loops import survive
from runtime.shared_state import SharedState
from runtime.signal import Listener, Signal
from runtime.wire.commands import DevAnswer
from runtime.wire.signal import Commanded, ForApp, HandedMessage, Handoff, OwnedShare

# The model, in one place. The log (Postgres) is the durable channel and the signal (Redis) loses
# messages. A call is its opener's: the gateway that opened it (`Served.opened_here`) is the only one
# that counts it against its org, parks it and hands it on; every other gateway serves a copy, built from the
# opening that was kept, the first time it is asked for the call. A spoken call outlives its opener: once
# that gateway has said nothing for `OPENER_SILENT_S`, the gateway its worker reads its commands from
# adopts it (`Calls.adopt_orphans`). An app's socket lives on one
# gateway and has an inbox there (`app:{app}`): what another gateway has for it goes through it. A
# written call's session and a WhatsApp thread run on one gateway, which says so (`owned`), and
# another takes one up only once that gateway fell silent. What the signal loses, the next pass of
# the reaper mends (`handoff.hand_parked`, `reaper.let_go`) or the next retry does. Until 2026-11
# this was read out of eight modules; the names below were strings formatted where they were used.

# How long a listener waits for the signal before it listens again.
RETRY_S = 1.0


# A channel's name may carry what it is of (`cmd:{call}`): the key is given where it is told or heard.
@dataclass(frozen=True, slots=True)
class Channel[T]:
    """One channel of the signal: its name, and how a message of it is read and written."""

    name: str
    load: Callable[[bytes], T]
    dump: Callable[[T], bytes]

    # Lossy, as the signal is: what nobody heard is mended by whoever tells it again.
    def tell(self, signal: Signal, message: T, **key: str) -> None:
        """Queue the message for whoever listens; never waits."""
        signal.publish(self.name.format(**key), self.dump(message))

    # Nobody hearing it is the refusal the sender gives, and so is a signal that is away: the app
    # or the person who asked tries again.
    async def reach(self, signal: Signal, message: T, **key: str) -> bool:
        """Tell the message now; False when nobody listens, or the signal is down."""
        try:
            return await signal.publish_now(self.name.format(**key), self.dump(message)) > 0
        except ServiceUnavailable:
            return False

    async def subscribe(self, signal: Signal, **key: str) -> Listener:
        """A listener of the channel from now on; ServiceUnavailable while the signal is down."""
        return await signal.subscribe(self.name.format(**key))

    # The one loop a channel is heard with: until 2026-11 it was written three times (a socket's
    # inbox, the handoffs, the threads handed on). A message that cannot be read or applied is said
    # and the next is heard: a task that died with it would leave its owner deaf for its whole life.
    # `asked` is set once the signal was asked for the channel, heard on or not: what is told before
    # that is lost, so whoever must not miss a word waits for it.
    async def listen(
        self, signal: Signal, hear: Callable[[T], Awaitable[None]], *, asked: asyncio.Event | None = None, **key: str
    ) -> None:
        """Hear the channel for ever: listened to again while the signal is down, each message survived."""
        named = self.name.format(**key)
        while True:
            try:
                listener = await signal.subscribe(named)
            except ServiceUnavailable:
                listener = None
            if asked is not None:
                asked.set()
            if listener is not None:
                try:
                    async for data in listener:
                        with survive("a message between gateways", named):
                            await hear(self.load(data))
                finally:
                    listener.close()
            await asyncio.sleep(RETRY_S)


# One channel per call: every gateway that serves the call listens on it while it does. Each command
# under an id of its own, which the worker's stream carries: every gateway keeps a spoken call's
# commands for its worker, and a worker that reads them from a second gateway drops what it applied.
COMMANDS: Channel[Commanded] = Channel(
    "cmd:{call}", Commanded.model_validate_json, lambda said: said.model_dump_json().encode()
)
# Each app socket's inbox, listened to by the gateway holding it while it is open.
APP_INBOX: Channel[ForApp] = Channel(
    "app:{app}", ForApp.model_validate_json, lambda said: said.model_dump_json().encode()
)
# Where a dev.request's answer goes back to the gateway that asked it.
DEV_ANSWERS: Channel[DevAnswer] = Channel(
    "answer:{id}", DevAnswer.model_validate_json, lambda said: said.model_dump_json().encode()
)
# What every gateway hears about the sockets that take an agent and the ones that let a call go.
HANDOFFS: Channel[Handoff] = Channel(
    "handoff", Handoff.model_validate_json, lambda said: said.model_dump_json(exclude_none=True).encode()
)
# Where a gateway hands a WhatsApp message on to the one holding its contact's thread.
THREADS: Channel[HandedMessage] = Channel(
    "thread:{gateway}", HandedMessage.model_validate_json, lambda said: said.model_dump_json().encode()
)

# Where a claim wakes the page waiting on a caller's code, whichever gateway it waits on. The word carries
# nothing: it says "read the code again". Both are the bytes the release before 2026-11 says and hears.
CODE_TAKEN: Channel[bytes] = Channel("code:{agent}:{code}", bytes, bytes)
TAKEN = b"taken"

# The shares each gateway says whole, again and again (`shared_state.SharedState`): the app sockets it
# holds, the agents they hold, the written calls and threads it runs, and the calls it opened.
SOCKETS_CHANNEL = "sockets"
HELD_CHANNEL = "held"
OWNED_CHANNEL = "owned"
RUNNING_CHANNEL = "running"


# The gateways of the release before 2026-11 say and read the same words, joined by a bar: until that
# release is gone the bytes are these.
@dataclass(frozen=True, slots=True)
class CallsAtOnce:
    """An org's calls at once in one env, as the gateways name them to each other."""

    org: str
    env: Env

    @override
    def __str__(self) -> str:
        return f"{self.org}|{self.env.value}"


@dataclass(frozen=True, slots=True)
class ThreadKey:
    """One WhatsApp conversation: whose, in which env, the number written to, and who wrote."""

    org: str
    env: Env
    number: str
    wa_id: str

    @override
    def __str__(self) -> str:
        return "|".join((self.org, self.env.value, self.number, self.wa_id))


# A session and a thread live where they were opened: another gateway takes one up only once its
# owner fell silent, when the owner is forgotten (`shared_state.SILENT_AT_MOST_S`).
class Owners:
    """This gateway's written calls and threads, and every other gateway's as it says them."""

    def __init__(self, signal: Signal) -> None:
        """Nothing run and nothing held yet."""
        self.shared = SharedState(
            signal,
            OWNED_CHANNEL,
            load=OwnedShare.model_validate,
            dump=OwnedShare.model_dump,
            empty=OwnedShare(),
            on_change=self._merge,
        )
        self._texts: set[str] = set()
        self._threads: set[str] = set()
        self._texts_elsewhere: set[str] = set()
        # Each thread another live gateway holds, and that gateway's name on the signal.
        self._threads_elsewhere: dict[str, str] = {}

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

    def run_call(self, call: str, *, here: bool) -> None:
        """A written call's session started here, or ended."""
        self._set(self._texts, call, here)

    def hold_thread(self, thread: ThreadKey, *, here: bool) -> None:
        """A contact's thread opened here, or closed."""
        self._set(self._threads, str(thread), here)

    def runs_elsewhere(self, call: str) -> bool:
        """Whether a live gateway other than this one runs the written call."""
        return call in self._texts_elsewhere

    def find_thread_holder(self, thread: ThreadKey) -> str | None:
        """The other gateway holding the contact's thread, by its name on the signal; None when none does."""
        return self._threads_elsewhere.get(str(thread))

    # One setter for both: until 2026-11 the same eight lines were written for the calls and the threads.
    def _set(self, mine: set[str], key: str, here: bool) -> None:
        if (key in mine) == here:
            return
        if here:
            mine.add(key)
        else:
            mine.discard(key)
        self.shared.put(OwnedShare(texts=tuple(sorted(self._texts)), threads=tuple(sorted(self._threads))))

    def _merge(self) -> None:
        heard = self.shared.theirs.items()
        self._texts_elsewhere = {call for _, share in heard for call in share.share.texts}
        self._threads_elsewhere = {thread: gateway for gateway, share in heard for thread in share.share.threads}
