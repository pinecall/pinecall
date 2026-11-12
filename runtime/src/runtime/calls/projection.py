"""What each audience reads of an entry and of the state: the tenant with the private masked, the public by field."""

from collections.abc import Awaitable, Callable, Mapping
from dataclasses import dataclass

from runtime.agents.declaration import Declaration
from runtime.calls.log.private import mask_state, split
from runtime.exceptions import ValidationError
from runtime.kit.text import Json, JsonObject
from runtime.wire.base import Entry, WireModel
from runtime.wire.events import AgentTurnEnded, LogGap, StateChanged, event_of
from runtime.wire.parts import Projection
from runtime.wire.state import AgentTurn, State, Turn

# How many entries a stream asks at for a declaration it began without, before it reads on with none.
LATE_TRIES = 8

NEEDS_READING = frozenset({"turn.agent", "state.changed", "log.gap"})

# The contract's table (docs/protocol/projections.md), row by row: a type absent is dropped
# whole, a field absent is dropped.
PUBLIC_ENTRY_FIELDS: Mapping[str, tuple[str, ...]] = {
    "call.ringing": ("channel",),
    "call.dialing": ("channel",),
    "call.started": ("channel", "direction", "started_at"),
    "call.ended": ("reason", "ended_by", "ended_at", "duration_s"),
    "user.state": ("state",),
    "agent.state": ("state",),
    "user.transcript": ("text", "final"),
    "agent.transcript": ("speech_id", "text", "final", "start"),
    "agent.waiting": ("speech_id", "interrupted"),
    "turn.user": ("speech_id", "text"),
    "turn.agent": ("speech_id", "text", "interrupted", "metrics"),
    "room.opened": ("name", "sid"),
    "participant.joined": ("identity", "kind", "name"),
    "participant.left": ("identity",),
    "participant.speaking": ("identity", "speaking"),
    "confirm.request": ("phrase", "ttl_s"),
    "confirm.granted": (),
    "confirm.declined": (),
    "call.transferred": ("to", "mode", "ok", "error"),
    "call.line": ("held",),
    "event.received": ("name", "data", "source", "identity"),
    "state.changed": ("state", "changed"),
    "log.gap": ("from_seq", "to_seq", "snapshot"),
    "log.caught_up": ("seq",),
}

# agent and call are left out so a participant learns nothing of the tenant's setup.
PUBLIC_ENVELOPE = ("seq", "ts", "type", "ephemeral")
PUBLIC_TURN = frozenset({"role", "speech_id", "text", "interrupted"})
PUBLIC_PARTICIPANT = frozenset({"identity", "kind", "name", "joined_at", "speaking"})
PUBLIC_CONFIRM = frozenset({"phrase", "status"})


# A key reads what is the tenant's, the private values masked; a visitor's token reads the public
# projection, and of the events a participant sent only its own. Until 2026-11 the two travelled
# apart through every function, the second read by one of the two bodies alone.
@dataclass(frozen=True, slots=True)
class Audience:
    """Who reads: the tenant, or the public, which is a participant of the call by its identity."""

    projection: Projection = "tenant"
    # The identity of the participant reading; None for the tenant, and for a page that is no participant.
    viewer: str | None = None


TENANT = Audience()


# A page follows its call from the mint, before the call has opened and declared anything: what is
# public of it is read once it has, never decided for the whole stream while nothing is declared.
@dataclass(slots=True)
class Declaring:
    """The declaration a stream projects by: the one it began with, else its call's own once it opened."""

    declaration: Declaration | None
    late: Callable[[], Awaitable[Declaration | None]] | None = None
    tries: int = LATE_TRIES

    async def now(self) -> Declaration | None:
        """The declaration to project the next entry by, asked for again while there is none."""
        if self.declaration is None and self.late is not None and self.tries > 0:
            self.tries -= 1
            self.declaration = await self.late()
        return self.declaration


def project_state(state: State, audience: Audience, declaration: Declaration | None) -> JsonObject:
    """The reduced state as this audience may read it."""
    match audience.projection:
        case "tenant":
            app_state = state.app_state if declaration is None else mask_state(state.app_state, declaration)
            return {**state.dump(), "app_state": app_state}
        case "public":
            return _public_state(state, declaration, audience.viewer)


def project_entry(entry: Entry, audience: Audience, declaration: Declaration | None) -> JsonObject | None:
    """The entry as this audience may read it, or None when it must not reach them."""
    match audience.projection:
        case "tenant":
            return {**entry.dump(), "data": _tenant_data(entry, declaration)}
        case "public":
            return _public_entry(entry, declaration, audience.viewer)


def _public_state(state: State, declaration: Declaration | None, viewer: str | None) -> JsonObject:
    written = state.dump()
    room: Json = None
    if state.room is not None:
        present: list[Json] = [_keep(one.dump(), PUBLIC_PARTICIPANT) for one in state.room.participants]
        room = {**state.room.dump(), "participants": present}
    return {
        "seq": state.seq,
        "status": state.status,
        "user_state": written["user_state"],
        "agent_state": written["agent_state"],
        "live": written["live"],
        "turns": [_public_turn(turn) for turn in state.turns],
        "app_state": _only_public(state.app_state, declaration),
        "room": room,
        "confirms": [_keep(confirm.dump(), PUBLIC_CONFIRM) for confirm in state.confirms],
        "transfer": written["transfer"],
        "held": state.held,
        "events": [
            event.dump() for event in state.events if event.source == "participant" and event.identity == viewer
        ],
    }


def _public_entry(entry: Entry, declaration: Declaration | None, viewer: str | None) -> JsonObject | None:
    fields = PUBLIC_ENTRY_FIELDS.get(entry.type)
    if fields is None:
        return None
    data: JsonObject = {name: entry.data[name] for name in fields if name in entry.data}
    if entry.type == "event.received" and not (data.get("source") == "participant" and data.get("identity") == viewer):
        return None
    match _event_of(entry):
        case AgentTurnEnded() as turn:
            data["metrics"] = _public_metrics(turn.metrics.e2e_latency)
        case StateChanged() as changed:
            public = _only_public(changed.state, declaration)
            data = {"state": public, "changed": [name for name in changed.changed if name in public]}
        case LogGap(snapshot=State() as snapshot):
            data["snapshot"] = _public_state(snapshot, declaration, viewer)
        case None if entry.type in NEEDS_READING:
            return None
        case _:
            pass
    envelope = entry.dump()
    return {**{name: envelope[name] for name in PUBLIC_ENVELOPE}, "data": data}


# A log written since private values are masked when written holds them masked already; the
# rows written before are masked here, by the declaration the reader reads with.
def _tenant_data(entry: Entry, declaration: Declaration | None) -> JsonObject:
    gap = _event_of(entry)
    if isinstance(gap, LogGap) and gap.snapshot is not None:
        return {**entry.data, "snapshot": project_state(gap.snapshot, TENANT, declaration)}
    return entry.data if declaration is None else split(entry.type, entry.data, declaration).kept


# Only the entries a projection reaches into are read; an old shape of one is withheld from the
# public, since what it would leak cannot be told, and passed whole to the tenant.
def _event_of(entry: Entry) -> WireModel | None:
    if entry.type not in NEEDS_READING:
        return None
    try:
        return event_of(entry)
    except ValidationError:
        return None


def _public_turn(turn: Turn) -> JsonObject:
    kept = _keep(turn.dump(), PUBLIC_TURN)
    if isinstance(turn, AgentTurn):
        kept["metrics"] = _public_metrics(turn.metrics.e2e_latency)
    return kept


# How long the caller waited is the one number about them; the rest is the tenant's cost and its settings.
def _public_metrics(e2e_latency: float | None) -> JsonObject:
    return {} if e2e_latency is None else {"e2e_latency": e2e_latency}


# Without a declaration every field is the tenant's: nothing is public, nothing is masked.
def _only_public(app_state: JsonObject, declaration: Declaration | None) -> JsonObject:
    if declaration is None:
        return {}
    return {name: value for name, value in app_state.items() if declaration.visibility_of(name) == "public"}


def _keep(written: JsonObject, fields: frozenset[str]) -> dict[str, Json]:
    return {name: value for name, value in written.items() if name in fields}
