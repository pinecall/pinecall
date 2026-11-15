"""What the ears are told: the counts that stop the agent, what the ears make up, the agent heard back, the keyterms."""

import time
from collections import deque
from collections.abc import Callable
from dataclasses import dataclass

from runtime.agents.declaration import Declaration, Turn
from runtime.kit.text import JsonObject, a_mapping, words_of

# livekit counts no words by default; one word is as often a cough or an echo.
MIN_WORDS = 2
# Silence before an interruption is judged false: livekit's 2 s sound like a dropped call.
FALSE_INTERRUPTION_TIMEOUT_S = 1.0

# Whisper's invention: on a fraction of a second of noise it writes one phrase over and over
# ("I'm going to make sure that" forty times, gpu.pinecall.io 2026-10-17). A phrase of three words
# or more said three times running is not a caller, whoever is speaking.
LOOPED_WORDS = 3
LOOPED_TIMES = 3

# The agent's own words heard back: most of a turn's words among what it said in the last
# seconds. A caller who repeats a date back says other words around it.
ECHO_SHARE = 0.7
ECHO_WINDOW_S = 12.0
# The echo of the agent's last words reaches the ears after it stops: the room's queue and the
# network both ways, then the ears' own delay.
ECHO_TAIL_S = 1.5

# Keyterms are names, not sentences: longer text dilutes them. The cap is ours, since the ears'
# vendors either document none or count the terms against the model's budget.
LONGEST_TERM = 40
MOST_WORDS = 4
MOST_TERMS = 50


@dataclass(frozen=True, slots=True)
class TurnPolicy:
    """What the caller must say to take the floor, on a call no model judges their voice on."""

    min_words: int = MIN_WORDS
    false_interruption_s: float = FALSE_INTERRUPTION_TIMEOUT_S
    # How long the caller speaks over the agent before it stops; None leaves livekit's own.
    min_speech_s: float | None = None


def loops(text: str) -> bool:
    """Whether a phrase of LOOPED_WORDS words or more comes LOOPED_TIMES times running: the ears looping."""
    words = words_of(text)
    for size in range(LOOPED_WORDS, len(words) // LOOPED_TIMES + 1):
        for start in range(len(words) - size * LOOPED_TIMES + 1):
            phrase = words[start : start + size]
            if all(words[start + size * n : start + size * (n + 1)] == phrase for n in range(1, LOOPED_TIMES)):
                return True
    return False


class AgentWords:
    """What the agent said in the last seconds, to tell its own voice heard back from the caller's."""

    def __init__(self, clock: Callable[[], float] = time.monotonic) -> None:
        """Nothing said yet."""
        self.clock = clock
        self.said: deque[tuple[float, list[str]]] = deque()
        self.stopped_at: float | None = None

    def spoke(self, text: str) -> None:
        """A piece of the agent's reply, as it played."""
        now = self.clock()
        self.said.append((now, words_of(text)))
        while self.said and now - self.said[0][0] > ECHO_WINDOW_S:
            self.said.popleft()

    def stop(self) -> None:
        """The agent's voice stopped: its echo may still be on its way."""
        self.stopped_at = self.clock()

    def just_stopped(self) -> bool:
        """Whether the agent stopped speaking so lately its echo may still come."""
        return self.stopped_at is not None and self.clock() - self.stopped_at <= ECHO_TAIL_S

    def echoes(self, text: str) -> bool:
        """Whether most of the turn's words are the agent's own of the last seconds."""
        heard = words_of(text)
        now = self.clock()
        recent = {word for at, words in self.said if now - at <= ECHO_WINDOW_S for word in words}
        return bool(heard) and sum(word in recent for word in heard) / len(heard) >= ECHO_SHARE


# Until 2026-11-15 it also held a list of words per language that only agree ("ok", "vale", "mhm"),
# and a turn made of them over the agent was dropped by its text. Words written by hand are not what
# heard the caller: with a model on the call its word on the audio decides (taking_the_floor.py), and
# without one the counts here do.
def policy_for(turn: Turn | None = None) -> TurnPolicy:
    """The policy of what the agent says about turns, livekit's counts where it says nothing."""
    said = turn or Turn()
    return TurnPolicy(
        min_words=MIN_WORDS if said.min_interruption_words is None else said.min_interruption_words,
        min_speech_s=None if said.min_interruption_ms is None else said.min_interruption_ms / 1000,
    )


# The agent's own words first, so the cap drops the names found in the state before them. One
# level deep catches `patient = {name, phone}`; a term needs a letter, which leaves out numbers.
def keyterms(declaration: Declaration, state: JsonObject) -> list[str]:
    """The words the ears are told to expect: the agent's own, then names the state holds."""
    found: list[object] = []
    for value in state.values():
        found += list(value.values()) if a_mapping(value) else [value]
    names = [name for name in (_a_name(item) for item in found) if name]
    return list(dict.fromkeys(term for term in (*declaration.hears, *names) if term))[:MOST_TERMS]


def _a_name(value: object) -> str:
    if not isinstance(value, str):
        return ""
    name = value.strip()
    if not name or len(name) > LONGEST_TERM or len(name.split()) > MOST_WORDS:
        return ""
    return name if any(character.isalpha() for character in name) else ""
