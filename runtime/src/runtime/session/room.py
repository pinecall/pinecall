"""A voice call's room: who is in it, the caller's codes, transfers, the room verbs, its facts."""

import asyncio
import contextlib
import json
import logging
import time
from collections import deque
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import assert_never

from livekit import api, rtc
from livekit.agents.voice import AgentSession
from livekit.protocol.room import MuteRoomTrackRequest, RoomParticipantIdentity
from livekit.rtc.participant import PublishDataError, PublishDTMFError

from runtime.enums import Channel
from runtime.exceptions import PinecallError, ValidationError
from runtime.fleet import service as fleet
from runtime.kit.text import JsonObject
from runtime.session.call import Call
from runtime.telephony import service as telephony
from runtime.wire import events as wire
from runtime.wire.commands import (
    CallDtmf,
    CallMute,
    CallTransfer,
    CallUnmute,
    ParticipantMute,
    ParticipantRemove,
    RoomInvite,
    RoomSend,
    name_of,
)
from runtime.wire.parts import ParticipantKind, TrackKind, TrackSource, TransferMode
from runtime.wire.room import (
    SCOPE_ATTRIBUTE,
    ParticipantJoined,
    ParticipantLeft,
    ParticipantSpeaking,
    RoomOpened,
    RoomSent,
    TrackPublished,
    TrackUnpublished,
)

# A code the caller keyed, claimed with the gateway, which decides whether it is one.
type ClaimCode = Callable[[str], Awaitable[None]]
# The verbs of the app's that act on the room. `call.mute` and `call.unmute` are on the wire and have
# no handler: they leave it once the release before 2026-11 is gone (session-7), and until then they
# answer as they always did, with the room's refusal.
type RoomCommand = RoomInvite | RoomSend | ParticipantMute | ParticipantRemove | CallDtmf | CallMute | CallUnmute

logger = logging.getLogger(__name__)

KIND_OF_SCOPE: dict[str, ParticipantKind] = {"supervise": "supervisor", "observe": "listener"}
# livekit's session closes when the caller leaves only for three reasons (they hung up, the room
# was deleted, they were rejected); one whose connection dropped is waited for, and the room ends
# 20 s after its last person left, LiveKit's departure timeout. A supervisor watching keeps the
# room up, so the call is ended here: the caller gone as long as LiveKit waits for a last person.
CALLER_RETURNS_S = 20.0
CALLER_GONE = "call %s: the caller left (%s) and did not come back in %.0f s: the call ends"
# The longest a transfer asked outside a tool waits for the agent to finish its sentence.
THE_ANNOUNCEMENT_S = 12.0
# A code is four digits keyed within eight seconds (docs/protocol/codes.md); answers to a menu
# are slower.
CODE_LENGTH = 4
CODE_WITHIN_S = 8.0


@dataclass(frozen=True, slots=True)
class Waits:
    """How long a room waits: for a caller who dropped, for a visitor who left, for a code's four tones."""

    caller_returns_s: float = CALLER_RETURNS_S
    visitor_returns_s: float = fleet.A_VISITOR_RETURNS_S
    code_within_s: float = CODE_WITHIN_S


# What a room waits when nothing says otherwise.
LIVEKITS_WAITS = Waits()


ROOM_VERB_FAILED = "room_verb_failed"
NOT_DIALLED = "room.invite: a participant joins with a token; the room dials only kind sip"
NOT_IN_THE_ROOM = "participant.mute: {identity} is not in the room"
NO_MICROPHONE = "participant.mute: {identity} has no microphone in the room"
NOT_A_ROOM_VERB = "{verb} is not a verb of a call's room"
TRACK_KINDS: dict[int, TrackKind] = {rtc.TrackKind.KIND_AUDIO: "audio", rtc.TrackKind.KIND_VIDEO: "video"}
TRACK_SOURCES: dict[int, TrackSource] = {
    rtc.TrackSource.SOURCE_MICROPHONE: "microphone",
    rtc.TrackSource.SOURCE_CAMERA: "camera",
    rtc.TrackSource.SOURCE_SCREENSHARE: "screen_share",
    rtc.TrackSource.SOURCE_SCREENSHARE_AUDIO: "screen_share_audio",
}


class CallRoom:
    """One voice call's room, the server's API over it, and what it writes about both."""

    def __init__(
        self,
        call: Call,
        room: rtc.Room,
        server: api.LiveKitAPI,
        *,
        legs: telephony.Legs,
        claim: ClaimCode,
        waits: Waits = LIVEKITS_WAITS,
    ) -> None:
        """The room of a call not yet opened."""
        self.call = call
        self.waits = waits
        self.room = room
        self.server = server
        self.legs = legs
        self.claim = claim
        self.speaking: set[str] = set()
        self.tones: deque[tuple[str, float]] = deque(maxlen=CODE_LENGTH)
        self.claimed: set[str] = set()
        self.tasks: set[asyncio.Task[None]] = set()
        # The person a warm transfer dialled in, and what ends the call when they leave.
        self.bridged: str | None = None
        self.person_gone: Callable[[], None] | None = None
        self.caller_gone: Callable[[], None] | None = None
        self.returning: asyncio.Task[None] | None = None

    async def leg(self) -> rtc.RemoteParticipant | None:
        """The caller's SIP leg, waited for a moment; none on a call that is not a phone's."""
        return await telephony.caller_leg(self.room, self.call.context.channel)

    # ── transfers ──

    async def mode_of(self, wanted: CallTransfer) -> TransferMode:
        """The mode asked for, else cold on a phone leg and warm on a browser's call."""
        if wanted.mode is not None:
            return wanted.mode
        return "cold" if await self.leg() is not None else "warm"

    # A failed transfer is call.transferred with ok false, and the call goes on.
    async def transfer(self, wanted: CallTransfer, live: AgentSession[Call]) -> wire.CallTransferred:
        """Send the caller on (cold, by REFER of their leg) or dial the person in (warm)."""
        mode = await self.mode_of(wanted)
        await _wait_for_the_announcement(live)
        if mode == "cold":
            return await telephony.send_on(self.server, self.room, self.call.context.channel, self.legs, wanted.to)
        return await telephony.dial_in(self.server, self.room.name, self.legs, wanted.to)

    # The person is dialled into this room. The caller leaving closes the session by itself; the
    # person leaving does not, so the call ends then. Their leg is named as telephony names every
    # leg it dials, and heard leaving by the room's own listener: until 2026-11 the session built
    # the name and a listener of its own was left in the room.
    def when_the_person_leaves(self, to: str, hang_up: Callable[[], None]) -> None:
        """Call `hang_up` once the person a warm transfer dialled in leaves the room."""
        self.bridged = f"{telephony.LEG_PREFIX}{to}"
        self.person_gone = hang_up

    def when_the_caller_is_gone(self, hang_up: Callable[[], None]) -> None:
        """Call `hang_up` once the caller left, whatever the reason, and did not come back."""
        self.caller_gone = hang_up

    # ── the other room verbs ──

    async def apply(self, command: RoomCommand) -> None:
        """A room verb of the app's; the server's refusal is an error entry, the call goes on."""
        match command:
            case RoomInvite():
                await self._invite(command)
            case RoomSend():
                await self._send(command)
            case ParticipantMute():
                await self._mute(command)
            case ParticipantRemove():
                request = RoomParticipantIdentity(room=self.room.name, identity=command.identity)
                await self._complete("participant.remove", self.server.room.remove_participant(request))
            case CallDtmf():
                await self._send_tones(command)
            case CallMute() | CallUnmute():
                self._fail(name_of(command), NOT_A_ROOM_VERB.format(verb=name_of(command)))
            case _:
                assert_never(command)

    # Success is written by the room itself, as participant.joined of kind sip.
    async def _invite(self, wanted: RoomInvite) -> None:
        if wanted.kind != "sip":
            self._fail("room.invite", NOT_DIALLED)
            return
        try:
            request = await telephony.leg_to(self.room.name, self.legs, wanted.to)
        except PinecallError as refused:
            self._fail("room.invite", str(refused) or telephony.NO_TRUNK.format(verb="room.invite", to=wanted.to))
            return
        await self._complete("room.invite", self.server.sip.create_sip_participant(request))

    # The payload stays out of the log: room.sent says the topic, whom, and the size.
    async def _send(self, wanted: RoomSend) -> None:
        packed = json.dumps(wanted.data, separators=(",", ":")).encode()
        to = [] if wanted.to is None else [wanted.to]
        sent = self.room.local_participant.publish_data(packed, topic=wanted.topic, destination_identities=to)
        if await self._complete("room.send", sent):
            self.call.writing.write("room.sent", RoomSent(topic=wanted.topic, to=wanted.to, bytes=len(packed)))

    # livekit mutes in place and says nothing, so the verb writes track.unpublished itself.
    async def _mute(self, wanted: ParticipantMute) -> None:
        participant = self.room.remote_participants.get(wanted.identity)
        if participant is None:
            self._fail("participant.mute", NOT_IN_THE_ROOM.format(identity=wanted.identity))
            return
        microphone = next(
            (
                value
                for value in participant.track_publications.values()
                if value.source == rtc.TrackSource.SOURCE_MICROPHONE
            ),
            None,
        )
        if microphone is None:
            self._fail("participant.mute", NO_MICROPHONE.format(identity=wanted.identity))
            return
        request = MuteRoomTrackRequest(
            room=self.room.name, identity=wanted.identity, track_sid=microphone.sid, muted=True
        )
        if await self._complete("participant.mute", self.server.room.mute_published_track(request)):
            unpublished = TrackUnpublished(identity=wanted.identity, kind="audio", source="microphone")
            self.call.writing.write("track.unpublished", unpublished)

    # The whole sequence is refused before a tone goes out: half a card number is worse than none.
    async def _send_tones(self, wanted: CallDtmf) -> None:
        wrong = telephony.find_wrong_tone(wanted.digits)
        if wrong is not None:
            self._fail("call.dtmf", wrong)
            return
        if await self.leg() is None:
            self._fail("call.dtmf", telephony.NO_LEG.format(verb="call.dtmf"))
            return
        await self._complete("call.dtmf", telephony.send_tones(self.room, wanted.digits))

    # The server's own words, as it said them.
    async def _complete(self, verb: str, done: Awaitable[object]) -> bool:
        try:
            await done
        except (api.TwirpError, PublishDataError, PublishDTMFError, ConnectionError) as refused:
            self._fail(verb, str(refused))
            return False
        return True

    def _fail(self, verb: str, why: str) -> None:
        failed = wire.ErrorEvent(code=ROOM_VERB_FAILED, message=why, command=verb, recoverable=True)
        self.call.writing.write("error", failed)

    # ── the room's own facts ──

    # The job usually connects before the session exists, so the connection was already missed.
    def watch(self) -> None:
        """Write what happens in the room, room.opened first."""
        for name, listener in self._listeners().items():
            self.room.on(name, listener)  # pyright: ignore[reportUnknownMemberType]
        if self.room.isconnected():
            self._on_connection_state_changed(rtc.ConnectionState.CONN_CONNECTED)

    def stop(self) -> None:
        """Let go of the room and of every claim still out."""
        for name, listener in self._listeners().items():
            self.room.off(name, listener)  # pyright: ignore[reportUnknownMemberType]
        for task in self.tasks:
            task.cancel()

    # A SIP participant is the caller only if its number is the call's caller; any other was dialled in.
    def kind_of(self, participant: rtc.Participant) -> ParticipantKind:
        """Who a participant of the room is to this call: caller, agent, supervisor or a far end."""
        if participant.kind == rtc.ParticipantKind.PARTICIPANT_KIND_AGENT:
            return "agent"
        attributes = dict(participant.attributes)
        by_scope = KIND_OF_SCOPE.get(attributes.get(SCOPE_ATTRIBUTE, ""))
        if by_scope is not None:
            return by_scope
        if telephony.is_a_phone(attributes) and attributes.get(telephony.CALLER_NUMBER) != self.call.context.caller:
            return "sip"
        return "caller"

    def _listeners(self) -> dict[rtc.room.EventTypes, Callable[..., None]]:
        return {
            "connection_state_changed": self._on_connection_state_changed,
            "participant_connected": self._on_participant_connected,
            "participant_disconnected": self._on_participant_disconnected,
            "track_published": self._on_track_published,
            "track_unpublished": self._on_track_unpublished,
            "active_speakers_changed": self._on_active_speakers_changed,
            "sip_dtmf_received": self._on_sip_dtmf_received,
        }

    def _on_connection_state_changed(self, state: int) -> None:
        if state == rtc.ConnectionState.CONN_CONNECTED:
            self._spawn(self._open())

    # room.sid is awaited, so the opening runs as a task: room.opened, the agent's own participant,
    # then the ones who came before the agent and their tracks.
    async def _open(self) -> None:
        opened = RoomOpened(name=self.room.name, sid=await self.room.sid, channel=self.call.context.channel)
        await self.call.writing.write("room.opened", opened)
        self._on_participant_connected(self.room.local_participant)
        for participant in self.room.remote_participants.values():
            self._on_participant_connected(participant)
            for publication in participant.track_publications.values():
                self._on_track_published(publication, participant)

    def _on_participant_connected(self, participant: rtc.Participant) -> None:
        attributes: JsonObject = dict(participant.attributes)
        joined = ParticipantJoined(
            identity=participant.identity,
            kind=self.kind_of(participant),
            name=participant.name or None,
            attributes=attributes,
        )
        self.call.writing.write("participant.joined", joined)
        if joined.kind == "caller" and self.returning is not None:
            self.returning.cancel()
            self.returning = None

    def _on_participant_disconnected(self, participant: rtc.RemoteParticipant) -> None:
        reason = participant.disconnect_reason
        text = "unknown" if reason is None else rtc.DisconnectReason.Name(reason).lower()
        self.call.writing.write("participant.left", ParticipantLeft(identity=participant.identity, reason=text))
        self.speaking.discard(participant.identity)
        if participant.identity == self.bridged:
            self.bridged = None
            if self.person_gone is not None:
                self.person_gone()
        gone = self.caller_gone
        if gone is not None and self.kind_of(participant) == "caller":
            if self.returning is not None:
                self.returning.cancel()
            self.returning = self._spawn(self._wait_for_the_caller(gone, text))

    # A visitor's call waits for them as long as their room does; their widget's hang-up ends it
    # at once (widget.py), a reload does not.
    async def _wait_for_the_caller(self, hang_up: Callable[[], None], reason: str) -> None:
        waits = (
            self.waits.visitor_returns_s if self.call.context.channel is Channel.web else self.waits.caller_returns_s
        )
        await asyncio.sleep(waits)
        self.returning = None
        logger.info(CALLER_GONE, self.room.name, reason, waits)
        hang_up()

    def _on_track_published(self, publication: rtc.TrackPublication, participant: rtc.Participant) -> None:
        track = _track_of(publication)
        if track is not None:
            self.call.writing.write(
                "track.published", TrackPublished(identity=participant.identity, kind=track[0], source=track[1])
            )

    def _on_track_unpublished(self, publication: rtc.TrackPublication, participant: rtc.Participant) -> None:
        track = _track_of(publication)
        if track is not None:
            self.call.writing.write(
                "track.unpublished", TrackUnpublished(identity=participant.identity, kind=track[0], source=track[1])
            )

    # Written on the change, never on every tick.
    def _on_active_speakers_changed(self, speakers: list[rtc.Participant]) -> None:
        now = {speaker.identity for speaker in speakers}
        for identity in sorted(now - self.speaking):
            self.call.writing.write("participant.speaking", ParticipantSpeaking(identity=identity, speaking=True))
        for identity in sorted(self.speaking - now):
            self.call.writing.write("participant.speaking", ParticipantSpeaking(identity=identity, speaking=False))
        self.speaking = now

    # The caller's tones only: a server's have no participant, another leg is not the caller.
    def _on_sip_dtmf_received(self, tone: rtc.SipDTMF) -> None:
        participant = tone.participant
        if participant is None or self.kind_of(participant) != "caller":
            return
        try:
            pressed = wire.DtmfReceived.parse({"digit": tone.digit, "code": tone.code}, "dtmf.received")
        except ValidationError:
            return
        self.call.writing.write("dtmf.received", pressed)
        self._press(pressed.digit, time.monotonic())

    # The worker cannot tell a code from an extension, so every candidate is claimed and the
    # gateway decides; each code once a call. `*` or `#` starts over.
    def _press(self, digit: str, at: float) -> None:
        if not digit.isdigit():
            self.tones.clear()
            return
        self.tones.append((digit, at))
        if len(self.tones) < CODE_LENGTH or at - self.tones[0][1] > self.waits.code_within_s:
            return
        code = "".join(pressed for pressed, _ in self.tones)
        self.tones.clear()
        if code not in self.claimed:
            self.claimed.add(code)
            self._spawn(self._claim(code))

    async def _claim(self, code: str) -> None:
        try:
            await self.claim(code)
        except Exception:
            logger.warning("call %s: the claim of a keyed code was refused", self.call.context.call, exc_info=True)

    # A task of a synchronous listener is kept, or it may be collected mid-run.
    def _spawn(self, work: Awaitable[None]) -> asyncio.Task[None]:
        task = asyncio.ensure_future(work)
        self.tasks.add(task)
        task.add_done_callback(self.tasks.discard)
        return task


async def _wait_for_the_announcement(live: AgentSession[Call]) -> None:
    speech = live.current_speech
    if speech is not None:
        with contextlib.suppress(TimeoutError):
            await asyncio.wait_for(speech.wait_for_playout(), THE_ANNOUNCEMENT_S)


def _track_of(publication: rtc.TrackPublication) -> tuple[TrackKind, TrackSource] | None:
    kind = TRACK_KINDS.get(publication.kind)
    return None if kind is None else (kind, TRACK_SOURCES.get(publication.source, "unknown"))
