"""What evals starts and does not await: the runs a gateway plays, its simulated calls, the callers a process plays."""

import asyncio
import logging
import time
from collections.abc import AsyncGenerator, Awaitable, Callable, Coroutine
from contextlib import asynccontextmanager
from functools import partial

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from runtime.actor import Scope
from runtime.enums import Env
from runtime.evals.models import CallerJob
from runtime.evals.repository import CallerJobRepository, RunLeaseRepository
from runtime.exceptions import Conflict, TooManyRequests
from runtime.kit.loops import loop, survive
from runtime.kit.tasks import Tasks
from runtime.scoping import box_wide, within_org
from runtime.shared_state import SharedState
from runtime.signal import Signal
from runtime.wire.signal import SimulatingShare

logger = logging.getLogger(__name__)

# A run holds its agent for so long and renews it at a third of that: a gateway that died
# mid-run leaves a lease another run takes once it ran out.
LEASED_S = 60.0
RENEWED_EVERY_S = LEASED_S / 3


# The channel each gateway says its simulated calls on, and how often; a change is said at once.
SIMULATING_CHANNEL = "simulating"
SIMULATING_EVERY_S = 1.0
TOO_MANY_AT_ONCE = "the org has {playing} simulated calls on the line in {env}, the most at once: wait for one to end"
# How long a caller is told to wait before asking again: about a turn of a call.
ASK_AGAIN_IN_S = 15


class TooManyAtOnce(TooManyRequests):
    """The org has as many simulated calls on the line in the env as it may."""

    def __init__(self, env: Env, playing: int) -> None:
        super().__init__(TOO_MANY_AT_ONCE.format(playing=playing, env=env.value), retry_after_s=ASK_AGAIN_IN_S)


# The run itself is coroutines of this process, gone with it; the lease is in Postgres, so a run on
# one gateway holds the agent on every one, and a gateway that died mid-run leaves a lease another
# run takes once it ran out.
class Runner:
    """The runs this gateway plays, each on a task of its own, and the agent each one holds."""

    def __init__(self, sessions: async_sessionmaker[AsyncSession]) -> None:
        self.sessions = sessions
        self._holding: dict[str, str] = {}
        self._playing = Tasks("an eval run")

    # Refused, not queued: the refusal names the run to follow instead.
    async def hold(self, run: str, agent: str) -> None:
        """Hold the agent for this run, renewed while it plays; Conflict while another run holds it."""
        if not await self._lease(run, agent):
            async with self.sessions.begin() as session:
                holding = await RunLeaseRepository(session).holder_of(agent)
            raise Conflict(
                f"eval run {holding or 'another run'} is running on agent {agent}: a run drives the app that "
                "also answers that agent's real calls, so there is one per agent at a time"
            )
        self._holding[run] = agent

    async def let_go(self, run: str, agent: str) -> None:
        """Let the agent go: its renewal stopped, the lease released."""
        self._holding.pop(run, None)
        async with self.sessions.begin() as session:
            await RunLeaseRepository(session).release(agent, run)

    # The request's context goes with the task, so the run plays as the org that asked for it.
    def play(self, run: str, played: Coroutine[object, object, None]) -> None:
        """Play the run on a task of its own, kept until it ends; a break is logged, never lost."""
        self._playing.spawn(played, name=f"eval run {run}")

    # A renewal that failed is said and tried again a third of the lease on: the one that ended the
    # pass would let another run take the agent under this one.
    async def renew(self) -> None:
        """Renew the lease of every run this gateway plays."""
        for run, agent in list(self._holding.items()):
            with survive("renewing the lease of an eval run", run):
                await self._lease(run, agent)

    async def stop(self) -> None:
        """Stop every run still playing: each one writes itself stopped as its task is cancelled."""
        await self._playing.cancel()

    async def _lease(self, run: str, agent: str) -> bool:
        async with self.sessions.begin() as session:
            return await RunLeaseRepository(session).take(agent, run, LEASED_S)


# Until 2026-11 each run renewed its own lease in a `while True` of the service, on a bare task: one
# that died showed nowhere, and its run went on holding an agent whose lease had run out.
@loop("eval-run-leases", every_s=RENEWED_EVERY_S)
async def renew_leases(runner: Runner) -> None:
    """One pass: every run this gateway plays keeps its agent a minute more."""
    await runner.renew()


# A comparison is played by the gateway that took its request, which says so every twenty seconds; one
# nobody said anything of for forty went with its gateway (a release, a crash). Every gateway looks,
# and the one that finds it goes on with it. What a take-up does is the service's (`placing`), handed
# in: this module is what the service's own modules import.
TAKEN_UP_EVERY_S = 10.0


@loop("comparisons-left", every_s=TAKEN_UP_EVERY_S)
async def take_up_comparisons(take_up_left: Callable[[], Awaitable[None]]) -> None:
    """One pass: every comparison its gateway left is taken up by this one."""
    await take_up_left()


# Each gateway counts the calls it plays and says the count on the signal, as the calls at once
# are counted: a call takes its place the instant it is admitted, with no await between the
# count and the place, so a burst on one gateway never passes the ceiling; the other gateways'
# counts are heard the instant they change, so a burst split between two may pass it by what
# both admitted in that instant, as the calls at once may. A call never counts twice whichever
# gateway its worker reached.
class Simulations:
    """The simulated calls this process plays, and every gateway's count; stopped with the process."""

    def __init__(self, signal: Signal) -> None:
        self._on_the_line: dict[str, Scope] = {}
        self._calls = Tasks("a simulated call")
        # The comparisons this process is still placing the calls of: each waits for places on the line.
        self._placing = Tasks("a comparison's placing")
        self._counted = SharedState(
            signal,
            SIMULATING_CHANNEL,
            load=SimulatingShare.model_validate,
            dump=_dump_share,
            empty=SimulatingShare({}),
            on_change=lambda: None,
            every_s=SIMULATING_EVERY_S,
            gathered=self._count_here,
        )

    async def start(self) -> None:
        """Hear the other gateways' counts, and say this one's."""
        await self._counted.start()

    async def stop(self) -> None:
        """Stop every call still playing and every placing: each call's caller hangs up as its task is cancelled."""
        await self._calls.cancel()
        await self._placing.cancel()
        await self._counted.close()

    # A call that has its place already is refused, never given it again: until 2026-11 an id sent
    # twice took the place of the call playing under it, and the second one's end gave that place back,
    # so the first went on uncounted and was not stopped with the process.
    # `beside` is what the org has on its line that no gateway's memory counts: the spoken calls a
    # process plays, each a row (`service.caller_jobs`), read by whoever asks before this is called.
    def take_place(self, call: str, scope: Scope, at_most: int, *, beside: int = 0) -> None:
        """Give the call its place on the line now, or refuse it: the org has its `at_most` there already."""
        if call in self._on_the_line:
            # A call id names a room, a log and a recording: a simulated caller is put on a new one alone.
            raise Conflict(f"call {call} exists already: a simulated caller is placed on a call id nobody opened")
        playing = self.count(scope.org, scope.env) + beside
        if playing >= at_most:
            raise TooManyAtOnce(scope.env, playing)
        self._on_the_line[call] = scope
        self._say()

    def give_back(self, call: str) -> None:
        """Give the call's place back: it was refused after it took it, or it ended."""
        if self._on_the_line.pop(call, None) is not None:
            self._say()

    # The request's context goes with the task, so the call is played as the org that asked for it.
    def play(self, call: str, played: Coroutine[object, object, object]) -> None:
        """Play the call that took its place on a task of its own; its place is given back when it ends."""
        task = self._calls.spawn(played, name=f"simulated call {call}")
        task.add_done_callback(lambda _ended: self.give_back(call))

    # The request's context goes with the task, as a call's does: the calls are placed as the org that asked.
    def place_later(self, placing: Coroutine[object, object, None]) -> None:
        """Go on placing a comparison's calls after its request was answered; a break is logged, never lost."""
        self._placing.spawn(placing)

    @asynccontextmanager
    async def hold_place(self, call: str, scope: Scope, at_most: int, *, beside: int = 0) -> AsyncGenerator[None]:
        """The call's place on the line for the block, which plays it: taken first, given back after."""
        self.take_place(call, scope, at_most, beside=beside)
        try:
            yield
        finally:
            self.give_back(call)

    def count(self, org: str, env: Env) -> int:
        """How many of the org's simulated calls are on the line in the env, on every gateway."""
        key = _key_of(org, env)
        theirs = sum(heard.share.root.get(key, 0) for heard in self._counted.theirs.values())
        return self._count_here().root.get(key, 0) + theirs

    def _count_here(self) -> SimulatingShare:
        counts: dict[str, int] = {}
        for scope in self._on_the_line.values():
            key = _key_of(scope.org, scope.env)
            counts[key] = counts.get(key, 0) + 1
        return SimulatingShare(counts)

    def _say(self) -> None:
        self._counted.put(self._count_here())


# The bytes the release before 2026-11 says and hears on the channel: `<org>|<env>`.
def _key_of(org: str, env: Env) -> str:
    return f"{org}|{env.value}"


def _dump_share(share: SimulatingShare) -> object:
    return share.model_dump(mode="json")


# ── the callers a process plays ──

# A process says it still plays the callers it claimed this often, and one silent for four of them is
# gone: its callers are taken up by a gateway (`service.caller_jobs.settle`).
A_CALLER_IS_SAID_EVERY_S = 10.0
LEFT_AFTER_S = 4 * A_CALLER_IS_SAID_EVERY_S
# How often a process with room looks for a caller that waits, and how often a gateway settles.
CLAIMED_EVERY_S = 1.0
SETTLED_EVERY_S = 2.0
# A caller's leg hands the room ten milliseconds of audio a hundred times a second, a tenth of a second
# ahead (`service.leg`): a loop that wakes this late has used up half of that, for every caller it
# plays at once. It reads the clock twenty times a second, and after a late reading takes no caller
# for ten seconds: the ones it plays are what made it late.
THE_CLOCK_IS_READ_EVERY_S = 0.05
A_LATE_READING_S = 0.05
A_LATE_PROCESS_RESTS_S = 10.0
# What a process told to stop gives the calls it plays: a simulated call is ten minutes at most
# (`session.clock`), its caller hangs up and hears the end within one more.
CALLERS_DRAIN_S = 11 * 60.0


# One Python loop plays the callers it claimed and nothing else comes before them. Until 2026-11-25
# every simulated caller was a task of the gateway that took its request, with everything else that
# gateway does: nineteen at once were late with their frames, the room heard gaps inside each word, and
# the agents were judged on audio no caller makes. A process claims what it can play on time, says so
# while it plays, and when told to stop takes no other and ends with the calls it has.
class Callers:
    """The simulated callers this process plays: each claimed off its row, played on a task, let go by it."""

    def __init__(
        self,
        sessions: async_sessionmaker[AsyncSession],
        play: Callable[[CallerJob, str], Coroutine[object, object, None]],
        *,
        name: str,
        at_once: int,
        clock: Callable[[], float] = time.time,
        ticks: Callable[[], float] = time.monotonic,
    ) -> None:
        self.name = name
        self._sessions = sessions
        self._play = play
        self._at_once = at_once
        self._clock = clock
        self._ticks = ticks
        self._playing = Tasks("a simulated caller")
        # The calls whose callers it plays now: what it says it still has.
        self._calls: set[str] = set()
        # One pass claims at a time: its room is counted before each claim and taken after it.
        self._claiming = asyncio.Lock()
        self._stopping = False
        self._read_at: float | None = None
        self._rests_until = 0.0

    @property
    def playing(self) -> int:
        """How many callers this process plays now."""
        return len(self._playing)

    @property
    def takes_more(self) -> bool:
        """Whether this process may claim a caller now: it has room, it is on time, and it was not told to stop."""
        return not self._stopping and self.playing < self._at_once and self._ticks() >= self._rests_until

    def read_clock(self) -> None:
        """One reading of the clock, a twentieth of a second after the last: a late one says the loop is behind."""
        now = self._ticks()
        late = 0.0 if self._read_at is None else now - self._read_at - THE_CLOCK_IS_READ_EVERY_S
        self._read_at = now
        if late >= A_LATE_READING_S:
            logger.warning(
                "%s woke %.0f ms late with %d callers: it takes no other for %.0f s",
                self.name,
                late * 1000,
                self.playing,
                A_LATE_PROCESS_RESTS_S,
            )
            self._rests_until = now + A_LATE_PROCESS_RESTS_S

    # The org the caller is of goes with its task, as a request's does: what the caller reads and
    # writes is its org's alone. The claim itself is the box's, across orgs.
    async def claim(self) -> None:
        """One pass: take the callers that wait for a process, one at a time, while this one takes more."""
        async with self._claiming:
            while self.takes_more:
                with box_wide():
                    async with self._sessions.begin() as session:
                        job = await CallerJobRepository(session).claim(self.name, self._clock())
                if job is None:
                    return
                with within_org(job.org):
                    task = self._playing.spawn(self._play(job, self.name), name=f"the caller of {job.call}")
                self._calls.add(job.call)
                task.add_done_callback(partial(self._forget, job.call))

    def _forget(self, call: str, _ended: asyncio.Task[object]) -> None:
        self._calls.discard(call)

    async def renew(self) -> None:
        """Say this process still plays each caller it has on a task now."""
        if self._calls:
            with box_wide():
                async with self._sessions.begin() as session:
                    await CallerJobRepository(session).renew(self.name, sorted(self._calls), self._clock())

    # A call that outlives the wait is cut: its task says on its row how it was left (`play_claimed`),
    # so a call that never began is another process's to play and one on the line is said lost.
    async def stop(self, within_s: float) -> None:
        """Take no other caller, wait this long for the ones played to end, and cut what is left."""
        self._stopping = True
        deadline = self._ticks() + within_s
        while self.playing and self._ticks() < deadline:
            await asyncio.sleep(min(1.0, max(0.0, deadline - self._ticks())))
        if self.playing:
            logger.warning("%s: %d callers outlived the %.0f s it was given to stop", self.name, self.playing, within_s)
        await self._playing.cancel()


@loop("callers-claimed", every_s=CLAIMED_EVERY_S)
async def claim_callers(callers: Callers) -> None:
    """One pass: the callers that wait for a process are taken by this one, while it has room and is on time."""
    await callers.claim()


@loop("callers-said", every_s=A_CALLER_IS_SAID_EVERY_S)
async def say_callers(callers: Callers) -> None:
    """One pass: this process says it still plays the callers it claimed."""
    await callers.renew()


@loop("callers-clock", every_s=THE_CLOCK_IS_READ_EVERY_S)
async def watch_the_clock(callers: Callers) -> None:
    """One pass: the clock is read, and a reading that came late rests the process."""
    callers.read_clock()


# What a process that plays callers leaves to a gateway (`service.caller_jobs.settle`), handed in: this
# module is what the service's own modules import.
@loop("callers-settled", every_s=SETTLED_EVERY_S)
async def settle_callers(settle: Callable[[], Awaitable[None]]) -> None:
    """One pass: the calls whose caller broke before they began are ended, and what a process left is taken up."""
    await settle()
