"""What the ears are told: the words that only agree, what the ears make up, the agent heard back, the keyterms."""

import re
import time
from collections import deque
from collections.abc import Callable
from dataclasses import dataclass

from pinecall_runtime.agents.declaration import AgentConfig, Turn
from pinecall_runtime.kit.text import JsonObject, a_mapping

# livekit counts no words by default; one word is as often a cough or an echo.
MIN_WORDS = 2
# Silence before an interruption is judged false: livekit's 2 s sound like a dropped call.
FALSE_INTERRUPTION_TIMEOUT_S = 1.0

# A turn made of these alone is somebody agreeing, and does not take the floor. livekit's own
# backchannel detector is hosted only. Per language: "vale" takes the floor in English.
BACKCHANNELS: dict[str, frozenset[str]] = {
    "es": frozenset(
        {
            "aha",
            "ajá",
            "ah",
            "ajam",
            "bien",
            "bueno",
            "claro",
            "dale",
            "eh",
            "em",
            "exacto",
            "hm",
            "hmm",
            "mm",
            "mmm",
            "ok",
            "okay",
            "perfecto",
            "sí",
            "si",
            "vale",
            "ya",
            "uh",
            "uhu",
            "uhum",
        }
    ),
    "en": frozenset(
        {
            "aha",
            "ah",
            "hm",
            "hmm",
            "mm",
            "mmm",
            "mhm",
            "ok",
            "okay",
            "yeah",
            "yes",
            "yep",
            "right",
            "sure",
            "uh",
            "uh-huh",
            "gotcha",
            "exactly",
        }
    ),
    "pt": frozenset({"aham", "ah", "sim", "tá", "certo", "claro", "ok", "beleza", "hum", "uhum"}),
    "ca": frozenset({"sí", "vale", "d'acord", "clar", "entesos", "ok", "mm", "aha", "eh"}),
}

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

_A_WORD = re.compile(r"[^\W_]+(?:['’-][^\W_]+)*")

# Keyterms are names, not sentences: longer text dilutes them. The cap is ours, since the ears'
# vendors either document none or count the terms against the model's budget.
LONGEST_TERM = 40
MOST_WORDS = 4
MOST_TERMS = 50


@dataclass(frozen=True, slots=True)
class TurnPolicy:
    """What the caller must say to take the floor, in the agent's language."""

    backchannels: frozenset[str]
    min_words: int = MIN_WORDS
    false_interruption_s: float = FALSE_INTERRUPTION_TIMEOUT_S
    # How long the caller speaks over the agent before it stops; None leaves livekit's own.
    min_speech_s: float | None = None

    def is_a_backchannel(self, text: str) -> bool:
        """Whether every word said is somebody agreeing."""
        words = words_of(text)
        return bool(words) and all(word in self.backchannels for word in words)


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

    def stopped(self) -> None:
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


def words_of(text: str) -> list[str]:
    """The words of a text, lowered, its punctuation dropped."""
    return [str(found.group(0)).lower() for found in _A_WORD.finditer(text)]


def policy_for(language: str | None, turn: Turn | None = None) -> TurnPolicy:
    """The policy of the agent's language (`es-ES` is `es`) and its turn knobs; else every list."""
    tag = (language or "").split("-", 1)[0].lower()
    words = BACKCHANNELS.get(tag) or frozenset[str]().union(*BACKCHANNELS.values())
    declared = turn or Turn()
    return TurnPolicy(
        backchannels=words,
        min_words=MIN_WORDS if declared.min_interruption_words is None else declared.min_interruption_words,
        min_speech_s=None if declared.min_interruption_ms is None else declared.min_interruption_ms / 1000,
    )


# The declared words first, so the cap drops the names found in the state before them. One
# level deep catches `patient = {name, phone}`; a term needs a letter, which leaves out numbers.
def keyterms(config: AgentConfig, state: JsonObject) -> list[str]:
    """The words the ears are told to expect: the agent's own, then names the state holds."""
    found: list[object] = []
    for value in state.values():
        found += list(value.values()) if a_mapping(value) else [value]
    names = [name for name in (_a_name(item) for item in found) if name]
    return list(dict.fromkeys(term for term in (*config.hears, *names) if term))[:MOST_TERMS]


def _a_name(value: object) -> str:
    if not isinstance(value, str):
        return ""
    name = value.strip()
    if not name or len(name) > LONGEST_TERM or len(name.split()) > MOST_WORDS:
        return ""
    return name if any(character.isalpha() for character in name) else ""
