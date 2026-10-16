"""What a log says of its speed: each measure's samples and medians, barge-ins, the phone legs."""

from collections.abc import Iterable, Mapping
from dataclasses import dataclass, replace
from statistics import median

from pinecall_runtime.providers.service import prices
from pinecall_runtime.wire.base import Entry
from pinecall_runtime.wire.room import ParticipantJoined, ParticipantLeft
from pinecall_runtime.wire.state import AgentTurn, Turn, UserTurn

# livekit's names, in the order they happen within a turn (e2e_latency as the session writes it:
# the caller's wait to the reply's first sound), then ours: talk share is the agent's part of the
# time anybody spoke, one per call, a fraction and no seconds.
MEASURES = ("transcription_delay", "end_of_turn_delay", "llm_node_ttft", "tts_node_ttfb", "e2e_latency", "talk_share")

# livekit-sip's attributes on a participant that is a phone leg.
SIP_CALL = "sip.callID"
# Only a leg that came in through a dispatch rule carries one.
SIP_RULE = "sip.ruleID"
TWILIO_CALL = "sip.twilio.callSid"
OWN_NUMBER = "sip.trunkPhoneNumber"
FAR_NUMBER = "sip.phoneNumber"


@dataclass(frozen=True, slots=True)
class Median:
    """A measure's median over one call, and how many turns reported it."""

    name: str
    seconds: float
    turns: int


# One call's turns: a speaker's time is what each of its turns says it spoke, from starting to
# stopping.
def samples(turns: Iterable[Turn]) -> dict[str, list[float]]:
    """Each measure's values in turn order; a measure nobody took is left out."""
    found: dict[str, list[float]] = {name: [] for name in MEASURES}
    spoke = {"user": 0.0, "agent": 0.0}
    for turn in turns:
        for name, value in _measured(turn):
            if value is not None:
                found[name].append(value)
        spoke[turn.role] += _spoken_s(turn)
    if spoke["agent"] + spoke["user"] > 0:
        found["talk_share"].append(spoke["agent"] / (spoke["agent"] + spoke["user"]))
    return {name: values for name, values in found.items() if values}


# The median, not the mean: one interrupted turn would move an average. Each call is measured
# on its own, so no reply is paired with the caller of another call.
def medians(calls: Iterable[Iterable[Turn]]) -> list[Median]:
    """One Median per measure some call reported, pooled over the calls."""
    pooled: dict[str, list[float]] = {name: [] for name in MEASURES}
    for turns in calls:
        for name, values in samples(turns).items():
            pooled[name] += values
    return [Median(name=name, seconds=median(values), turns=len(values)) for name, values in pooled.items() if values]


# How long a barge-in takes to be obeyed: from the caller starting to speak over the agent to the
# agent leaving `speaking`, on each reply written as interrupted. livekit writes the reply and the
# state change in either order, so each waits for the other.
def interruption_delays(entries: Iterable[Entry]) -> list[float]:
    """Seconds from the caller cutting in to the agent falling quiet, per interrupted reply."""
    delays: list[float] = []
    speaking = False
    cut_in: float | None = None
    quiet_after: float | None = None
    interrupted = False
    for entry in entries:
        match entry.type:
            case "user.state" if entry.data.get("state") == "speaking":
                if speaking and cut_in is None:
                    cut_in = entry.ts
            case "turn.agent":
                interrupted = entry.data.get("interrupted") is True
            case "agent.state":
                now_speaking = entry.data.get("state") == "speaking"
                if speaking and not now_speaking and cut_in is not None:
                    quiet_after = entry.ts - cut_in
                if now_speaking and not speaking:
                    cut_in, quiet_after, interrupted = None, None, False
                speaking = now_speaking
            case _:
                continue
        if interrupted and quiet_after is not None:
            delays.append(quiet_after)
            cut_in, quiet_after, interrupted = None, None, False
    return delays


# A leg still up when the log ends is up until the call's last entry.
def phone_legs(entries: Iterable[Entry]) -> list[prices.PhoneLeg]:
    """Each leg of the call on the phone network, from when it joined the room until it left."""
    joined: dict[str, tuple[float, prices.PhoneLeg]] = {}
    legs: list[prices.PhoneLeg] = []
    last = 0.0
    for entry in entries:
        last = entry.ts
        if entry.type == "participant.joined":
            arrived = ParticipantJoined.model_validate(entry.data)
            leg = _leg_of(arrived.attributes)
            if leg is not None:
                joined[arrived.identity] = (entry.ts, leg)
        elif entry.type == "participant.left":
            gone = ParticipantLeft.model_validate(entry.data)
            if gone.identity in joined:
                began, leg = joined.pop(gone.identity)
                legs.append(replace(leg, seconds=entry.ts - began))
    legs += [replace(leg, seconds=last - began) for began, leg in joined.values()]
    return legs


def _measured(turn: Turn) -> tuple[tuple[str, float | None], ...]:
    match turn:
        case UserTurn():
            heard = turn.metrics
            return (("transcription_delay", heard.transcription_delay), ("end_of_turn_delay", heard.end_of_turn_delay))
        case AgentTurn():
            said = turn.metrics
            return (
                ("llm_node_ttft", said.llm_node_ttft),
                ("tts_node_ttfb", said.tts_node_ttfb),
                ("e2e_latency", said.e2e_latency),
            )


def _spoken_s(turn: Turn) -> float:
    started, stopped = turn.metrics.started_speaking_at, turn.metrics.stopped_speaking_at
    if started is None or stopped is None or stopped < started:
        return 0.0
    return stopped - started


def _leg_of(attributes: Mapping[str, object]) -> prices.PhoneLeg | None:
    if SIP_CALL not in attributes:
        return None
    inbound = SIP_RULE in attributes
    number = attributes.get(OWN_NUMBER if inbound else FAR_NUMBER)
    return prices.PhoneLeg(
        carrier="twilio" if TWILIO_CALL in attributes else "sip",
        direction="inbound" if inbound else "outbound",
        number=number if isinstance(number, str) else "",
        seconds=0.0,
    )
