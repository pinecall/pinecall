"""Who is in the call's room, a seat's two verbs, and the turns the call has had."""

from collections.abc import Callable
from dataclasses import dataclass, field

from pinecall.wire.commands import ParticipantMute, ParticipantRemove, RoomInvite
from pinecall.wire.frames import WireModel
from pinecall.wire.parts import ParticipantKind

# How the call sends a command: its type and its data.
Send = Callable[[str, WireModel], None]


@dataclass
class Participant:
    """One participant in the room."""

    identity: str
    kind: ParticipantKind
    name: str | None
    joined_at: float
    speaking: bool = False


class Seat:
    """One participant's two verbs: `call.participant(identity).mute()`."""

    def __init__(self, identity: str, send: Send) -> None:
        """The seat of `identity`."""
        self.identity = identity
        self._send = send

    def mute(self) -> None:
        """Mute them for the rest of the call; there is no unmute, invite the leg again."""
        self._send("participant.mute", ParticipantMute(identity=self.identity))

    def remove(self) -> None:
        """Take them out of the room; removing the caller ends the call."""
        self._send("participant.remove", ParticipantRemove(identity=self.identity))


class Room:
    """Who is in the room now, folded from its entries; reading is local, the verbs are commands."""

    def __init__(self, send: Send) -> None:
        """A room that sends through `send`."""
        self._send = send
        self._seats: dict[str, Participant] = {}

    @property
    def participants(self) -> list[Participant]:
        """Everyone in the room, in the order they joined."""
        return list(self._seats.values())

    @property
    def caller(self) -> Participant | None:
        """The caller, once they joined."""
        return next((one for one in self._seats.values() if one.kind == "caller"), None)

    def has(self, kind: ParticipantKind) -> bool:
        """Whether somebody of this kind is in the room: `has("supervisor")`."""
        return any(one.kind == kind for one in self._seats.values())

    def get(self, identity: str) -> Participant | None:
        """A participant by identity."""
        return self._seats.get(identity)

    def invite(self, to: str, kind: str = "sip") -> None:
        """Bring a number in as a phone leg (`sip`), or an identity as a participant."""
        self._send("room.invite", RoomInvite.model_validate({"to": to, "kind": kind}))

    def joined(self, participant: Participant) -> None:
        """Somebody joined; the same identity again replaces them."""
        self._seats[participant.identity] = participant

    def left(self, identity: str) -> None:
        """Somebody left."""
        self._seats.pop(identity, None)

    def speaking(self, identity: str, *, speaking: bool) -> None:
        """Whether somebody is speaking now."""
        seat = self._seats.get(identity)
        if seat is not None:
            seat.speaking = speaking


@dataclass(frozen=True)
class Turn:
    """One finished turn: who, what, its speech, whether the caller cut it off, and when."""

    who: str
    text: str
    speech_id: str
    interrupted: bool
    at: float


@dataclass
class History:
    """The call's finished turns, oldest first; a turn still being spoken is not one yet."""

    turns: list[Turn] = field(default_factory=list[Turn])

    @property
    def last(self) -> Turn | None:
        """The most recent turn."""
        return self.turns[-1] if self.turns else None

    def took(self, turn: Turn) -> None:
        """Keep a finished turn."""
        self.turns.append(turn)
