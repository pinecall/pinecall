"""`CallWorld`: the live call an agent serves — its line, its room, its turns, and its verbs."""

import asyncio
import itertools
from collections.abc import Awaitable, Callable
from dataclasses import dataclass

from pinecall import _answers
from pinecall._answers import Answer, Attended, Transferred, Waiting
from pinecall._calls import interruptible
from pinecall._room import History, Participant, Room, Seat, Turn
from pinecall.client import Found
from pinecall.errors import PinecallError
from pinecall.wire._names import Channel, JsonObject, Medium
from pinecall.wire.commands import (
    AgentReply,
    AgentSay,
    CallAttention,
    CallCallback,
    CallClaim,
    CallDtmf,
    CallHangup,
    CallHold,
    CallOptOut,
    CallTransfer,
    CallUnhold,
    RoomSend,
)
from pinecall.wire.events_call import AttentionAnswered, CallClaimed, CallEnded, CallTransferred
from pinecall.wire.events_turn import AgentTurnEnded, UserTurnEnded
from pinecall.wire.frames import WireModel
from pinecall.wire.parts import TransferMode
from pinecall.wire.room import ParticipantJoined, ParticipantLeft, ParticipantSpeaking

# How long `say` and `reply` wait for the turn they asked for.
SPOKEN_WITHIN_S = 30.0
# The far end may ring for 25 s before the transfer fails.
TRANSFERRED_WITHIN_S = 90.0
# How much longer than its own wait an ask for a person waits for the entry that answers it.
A_MOMENT_S = 15.0

NO_GATEWAY_TO_SEARCH = "this call cannot search: no gateway is serving it"

# A search the gateway runs for this call.
Searching = Callable[[str, int | None], Awaitable[list[Found]]]

# How the call sends a command: its type and its data.
Send = Callable[[str, WireModel], None]


@dataclass(frozen=True)
class Line:
    """The call as the prompt reads it: its channel, its medium, the page's code it claimed.

    With no call at all (`pinecall prompt`), a phone call's.
    """

    channel: Channel = "phone"
    medium: Medium | None = None
    claimed: str | None = None


@dataclass(frozen=True)
class CallLine:
    """What a call is when it opens: its id, who is on it, by which channel, on which day."""

    id: str
    contact: str = ""
    from_: str | None = None
    channel: Channel = "phone"
    medium: Medium | None = None
    today: str | None = None
    claimed: str | None = None


class CallWorld:
    """The live call an agent instance serves, folded from its entries; each verb one command.

    A verb that waits for the log to say how it went answers with an `Answer`.
    """

    def __init__(
        self,
        line: CallLine,
        send: Send | None = None,
        searching: Searching | None = None,
        loop: asyncio.AbstractEventLoop | None = None,
    ) -> None:
        """A call on `line`; with no `send`, an offline one whose verbs go nowhere."""
        self.id = line.id
        self.contact = line.contact
        self.from_ = line.from_
        self.channel: Channel = line.channel
        self.medium: Medium = line.medium or ("text" if line.channel == "whatsapp" else "voice")
        self.today = line.today
        """The day the call opened, `YYYY-MM-DD`."""
        self.claimed = line.claimed
        """The page's code this call claimed, or None."""
        self._send: Send = send or nowhere
        self._searching = searching
        self._loop = loop
        self.room = Room(self._send)
        self.history = History()
        self.cause: tuple[str, int] | None = None
        """The outside event a hook is running for, so a write in it can name what caused it."""
        self._numbers = itertools.count(1)
        self._speaking: Waiting[bool] = Waiting(loop)
        self._transfers: Waiting[Transferred] = Waiting(loop)
        self._asks: Waiting[Attended] = Waiting(loop)

    def line(self) -> Line:
        """The call as the prompt reads it."""
        return Line(self.channel, self.medium, self.claimed)

    def numbered(self) -> int:
        """The next number of this call's own outside events."""
        return next(self._numbers)

    # ── the verbs ──

    def say(self, text: str, *, allow_interruptions: bool | None = None) -> Answer[bool]:
        """Say this, verbatim, now; answers True once the turn lands, False if it never does."""
        self._send(
            "agent.say",
            AgentSay.model_validate({"text": text} | interruptible(allow=allow_interruptions)),
        )
        return self._speaking.answer(SPOKEN_WITHIN_S, False)  # noqa: FBT003 - what a turn that never landed answers

    def reply(self, instructions: str, *, allow_interruptions: bool | None = None) -> Answer[bool]:
        """Make the model speak now, following words the caller never hears; answers as `say`."""
        asked = {"instructions": instructions} | interruptible(allow=allow_interruptions)
        self._send("agent.reply", AgentReply.model_validate(asked))
        return self._speaking.answer(SPOKEN_WITHIN_S, False)  # noqa: FBT003 - what a turn that never landed answers

    def send(self, topic: str, data: JsonObject, *, to: str | None = None) -> None:
        """Send a payload to the browsers in the room; the log keeps its size, not its content."""
        self._send(
            "room.send", RoomSend.model_validate({"topic": topic, "data": data} | given(to=to))
        )

    def search(self, query: str, *, k: int | None = None) -> Answer[list[Found]]:
        """Search the bases attached to the agent; the gateway runs it for this call and logs it."""
        searching = self._searching
        if searching is None:
            raise PinecallError(NO_GATEWAY_TO_SEARCH)
        return Answer(_answers.scheduled(self._loop, lambda: searching(query, k)))

    def participant(self, identity: str) -> Seat:
        """One participant's verbs: `call.participant(identity).mute()`."""
        return Seat(identity, self._send)

    def invite(self, to: str, kind: str = "sip") -> None:
        """Bring a number in as a phone leg (`sip`), or an identity as a participant."""
        self.room.invite(to, kind)

    def transfer(self, to: str, *, mode: TransferMode | None = None) -> Answer[Transferred]:
        """Send the caller to a number: answers how it went; `ok=False`, they are still here."""
        self._send("call.transfer", CallTransfer.model_validate({"to": to} | given(mode=mode)))
        lapsed = Transferred(to, None, ok=False, error=_answers.NO_ANSWER)
        return self._transfers.answer(TRANSFERRED_WITHIN_S, lapsed)

    def attention(self, reason: str, *, wait_s: float) -> Answer[Attended]:
        """Ask for a person; the caller waits until one takes the line or `wait_s` passes."""
        self._send("call.attention", CallAttention(reason=reason, wait_s=wait_s))
        return self._asks.answer(
            wait_s + A_MOMENT_S, Attended(ok=False, by=None, error=_answers.NO_ANSWER)
        )

    def hold(self) -> None:
        """Put the caller on hold: they hear hold music, the agent neither speaks nor listens."""
        self._send("call.hold", CallHold())

    def unhold(self) -> None:
        """Take the caller off hold."""
        self._send("call.unhold", CallUnhold())

    def dtmf(self, digits: str) -> None:
        """Send tones: `0-9`, `*`, `#`, and `,` for a pause."""
        self._send("call.dtmf", CallDtmf(digits=digits))

    def claim(self, code: str) -> None:
        """Bind the call to the page showing this four-digit code."""
        self._send("call.claim", CallClaim(code=code))

    def callback(self, number: str, *, when: str | None = None, note: str | None = None) -> None:
        """Leave a request in the log for your backend to call this number back."""
        self._send(
            "call.callback",
            CallCallback.model_validate({"number": number} | given(when=when, note=note)),
        )

    def opt_out(self, note: str | None = None) -> None:
        """The caller asked never to be called again: their number joins the do-not-call list."""
        self._send("call.opt_out", CallOptOut.model_validate(given(note=note)))

    def hangup(self, reason: str | None = None) -> None:
        """End the call; say goodbye first, nothing after it is heard."""
        self._send("call.hangup", CallHangup.model_validate(given(reason=reason)))

    # ── what the entries teach it ──

    def take(self, event: WireModel, at: float) -> None:
        """Fold one of the call's entries into the room, the turns, and the verbs still waiting."""
        if isinstance(event, ParticipantJoined):
            self.room.joined(Participant(event.identity, event.kind, event.name, at))
        elif isinstance(event, ParticipantLeft):
            self.room.left(event.identity)
        elif isinstance(event, ParticipantSpeaking):
            self.room.speaking(event.identity, speaking=event.speaking)
        elif isinstance(event, CallClaimed):
            self.claimed = event.code
        elif isinstance(event, UserTurnEnded):
            self.history.took(Turn("user", event.text, event.speech_id, interrupted=False, at=at))
        elif isinstance(event, AgentTurnEnded):
            self.history.took(Turn("agent", event.text, event.speech_id, event.interrupted, at))
            self._speaking.settle(True)  # noqa: FBT003 - the turn landed
        elif isinstance(event, CallTransferred):
            self._transfers.settle(Transferred(event.to, event.mode, event.ok, event.error))
        elif isinstance(event, AttentionAnswered):
            self._asks.settle(Attended(event.ok, event.by, event.error))
        elif isinstance(event, CallEnded):
            # Every verb still waiting is answered now rather than at its ceiling.
            self._speaking.settle(False)  # noqa: FBT003 - the call ended first
            self._transfers.settle(Transferred("", None, ok=False, error=_answers.THE_CALL_ENDED))
            self._asks.settle(Attended(ok=False, by=None, error=_answers.THE_CALL_ENDED))


def nowhere(*_: object) -> None:
    """Where an offline call's commands go."""


def given(**fields: object) -> dict[str, object]:
    """The fields that were given: a field left out stays absent on the wire."""
    return {name: value for name, value in fields.items() if value is not None}
