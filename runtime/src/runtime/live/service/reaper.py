"""The reaper: it ends the calls nothing runs any more, a dead worker's and a silent chat's, and lets go of the rest."""

import logging
from typing import Protocol

from livekit import api
from sqlalchemy.ext.asyncio import AsyncSession

from runtime.calls import service as calls
from runtime.enums import Channel
from runtime.kit.loops import survive
from runtime.live.parts import LiveParts
from runtime.live.service import seal
from runtime.live.service.ending import End, Sealing
from runtime.livekit import Servers, close_room, rooms_with_an_agent
from runtime.wire.parts import EndReason

logger = logging.getLogger(__name__)

NOT_JUDGED_REAPED = (
    "the worker holding this call went away before it could end it, and the platform sealed the "
    "log: there was no session left to judge"
)
NOTHING_SAID = "no reply"

# Well over livekit's empty_timeout (60 s): the empty room is the signal, this is the margin.
QUIET_S = 5 * 60.0
AT_MOST = 100
# How long a WhatsApp thread waits for its contact before it is closed.
A_THREAD_WAITS_S = 2 * 60 * 60.0
# How long a written call parked by a process that left waits for the next one: a reload of
# `pinecall start` is seconds, a release registers within two minutes (hosting), and a caller left
# talking to nobody for longer than that has been let down already.
PARKED_WAITS_S = 120.0


# What a pass asks first. The box's reaper asks it of every org (`calls.list_quiet_spoken`,
# `calls.list_quiet_written`); a pass over fewer calls than the box's is handed what lists them.
class ListQuiet(Protocol):
    """The calls still open that said nothing since a moment, oldest first, at most so many."""

    async def __call__(self, session: AsyncSession, quiet_since: float, *, limit: int) -> list[calls.Unsealed]:
        """The quiet calls."""
        ...


# A killed job writes no call.ended, and nothing else would close its log. A call's room is
# asked of its env's LiveKit; a call no scope claimed, of every one.
async def reap(
    live: LiveParts,
    now: float,
    *,
    spoken: ListQuiet = calls.list_quiet_spoken,
    written: ListQuiet = calls.list_quiet_written,
) -> list[str]:
    """End the quiet calls nothing runs any more, and say which."""
    ended: list[str] = []
    async with live.sessions() as session:
        quiet = await spoken(session, now - QUIET_S, limit=AT_MOST)
        quiet_written = await written(session, now - QUIET_S, limit=AT_MOST)
    existing: set[str] = set()
    for server, named in _rooms_by_livekit(live.servers, quiet).items():
        existing |= await rooms_with_an_agent(server, named)
    for orphan in quiet:
        if orphan.call not in existing and await _try(live, orphan, "drained"):
            # The room goes too, so whoever is still in it hears the call end.
            with survive("the reaper's closing of the room", orphan.call):
                for server in _livekits_of(live.servers, orphan):
                    await close_room(server, orphan.call)
            logger.warning(
                "sealed %s: no agent is in its room and it has said nothing for %.0f s",
                orphan.call,
                now - orphan.last_at,
            )
            ended.append(orphan.call)
    for orphan in quiet_written:
        # A written call waits for its caller as long as its channel would.
        patience = A_THREAD_WAITS_S if orphan.channel == Channel.whatsapp else QUIET_S
        # Its session may run on another gateway, which says so: it is that gateway's to end. One
        # that closed here and left the call unsealed (its seal broke) is nobody's to end any more.
        served = live.calls.find(orphan.call)
        runs = served is not None and (served.running is None or not served.running.closed)
        if runs or live.owners.runs_elsewhere(orphan.call) or now - orphan.last_at < patience:
            continue
        if await _try(live, orphan, "timeout"):
            ended.append(orphan.call)
    return ended


# A process that drained parked its written calls for the next one; none came. The session runs
# here, so it is hung up as a platform would: the seal follows as for any ended call.
def end_parked(live: LiveParts, now: float) -> list[str]:
    """End the written calls parked here that no socket took back in PARKED_WAITS_S; which."""
    ended: list[str] = []
    for served in live.calls.list_parked_past(now, PARKED_WAITS_S):
        if served.running is None:
            continue
        with survive("the reaper's ending of a parked call", served.call):
            served.running.hang_up("app_detached", "platform", at_once=True)
            live.calls.forget_parked(served.call)
            logger.warning(
                "ended %s: parked by a process that left, and no socket took it in %.0f s", served.call, PARKED_WAITS_S
            )
            ended.append(served.call)
    return ended


# A call sealed on another gateway ends its readers there; here it is only let go of, so it no
# longer counts against its org's calls at once, and idle calls first seen here go with it. A call
# whose head is gone was erased, which only a sealed call is: it counts against nobody either. A call this
# gateway is sealing is its seal's to let go, after the bookkeeping that follows the score: let go
# here, an app's line arriving meanwhile would find no call and be lost without a word.
async def let_go(live: LiveParts, now: float) -> list[str]:
    """Stop serving the calls sealed or erased elsewhere, and the ones first seen here that went idle."""
    live.calls.let_idle_go(now)
    served = [held.call for held in live.calls.list_served() if not held.sealing.locked()]
    async with live.sessions() as session:
        still_open = await calls.list_open(session, served)
    gone = [call for call in served if call not in still_open]
    for call in gone:
        live.logs.forget(call)
        live.calls.close_call(call)
    return sorted(gone)


# Duration ends at the last entry, not now: reaping late bills no extra minutes. A call that never
# started lasted nothing: measured from no start, it was billed every second since 1970 (2026-10-23).
def duration_of(orphan: calls.Unsealed) -> float:
    """How long the reaped call lasted, in seconds: from its start to its last entry, or none."""
    if orphan.started_at is None:
        return 0.0
    return max(orphan.last_at - orphan.started_at, 0.0)


# ── private ──


def _rooms_by_livekit(servers: Servers, quiet: list[calls.Unsealed]) -> dict[api.LiveKitAPI, list[str]]:
    by_livekit: dict[api.LiveKitAPI, list[str]] = {}
    for orphan in quiet:
        for server in _livekits_of(servers, orphan):
            by_livekit.setdefault(server, []).append(orphan.call)
    return by_livekit


# Both envs hold the one client when they share a LiveKit: it is asked once.
def _livekits_of(servers: Servers, orphan: calls.Unsealed) -> list[api.LiveKitAPI]:
    if orphan.env is not None:
        return [servers[orphan.env]]
    return list(dict.fromkeys(servers.values()))


# A call the reaper cannot end is said and left; the calls behind it are reaped all the same, and
# so is every pass after this one: it must not be the one that stops the reaper. Ended by the one
# end every call has (`seal.end_unserved`): its day's drift counts it, as it counts any other.
async def _try(live: LiveParts, orphan: calls.Unsealed, reason: EndReason) -> bool:
    end = End(reason=reason, ended_at=orphan.last_at, duration_s=duration_of(orphan), not_judged=NOT_JUDGED_REAPED)
    with survive("the reaper's sealing", orphan.call):
        return await seal.end_unserved(live, orphan.call, orphan.agent, Sealing(outcome=NOTHING_SAID, end=end))
    return False
