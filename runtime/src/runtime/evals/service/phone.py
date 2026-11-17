"""The phone line: the simulated caller in a room of its own, its leg dialled over SIP into the agent's, the hang-up."""

import asyncio
from typing import override

from livekit.agents.utils import aio
from livekit.protocol.models import ParticipantInfo, TrackType

from runtime.evals.service import turns
from runtime.evals.service.spoken import THE_AGENT_MAY_TAKE_S, SpokenLine
from runtime.kit.retry import until
from runtime.livekit import close_room, participants_in
from runtime.telephony import service as telephony


# A caller on the spoken line sits in the agent's room, on WebRTC, and the agent hears it as a browser
# is heard. A caller on the phone line sits in a room of its own, on the LiveKit the hand-overs are
# dialled from, and that room dials a leg over SIP to the env's own SIP service, in a carrier's codec:
# the agent's room holds a phone leg, the call's channel is the phone, and the caller is heard through
# what a phone call goes through (G.711 at 8 kHz, the SIP service's jitter buffer, a BYE to hang up).
# The leg dials the call's own id, which a rule of the env's SIP seats in the room of that name
# (`telephony.service.simulated_rings`): the gateway named the room and offers it as it offers the
# spoken line's. The env's SIP answers the leg only once somebody in that room hears it, so the leg
# rings while the room is offered, and is answered as the agent's job arrives and finds its caller.
class PhoneLine(SpokenLine):
    """A phone call as its simulated caller is on it: a room of its own, a leg into the agent's, a voice."""

    @override
    async def hang_up(self) -> None:
        """Hear the last answer out, then hang the leg up as a phone does."""
        parts, leg = self._parts, self._on_the_line()
        await turns.wait_for_answer(parts.logs, parts.store, self._spoken.call, self._lines, since=leg.said_at)
        await telephony.hang_up_simulated_caller(parts.servers, self._spoken.call)

    @override
    async def _open(self) -> None:
        parts, call = self._parts, self._spoken.call
        the_fleet = await self._wait_for_a_slot()
        speech = await self._stack.enter_async_context(self._open_voice())
        interferer = await self._make_room_sound(speech)
        self._stack.push_async_callback(close_room, parts.servers[telephony.RINGS_FROM], telephony.callers_room(call))
        self._stack.push_async_callback(close_room, parts.servers[self.env], call)
        self._stack.push_async_exit(self._wait_for_the_end)
        await self._join(telephony.callers_room(call), telephony.RINGS_FROM, speech, interferer)
        ringing = asyncio.ensure_future(telephony.ring_simulated_caller(parts.servers, parts.names, self.env, call))
        self._stack.push_async_callback(aio.cancel_and_wait, ringing)
        await parts.offering.offer(call, the_fleet, self._dispatch)
        await ringing
        await self._wait_for_the_agent()

    # The caller's own room holds its leg alone: the agent is asked for where it sits, in the call's.
    @override
    async def _wait_for_the_agent(self) -> None:
        server, call = self._parts.servers[self.env], self._spoken.call

        async def probe() -> bool | None:
            listens = any(
                participant.kind == ParticipantInfo.Kind.AGENT
                and any(track.type == TrackType.AUDIO for track in participant.tracks)
                for participant in await participants_in(server, call)
            )
            return True if listens else None

        if await until(probe, every_s=turns.A_BEAT_S, within_s=THE_AGENT_MAY_TAKE_S) is None:
            raise TimeoutError(f"no agent joined room {call} in {THE_AGENT_MAY_TAKE_S:.0f}s: is the env's fleet up?")
