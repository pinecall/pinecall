"""Whether a simulated call measured its agent: one our side, its caller or a vendor broke counts in no table."""

from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from typing import Any, Literal

from runtime.wire.base import Entry

# Whose fault a call that measures nothing of its agent is.
type Fault = Literal["caller", "platform", "vendor"]

# What a vendor writes on a call's log: one of its stages refused or failed (`session.listener`).
OF_A_VENDOR = frozenset({"component_failed", "component_dead_end"})
# What our side writes: no worker served the call, or its caller broke before it began (`live.serving`);
# its worker went away mid-call (`live.stranded`); its session broke (`jobs.job`); the app that held its
# agent stopped or was killed (`live.socket`).
OF_OURS = frozenset({"never_served", "worker_lost", "session_failed", "stopped", "killed"})
# How often a simulated caller's voice may break inside its own lines before the call is no caller's
# voice: silences of 20 ms or more it put in its speech by being late with a frame (`leg.Pace`), a
# minute of its lines. Calibrated on recordings: on 2026-11-25 the calls placed five at a time had 0
# to 6 such silences a minute of the caller's speech, twenty at once on the callers service 0 to 5.9,
# and nineteen on one gateway's loop 36 to 137, whose table was thrown away. Over ten, the agent heard
# a broken voice and its answers say nothing of it.
BREAKS_A_MINUTE_AT_MOST = 10.0
# Under this much of the caller's lines measured, a count of breaks says nothing either way.
MEASURED_AT_LEAST_S = 10.0
FRAME_S = 0.01


@dataclass(frozen=True, slots=True)
class Invalid:
    """Why a call is no row of a table: whose fault, in a sentence a person reads."""

    kind: Fault
    why: str


@dataclass(frozen=True, slots=True)
class Validity:
    """Whether a simulated call measured its agent, and, when not, why."""

    invalid: Invalid | None = None

    @property
    def valid(self) -> bool:
        """Whether the call counts: it is what it claims to be, a caller on a clean line and an agent that answered."""
        return self.invalid is None


VALID = Validity()


# A model that is wrong, slow or silent is the eval: its call is valid. What is not is a call in which
# something other than the agent's model spoke for it, or kept it from speaking: a vendor that refused
# or failed one of its stages, our side losing the call, or a caller whose own line broke. The first
# found is the reason, a vendor's first: it is the plainest.
def judge(errors: Iterable[Entry], end_reason: str | None, line: Mapping[str, Any] | None) -> Validity:
    """Whether a simulated call measured its agent, from its log's errors, how it ended and its caller's line."""
    said = [(str(entry.data.get("code") or ""), _sentence(entry)) for entry in errors if entry.type == "error"]
    for code, sentence in said:
        if code in OF_A_VENDOR:
            return Validity(Invalid("vendor", f"a vendor of the agent failed the call: {sentence}"))
    for code, sentence in said:
        if code in OF_OURS:
            return Validity(Invalid("platform", sentence))
    broke = None if line is None else line.get("broke")
    if broke:
        return Validity(Invalid("caller", f"the simulated caller broke on the line: {broke}"))
    breaks = breaks_a_minute(line)
    if breaks is not None and breaks > BREAKS_A_MINUTE_AT_MOST:
        why = (
            f"the simulated caller's voice broke up: {breaks:.0f} silences a minute inside its own lines "
            f"(over {BREAKS_A_MINUTE_AT_MOST:g}, the agent did not hear a caller's voice)"
        )
        return Validity(Invalid("caller", why))
    if end_reason == "error":
        return Validity(Invalid("platform", "the call ended in an error its log gives no reason for"))
    return VALID


def breaks_a_minute(line: Mapping[str, Any] | None) -> float | None:
    """The silences a caller's voice broke into, a minute of its lines; None for a line not measured so."""
    if line is None or "breaks_in_speech" not in line:
        return None
    spoken_s = float(line.get("speech_frames") or 0) * FRAME_S
    if spoken_s < MEASURED_AT_LEAST_S:
        return None
    return float(line["breaks_in_speech"]) / spoken_s * 60


# An error's message is its reason as a person reads it, then a component's own account on the lines under.
def _sentence(entry: Entry) -> str:
    return str(entry.data.get("message") or "").partition("\n")[0] or "no reason given"
