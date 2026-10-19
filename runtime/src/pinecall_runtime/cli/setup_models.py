"""What `setup` runs a call on, stage by stage: an open model on this machine or a vendor of yours, and the keys."""

import os
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

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
# What the local servers ask for a key: nothing; the plugin wants one, so the org holds this word.
NO_KEY_NEEDED = "local"
# The vendors `--models keys` means when no stage is named.
KEYS_DEFAULTS = {"stt": "deepgram", "llm": "anthropic", "tts": "cartesia"}
NO_KEY_FOR = "{vendor} needs a key: set {variable}, or answer when asked at a terminal"
ONE_LOCAL_VOICE = "the local voice is Kokoro: --tts local, with no model after it"
# Where a key came from, when it was neither in the environment nor in a shell file.
TYPED = "typed"
# How a missing key is asked for at a terminal: the variable's name in, the secret out.
type Ask = Callable[[str], str]


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


def recommended(fits: providers.Recommendation) -> Choices:
    """The stack that fits this machine, as `setup --recommend` reads it; the judge and the caller follow it."""
    return Choices(
        stt=local_or_vendor(fits.stack["stt"]),
        turn=turn_of(fits.stack["turn"]),
        llm=local_or_vendor(fits.stack["llm"]),
        tts=local_or_vendor(fits.stack["tts"]),
    )


# ── the keys ──


def keys_for(
    choices: Choices,
    *,
    ask: Ask | None,
    environ: Mapping[str, str] = os.environ,
    home: Path | None = None,
) -> tuple[dict[str, str], dict[str, str]]:
    """Each chosen vendor's key, from its variable, else a shell file, else asked once; and where each one came from."""
    given: dict[str, str] = {}
    found: dict[str, str] = {}
    for vendor in sorted(choices.vendors):
        if not providers.takes_a_key(vendor):
            continue
        variable = providers.key_variable(vendor)
        secret, where = _read_key(variable, environ, home)
        if not secret and ask is not None:
            secret, where = ask(variable).strip(), TYPED
        if not secret or where is None:
            raise ValidationError(NO_KEY_FOR.format(vendor=vendor, variable=variable))
        given[vendor], found[variable] = secret, where
    # The embedder is local, on the openai plugin, whatever the stages: the plugin wants a key.
    given.setdefault("openai", NO_KEY_NEEDED)
    return given, found


def keys_found(
    *, environ: Mapping[str, str] = os.environ, home: Path | None = None
) -> tuple[dict[str, str], dict[str, str]]:
    """Every installed vendor whose key is in the environment or a shell file, its key read; and where each one was."""
    given: dict[str, str] = {}
    found: dict[str, str] = {}
    for vendor, plugin in sorted(providers.installed().items()):
        if plugin.broken is not None or not providers.takes_a_key(vendor):
            continue
        variable = providers.key_variable(vendor)
        secret, where = _read_key(variable, environ, home)
        if secret and where is not None:
            given[vendor], found[variable] = secret, where
    return given, found


def said_loading(found: Mapping[str, str]) -> str:
    """Where the keys were read from: the environment first, then each shell file holding one."""
    places = sorted(set(found.values()), key=lambda place: (place != providers.THE_ENVIRONMENT, place))
    where = " and ".join(places) if places else "the environment and the shell's files"
    return f"loading providers from {where} …"


def said_providers(loaded: Mapping[str, str]) -> str:
    """The vendors an agent may name with no key to add: each one whose key was found."""
    if not loaded:
        return "providers  no keys found: `pinecall providers add <vendor>` adds one"
    count = f"{len(loaded)} key found" if len(loaded) == 1 else f"{len(loaded)} keys found"
    return f"providers  {' · '.join(sorted(loaded))} — {count}"


def said_models(choices: Choices) -> str:
    """The open models this machine serves: an agent naming none runs on them."""
    served = [
        *choices.local_models,
        *(["whisper"] if is_local(choices.stt) else []),
        *(["kokoro"] if is_local(choices.tts) else []),
    ]
    if not served:
        return "models     none served here: an agent runs on the providers"
    return f"models     {' · '.join(served)} — open, served on this machine"


# A variable's value and where it was: the environment, else the shell file setting it as plain
# text; (None, the file) when the file's line expands, (None, None) when it is nowhere.
def _read_key(variable: str, environ: Mapping[str, str], home: Path | None) -> tuple[str | None, str | None]:
    where = providers.where_is_key(variable, environ, home)
    if where == providers.THE_ENVIRONMENT:
        return environ.get(variable, "").strip(), where
    if where is not None:
        return providers.key_from_shell(variable, home), where
    return None, None
