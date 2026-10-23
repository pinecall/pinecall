"""The reaper: it seals the calls nothing runs any more, a dead worker's and a silent chat's."""

import logging

from livekit import api

from pinecall_runtime.calls.repository.heads import HeadRepository, Unsealed
from pinecall_runtime.calls.schemas import SealCallRequest
from pinecall_runtime.calls.service.seal import LEASED_S, sum_up
from pinecall_runtime.calls.service.serving import Serving
from pinecall_runtime.enums import Channel
from pinecall_runtime.exceptions import Conflict
from pinecall_runtime.fleet import service as fleet
from pinecall_runtime.kit.loops import survived
from pinecall_runtime.livekit import Servers
from pinecall_runtime.wire.events import CallEnded
from pinecall_runtime.wire.parts import EndReason
from pinecall_runtime.wire.scores import CallScore

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


# A killed job writes no call.ended, and nothing else would close its log. A call's room is
# asked of its env's LiveKit; a call no scope claimed, of every one.
async def reap(serving: Serving, now: float) -> list[str]:
    """Seal the quiet calls nothing runs any more, and say which."""
    servers = serving.handles.servers
    sealed_now: list[str] = []
    async with serving.handles.sessions() as session:
        heads = HeadRepository(session)
        quiet = await heads.unsealed_spoken(now - QUIET_S, limit=AT_MOST)
        written = await heads.unsealed_written(now - QUIET_S, limit=AT_MOST)
    existing: set[str] = set()
    for server, calls in _rooms_by_livekit(servers, quiet).items():
        existing |= await fleet.rooms_with_an_agent(server, calls)
    for orphan in quiet:
        if orphan.call not in existing and await _tried(serving, orphan, "drained"):
            # The room goes too, so whoever is still in it hears the call end.
            with survived("the reaper's closing of the room", orphan.call):
                for server in _livekits_of(servers, orphan):
                    await fleet.close_room(server, orphan.call)
            logger.warning(
                "sealed %s: no agent is in its room and it has said nothing for %.0f s",
                orphan.call,
                now - orphan.last_at,
            )
            sealed_now.append(orphan.call)
    for orphan in written:
        # A written call waits for its caller as long as its channel would.
        patience = A_THREAD_WAITS_S if orphan.channel == Channel.whatsapp else QUIET_S
        # Its session may run on another gateway, which says so: it is that gateway's to end. One
        # that closed here and left the call unsealed (its seal broke) is nobody's to end any more.
        served = serving.live.calls.get(orphan.call)
        runs = served is not None and (served.running is None or not served.running.closed)
        if runs or serving.live.owners.text_elsewhere(orphan.call) or now - orphan.last_at < patience:
            continue
        if await _tried(serving, orphan, "timeout"):
            sealed_now.append(orphan.call)
    return sealed_now


# A process that drained parked its written calls for the next one; none came. The session runs
# here, so it is hung up as a platform would: the seal follows as for any ended call.
def end_parked(serving: Serving, now: float) -> list[str]:
    """End the written calls parked here that no socket took back in PARKED_WAITS_S; which."""
    ended: list[str] = []
    for served in serving.live.parked_past(now, PARKED_WAITS_S):
        if served.running is None:
            continue
        with survived("the reaper's ending of a parked call", served.call):
            served.running.hang_up("app_detached", "platform", at_once=True)
            serving.live.parked_since.pop(served.call, None)
            logger.warning(
                "ended %s: parked by a process that left, and no socket took it in %.0f s", served.call, PARKED_WAITS_S
            )
            ended.append(served.call)
    return ended


# A call sealed on another gateway ends its readers there; here it is only let go of, so it no
# longer counts against its org's calls at once, and idle calls first seen here go with it. A call
# whose head is gone was erased, which only a sealed call is: it holds no seat either.
async def let_go(serving: Serving, now: float) -> list[str]:
    """Stop serving the calls sealed or erased elsewhere, and the ones first seen here that went idle."""
    serving.live.let_idle_go(now)
    served = list(serving.live.calls)
    async with serving.handles.sessions() as session:
        heads = await HeadRepository(session).among(served)
    gone = [call for call in served if call not in heads or heads[call].sealed]
    for call in gone:
        serving.logs.forget(call)
        serving.live.close_call(call)
    return sorted(gone)


def _rooms_by_livekit(servers: Servers, quiet: list[Unsealed]) -> dict[api.LiveKitAPI, list[str]]:
    by_livekit: dict[api.LiveKitAPI, list[str]] = {}
    for orphan in quiet:
        for server in _livekits_of(servers, orphan):
            by_livekit.setdefault(server, []).append(orphan.call)
    return by_livekit


# Both envs hold the one client when they share a LiveKit: it is asked once.
def _livekits_of(servers: Servers, orphan: Unsealed) -> list[api.LiveKitAPI]:
    if orphan.env is not None:
        return [servers[orphan.env]]
    return list(dict.fromkeys(servers.values()))


# Duration ends at the last entry, not now: reaping late bills no extra minutes. A call that never
# started lasted nothing: measured from no start, it was billed every second since 1970 (2026-10-23).
def lasted(orphan: Unsealed) -> float:
    """How long the reaped call lasted, in seconds: from its start to its last entry, or none."""
    if orphan.started_at is None:
        return 0.0
    return max(orphan.last_at - orphan.started_at, 0.0)


# A call the reaper cannot seal is said and left; the calls behind it are reaped all the same, and
# so is every pass after this one: it must not be the one that stops the reaper.
async def _tried(serving: Serving, orphan: Unsealed, reason: EndReason) -> bool:
    with survived("the reaper's sealing", orphan.call):
        return await _finish(serving, orphan, reason)
    return False


async def _finish(serving: Serving, orphan: Unsealed, reason: EndReason) -> bool:
    store = serving.logs.store
    if not await store.lease_seal(orphan.call, LEASED_S):
        return False
    log = serving.logs.writing(orphan.call, orphan.agent)
    written_types = {item.type for item in await store.whole(orphan.call)}
    try:
        if "call.ended" not in written_types:
            ended = CallEnded(
                reason=reason,
                ended_by="platform",
                ended_at=orphan.last_at,
                duration_s=lasted(orphan),
            )
            await log.append("call.ended", ended.dump())
        if "call.summary" not in written_types:
            async with serving.handles.sessions.begin() as session:
                await sum_up(session, store, log, SealCallRequest(usage=[], outcome=NOTHING_SAID))
        await log.append("call.score", CallScore(judges=[], judge_calls=0, not_judged=NOT_JUDGED_REAPED).dump())
    except Conflict:
        # Another gateway sealed it first: nothing is left to do.
        return False
    finally:
        serving.logs.forget(orphan.call)
    serving.live.close_call(orphan.call)
    return True
