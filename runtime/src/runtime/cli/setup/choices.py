"""What `setup` runs a call on, stage by stage: an open model on this machine or a vendor of yours."""

import os
from dataclasses import dataclass
from typing import Literal

from runtime.cli.setup.files import shipped
from runtime.enums import Stage
from runtime.exceptions import ValidationError
from runtime.providers.service import machine, plugins, signatures

# The word for an open model on this machine, in any stage's answer: `local`, or `local/<model>`
# naming the one Ollama runs (`local/gemma4:12b`) or the one Whisper loads.
LOCAL = machine.LOCAL
SLASH = "/"
type Turn = Literal["stt", "smart-turn", "livekit"]
# How the end of the caller's turn is read: the ears' own endpointing, or a model on the worker's CPU.
TURNS: tuple[Turn, ...] = ("stt", "smart-turn", "livekit")
TURN_MODELS: dict[Turn, str | None] = {"stt": None, "smart-turn": "smart-turn-v3", "livekit": "v1-mini"}

# Open models on this machine, through the `openai` plugin and a `base_url` per stage.
# The thinking's default is the one that took a message, read the documents and made small talk on
# a 24 GB card (providers/service/machine.py); `setup --recommend` names a larger one where it fits.
LOCAL_LLM = "gemma4:12b"
LOCAL_STT = "deepdml/faster-whisper-large-v3-turbo-ct2"
LOCAL_TTS = "kokoro"
# The embedder is always local: changing it would blind every base and every memory.
LOCAL_EMBEDDER = "bge-m3"
# The three servers, on loopback, as `providers.local.json` reaches them.
MODEL_PORTS = {"Ollama": 11434, "Whisper": 8000, "Kokoro": 8880}
# The vendors `--models keys` means when no stage is named.
KEYS_DEFAULTS = {"stt": "deepgram", "llm": "anthropic", "tts": "cartesia"}
ONE_LOCAL_VOICE = "the local voice is Kokoro: --tts local, with no model after it"


@dataclass(frozen=True)
class Choices:
    """One vendor or `local[/model]` per stage, who reads the end of the turn, who judges, who plays the caller."""

    stt: str = LOCAL
    turn: Turn = "smart-turn"
    llm: str = LOCAL
    tts: str = LOCAL
    # None: the thinking's own model judges a finished call, and plays the simulated caller.
    judge: str | None = None
    caller: str | None = None

    @property
    def judging(self) -> str:
        """Who judges a finished call."""
        return self.judge or self.llm

    @property
    def calling(self) -> str:
        """Who improvises the simulated caller's lines."""
        return self.caller or self.llm

    @property
    def thinkers(self) -> tuple[str, str, str]:
        """The three choices that answer with a model: the thinking, the judge, the caller."""
        return (self.llm, self.judging, self.calling)

    @property
    def vendors(self) -> frozenset[str]:
        """The vendors of yours among the choices."""
        return frozenset(vendor_of(choice) for choice in (self.stt, self.tts, *self.thinkers) if not is_local(choice))

    @property
    def local_models(self) -> tuple[str, ...]:
        """The models Ollama must hold, in the order they are pulled: the thinking's first, each once."""
        named = [model_of(choice) or LOCAL_LLM for choice in self.thinkers if is_local(choice)]
        return tuple(dict.fromkeys(named))


# A choice names a vendor, or a vendor and the model it runs: `hf/Qwen/Qwen2.5-3B-Instruct`, `local/gemma4:12b`.
def vendor_of(choice: str) -> str:
    """The vendor a choice names."""
    return choice.partition(SLASH)[0]


def model_of(choice: str) -> str | None:
    """The model a choice names after its vendor, if any."""
    _, _, model = choice.partition(SLASH)
    return model or None


def is_local(choice: str) -> bool:
    """Whether a choice is an open model on this machine."""
    return vendor_of(choice) == LOCAL


def local_or_vendor(text: str) -> str:
    """A flag's or an answer's choice, trimmed; the vendor's name lowered, a model's kept as typed."""
    vendor, slash, model = text.strip().partition(SLASH)
    return f"{vendor.lower()}{slash}{model}"


ALL_LOCAL = Choices()
ALL_KEYS = Choices(stt=KEYS_DEFAULTS["stt"], turn="stt", llm=KEYS_DEFAULTS["llm"], tts=KEYS_DEFAULTS["tts"])


def turn_of(text: str) -> Turn:
    """The turn a flag or an answer names, one of three."""
    named = text.strip().lower()
    if named not in TURNS:
        raise ValidationError(f"--turn is one of {', '.join(TURNS)}, not {text!r}")
    return named


def check_choices(choices: Choices) -> Choices:
    """Each vendor installed and doing its stage; the turn one the ears can read; one local voice."""
    stages: tuple[tuple[Stage, str], ...] = (
        (Stage.stt, choices.stt),
        (Stage.llm, choices.llm),
        (Stage.tts, choices.tts),
        (Stage.llm, choices.judging),
        (Stage.llm, choices.calling),
    )
    for stage, choice in stages:
        if not is_local(choice):
            plugins.vendor_doing(vendor_of(choice), stage)
    if is_local(choices.tts) and model_of(choices.tts) is not None:
        raise ValidationError(ONE_LOCAL_VOICE)
    if choices.turn not in TURNS:
        raise ValidationError(f"--turn is one of {', '.join(TURNS)}, not {choices.turn!r}")
    if choices.turn == "stt" and (is_local(choices.stt) or not signatures.ends_turns(vendor_of(choices.stt))):
        who = "the local ears (Whisper)" if is_local(choices.stt) else choices.stt
        raise ValidationError(f"{who} end no turn themselves: --turn smart-turn or livekit")
    return choices


def recommended(fits: machine.Recommendation) -> Choices:
    """The stack that fits this machine, as `setup --recommend` reads it; the judge and the caller follow it."""
    return Choices(
        stt=local_or_vendor(fits.stack["stt"]),
        turn=turn_of(fits.stack["turn"]),
        llm=local_or_vendor(fits.stack["llm"]),
        tts=local_or_vendor(fits.stack["tts"]),
    )


# The runtime's defaults, what an agent naming no stage runs on: what the flags say, else the open
# models that fit this machine, else the vendors.
def choices_of(
    models: str | None,
    stt: str | None,
    turn: str | None,
    llm: str | None,
    tts: str | None,
    judge: str | None,
    caller: str | None,
    *,
    chat_only: bool,
) -> Choices | None:
    """The runtime's defaults: what the flags say, else the open models that fit this machine, else the vendors."""
    if models == "none":
        return None
    if models not in (None, "local", "keys"):
        raise ValidationError(f"--models is local, keys or none, not {models!r}")
    if models == "keys":
        base = ALL_KEYS
    elif models == "local":
        base = ALL_LOCAL
    else:
        measured = read_measured()
        base = recommended(machine.recommend(machine.detect(measured.on_keys.values(), os.environ), measured))
    chosen = Choices(
        stt=local_or_vendor(stt or base.stt),
        turn=turn_of(turn or base.turn),
        llm=local_or_vendor(llm or base.llm),
        tts=local_or_vendor(tts or base.tts),
        judge=local_or_vendor(judge) if judge else base.judge,
        caller=local_or_vendor(caller) if caller else base.caller,
    )
    if chat_only:
        chosen = Choices(
            stt=LOCAL,
            turn="smart-turn",
            llm=chosen.llm,
            tts=LOCAL,
            judge=chosen.judge,
            caller=chosen.caller,
        )
    return check_choices(chosen)


def read_measured() -> machine.Measured:
    """What a machine can run, as the package ships it measured."""
    return machine.measured_from_csv(shipped("measured.csv").read_text(encoding="utf-8"))
