"""What `setup` runs a call on, stage by stage: an open model on this machine or a vendor of yours, and the keys."""

import os
from dataclasses import dataclass
from typing import Literal

import typer

from pinecall_runtime.agents.declaration import Modality
from pinecall_runtime.exceptions import ValidationError
from pinecall_runtime.providers import service as providers

# The word for an open model on this machine, in any stage's answer: `local`, or `local/<model>`
# naming the one Ollama runs (`local/gemma4:12b`) or the one Whisper loads.
LOCAL = providers.LOCAL
SLASH = "/"
type Turn = Literal["stt", "smart-turn", "livekit"]
# How the end of the caller's turn is read: the ears' own endpointing, or a model on the worker's CPU.
TURNS: tuple[Turn, ...] = ("stt", "smart-turn", "livekit")
TURN_MODELS: dict[Turn, str | None] = {"stt": None, "smart-turn": "smart-turn-v3", "livekit": "v1-mini"}

# Open models on this machine, through the `openai` plugin and a `base_url` per stage (DEV-FIRST.md).
# The thinking's default is the one that took a message, read the documents and made small talk on
# a 24 GB card (providers/service/machine.py); `setup --recommend` names a larger one where it fits.
LOCAL_LLM = "gemma4:12b"
LOCAL_STT = "deepdml/faster-whisper-large-v3-turbo-ct2"
LOCAL_TTS = "kokoro"
# The embedder is always local: changing it would blind every base and every memory.
LOCAL_EMBEDDER = "bge-m3"
# The three servers, on loopback, as `providers.local.json` reaches them.
MODEL_PORTS = {"Ollama": 11434, "Whisper": 8000, "Kokoro": 8880}
# What the local servers ask for a key: nothing; the plugin wants one, so the org holds this word.
NO_KEY_NEEDED = "local"
# The vendors `--models keys` means when no stage is named.
KEYS_DEFAULTS = {"stt": "deepgram", "llm": "anthropic", "tts": "cartesia"}
NO_KEY_FOR = "{vendor} needs a key: set {variable}, or answer when asked at a terminal"
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
    stages: tuple[tuple[Modality, str], ...] = (
        ("stt", choices.stt),
        ("llm", choices.llm),
        ("tts", choices.tts),
        ("llm", choices.judging),
        ("llm", choices.calling),
    )
    for stage, choice in stages:
        if not is_local(choice):
            providers.vendor_doing(vendor_of(choice), stage)
    if is_local(choices.tts) and model_of(choices.tts) is not None:
        raise ValidationError(ONE_LOCAL_VOICE)
    if choices.turn not in TURNS:
        raise ValidationError(f"--turn is one of {', '.join(TURNS)}, not {choices.turn!r}")
    if choices.turn == "stt" and (is_local(choices.stt) or not providers.ends_turns(vendor_of(choices.stt))):
        who = "the local ears (Whisper)" if is_local(choices.stt) else choices.stt
        raise ValidationError(f"{who} end no turn themselves: --turn smart-turn or livekit")
    return choices


def ask_choices() -> Choices:
    """The questions, at a terminal: each stage's list is what this build runs, plus `local[/model]`."""
    stt = _ask("ears: who hears the caller?", "stt")
    turns = [turn for turn in TURNS if turn != "stt" or (not is_local(stt) and providers.ends_turns(stt))]
    turn = typer.prompt(f"end of turn: {' · '.join(turns)}", default="stt" if "stt" in turns else "smart-turn")
    llm = _ask("thinking: which model?", "llm")
    tts = _ask("voice: who speaks?", "tts")
    judge = _ask("judging a finished call: which model?", "llm", default=llm)
    caller = _ask("the simulated caller: which model?", "llm", default=llm)
    return check_choices(
        Choices(
            stt=stt,
            turn=turn_of(turn),
            llm=llm,
            tts=tts,
            judge=None if judge == llm else judge,
            caller=None if caller == llm else caller,
        )
    )


def _ask(question: str, stage: str, default: str = LOCAL) -> str:
    listed = sorted(
        name for name, vendor in providers.installed().items() if vendor.broken is None and stage in vendor.does
    )
    answer: str = typer.prompt(f"{question}  {LOCAL}[/model] · {' · '.join(listed)}", default=default)
    return local_or_vendor(answer)


# ── the keys ──


def keys_for(choices: Choices, *, asking: bool) -> tuple[dict[str, str], list[str]]:
    """Each chosen vendor's key, from its variable or asked once; and which came from the environment."""
    given: dict[str, str] = {}
    read: list[str] = []
    for vendor in sorted(choices.vendors):
        if not providers.takes_a_key(vendor):
            continue
        variable = providers.key_variable(vendor)
        found = os.environ.get(variable, "").strip()
        if found:
            given[vendor] = found
            read.append(variable)
        elif asking:
            typed = typer.prompt(variable, hide_input=True, show_default=False).strip()
            if not typed:
                raise ValidationError(NO_KEY_FOR.format(vendor=vendor, variable=variable))
            given[vendor] = typed
        else:
            raise ValidationError(NO_KEY_FOR.format(vendor=vendor, variable=variable))
    # The embedder is local, on the openai plugin, whatever the stages: the plugin wants a key.
    given.setdefault("openai", NO_KEY_NEEDED)
    return given, read
