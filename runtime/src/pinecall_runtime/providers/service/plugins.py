"""The vendors this process can build a stage from: livekit's plugins, installed, and what each does."""

import importlib
import importlib.util
import inspect
import logging
import pkgutil
import re
import typing
from collections.abc import Mapping
from dataclasses import dataclass, field
from functools import cache
from types import ModuleType
from typing import Any, Never

from livekit.agents import APIError, llm, stt, tts
from livekit.agents.language import LanguageCode

from pinecall_runtime.agents.declaration import Modality
from pinecall_runtime.exceptions import ServiceUnavailable, ValidationError
from pinecall_runtime.kit.text import a_mapping
from pinecall_runtime.providers.schemas import TurnModel

# A key alone, or the object a plugin's constructor takes (`speech_key` and `speech_region`).
type Credentials = str | Mapping[str, Any]
# A call's stage as it is built: the plugin's object, or livekit's adapter over several.
type Thinking = llm.LLM[Never] | llm.FallbackAdapter
type Ears = stt.STT[Never] | stt.FallbackAdapter
type Speaking = tts.TTS[Never] | tts.FallbackAdapter

logger = logging.getLogger(__name__)

# LiveKit Inference: the same three classes, on the box's LiveKit key pair, models `vendor/model`.
INFERENCE = "livekit"
INFERENCE_MODULE = "livekit.agents.inference"
PLUGINS = "livekit.plugins"

MODALITIES: tuple[Modality, ...] = ("llm", "stt", "tts")
CLASS_OF: dict[Modality, str] = {"llm": "LLM", "stt": "STT", "tts": "TTS"}
# Where a plugin puts each class, in the order looked for: at the top of its module, or an LLM on the
# Responses API in its `responses` module, as xAI's Grok is (`livekit.plugins.xai.responses.LLM`).
CLASS_PATHS: dict[Modality, tuple[str, ...]] = {"llm": ("LLM", "responses.LLM"), "stt": ("STT",), "tts": ("TTS",)}
# A model that hears and speaks itself (xAI's Grok Voice, OpenAI's Realtime API) is the plugin's
# realtime class, where it keeps one: in its `realtime` module, or at the top. The models that class
# runs are what the plugin types its `model` argument as (a Literal), else what it lists under a
# name ending so, at its top or in its `models` module (OpenAI's `RealtimeModels`).
REALTIME_PATHS: tuple[str, ...] = ("realtime.RealtimeModel", "RealtimeModel")
REALTIME_MODELS = "RealtimeModels"
# Where a refused realtime model points the person: the ones the catalogue lists.
NOT_REALTIME = "`pinecall providers` lists, by vendor, the models that do"

# livekit's three bases are generic in the extra events a subclass may emit; a plugin adds none.
AN_LLM: type[llm.LLM[Never]] = llm.LLM
AN_STT: type[stt.STT[Never]] = stt.STT
A_TTS: type[tts.TTS[Never]] = tts.TTS

# Plugins spell the same argument differently; the first one a constructor declares gets it.
# `voice_id` comes before `voice`: a plugin that declares both reads the id.
THE_KEY = ("api_key", "speech_key", "secret")
THE_VOICE = ("voice_id", "voice_uuid", "voice", "speaker", "voice_name")
THE_LANGUAGE = ("language", "language_code")
THE_HINTS = ("language_hint", "language_hints")
# The words the ears are told to expect: an argument of its own (Deepgram's and Cartesia's `keyterm`),
# or, in a plugin that takes its options as one object, that object's `context` as `{terms: [...]}`
# (Soniox's).
THE_TERMS = ("keyterm",)
A_CONTEXT = "context"

# The org's own knobs and the names a plugin may take each under; one it takes under none is
# refused where the org sets it, not dropped on the next call. `stt_of` gives the endpointing to
# ears that call it `eot_timeout_ms`.
KNOB_NAMES: dict[str, tuple[str, ...]] = {
    "endpointing_ms": ("endpointing_ms", "eot_timeout_ms"),
    "eot_threshold": ("eot_threshold",),
    "eager_eot_threshold": ("eager_eot_threshold",),
    "voice": THE_VOICE,
}

# What an org's credentials object may carry: the fields the vendor's constructors take, none of
# them an address, a file or a session. Where a vendor is reached is the operator's, in the
# providers row's tuning; a tenant's object that named one would aim the box's requests anywhere.
NOT_A_CREDENTIAL = frozenset({"url", "host", "endpoint", "session", "client", "transport", "connection", "model"})
NOT_A_CREDENTIAL_ENDS = ("_url", "_base", "_endpoint", "_host", "_file", "_path", "_session")
MOST_FIELDS = 8
LONGEST_VALUE = 1024

# A component that failed is named in its error's label: `label='livekit.plugins.deepgram.stt.STT'`.
LABELLED = re.compile(
    rf"label='(?:{re.escape(PLUGINS)}\.(?P<plugin>\w+)|(?P<inference>{re.escape(INFERENCE_MODULE)}))\."
)


@dataclass(frozen=True, slots=True)
class Vendor:
    """A vendor this process can build: what it does, or why its plugin does not import."""

    name: str
    does: frozenset[Modality]
    broken: str | None = None
    # The models that hear and speak themselves, by name: the agent's `realtime` names one for its voice calls.
    realtime: tuple[str, ...] = ()


@dataclass(frozen=True)
class Running:
    """One stage of a call as it runs: vendor, model, key, and what the plugin is told."""

    vendor: str
    credentials: Credentials
    # None: the plugin's own default.
    model: str | None = None
    # The plugin's class, where the operator names one other than LLM, STT or TTS.
    builds: str | None = None
    # The operator's keyword arguments for this vendor and stage, as the plugin names them.
    options: Mapping[str, Any] = field(default_factory=dict[str, Any])
    voice: str | None = None
    language: str | None = None
    # Languages the ears listen for, the call's first.
    hints: tuple[str, ...] = ()
    # The ears end the turn themselves, so the session stacks no detector on top.
    ends_the_turn: bool = False
    # Which local model reads the end of the turn off the audio, where the ears do not.
    turn_model: TurnModel = "smart-turn-v3"
    # What every request of an llm stage carries beside the conversation, in the vendor's names.
    request: Mapping[str, Any] = field(default_factory=dict[str, Any])
    # On the box's key rather than the org's own.
    lent: bool = False
    # Who takes over, in order, each on its own key: the stage is livekit's FallbackAdapter.
    fallbacks: tuple["Running", ...] = ()


# ── what is installed ──


@cache
def installed() -> dict[str, Vendor]:
    """Every vendor of this process: each livekit plugin exporting an LLM, an STT or a TTS."""
    found = {INFERENCE: _vendor(INFERENCE, INFERENCE_MODULE)}
    spec = importlib.util.find_spec(PLUGINS)
    locations = spec.submodule_search_locations if spec is not None else None
    for module in pkgutil.iter_modules(locations or []):
        vendor = _vendor(module.name, f"{PLUGINS}.{module.name}")
        if vendor.does or vendor.broken:
            found[vendor.name] = vendor
    return found


def is_installed(vendor: str) -> bool:
    """Whether a plugin of that name is installed here."""
    return vendor in installed()


def installed_vendor(vendor: str) -> str:
    """The vendor's name as installed; refused naming the ones this build runs."""
    named = vendor.strip().lower()
    if named not in installed():
        raise ValidationError(f"no vendor named {vendor!r}; this build runs: {', '.join(sorted(installed()))}")
    return named


def vendor_doing(vendor: str, modality: Modality) -> str:
    """The vendor's name, once it is installed and does that stage; refused if not."""
    found = installed().get(vendor)
    if found is None:
        raise ValidationError(
            f"no vendor named {vendor!r} is installed here: `pinecall providers catalog` lists every one"
        )
    if found.broken is None and modality not in found.does:
        raise ValidationError(f"{vendor} has no {modality}: it does {', '.join(sorted(found.does))}")
    return vendor


# A plugin that did not import is tried again: what broke it (a package missing) may have been
# fixed since the process started.
def plugin(vendor: str) -> ModuleType:
    """The installed module of a vendor; refused when it is not installed or does not import."""
    found = installed().get(vendor)
    if found is None:
        raise ValidationError(
            f'no vendor named {vendor!r} is installed; `pip install "livekit-agents[{vendor}]"` adds its plugin'
        )
    module = INFERENCE_MODULE if vendor == INFERENCE else f"{PLUGINS}.{vendor}"
    if found.broken is not None:
        found = _vendor(vendor, module)
        installed()[vendor] = found
    if found.broken is not None:
        raise ServiceUnavailable(f"the {vendor} plugin is installed and does not import: {found.broken}")
    return importlib.import_module(module)


def vendor_named_in(text: str) -> str:
    """The vendor whose plugin a component's error names, "" when it names none."""
    found = LABELLED.search(text)
    if found is None:
        return ""
    return INFERENCE if found["inference"] else found["plugin"]


# What a plugin or a row hands back is typed as nothing; these say what it is, once.
def primary_language(language: str | None) -> str | None:
    """The base code of a language (`es` for `es-ES` or `spanish`); vendors refuse full tags."""
    if language is None or not language.strip():
        return None
    return LanguageCode(language.strip()).language


# ── private ──


def _vendor(name: str, module: str) -> Vendor:
    try:
        imported = importlib.import_module(module)
    except ImportError as broken:
        logger.warning("the %s plugin does not import, so it builds nothing", name, exc_info=True)
        return Vendor(name, frozenset(), broken=str(broken))
    does: set[Modality] = {m for m in MODALITIES if class_path(imported, m) is not None}
    # A realtime model is the LLM stage of the calls it runs, whatever else the plugin exports.
    if realtime_path(imported) is not None:
        does.add("llm")
    return Vendor(name, frozenset(does), realtime=realtime_models(imported))


def class_path(module: object, modality: Modality) -> str | None:
    """Where the module keeps its class for that stage (`LLM`, `responses.LLM`), or None."""
    return next((path for path in CLASS_PATHS[modality] if isinstance(_at(module, path), type)), None)


def realtime_path(module: object) -> str | None:
    """Where the module keeps its realtime model's class (`realtime.RealtimeModel`), or None."""
    return next((path for path in REALTIME_PATHS if isinstance(_at(module, path), type)), None)


def hears_and_speaks(vendor: str) -> bool:
    """Whether the vendor's plugin has a realtime model's class."""
    return realtime_path(plugin(vendor)) is not None


# The model that writes the answers is never one that hears and speaks itself: that one is the
# agent's `realtime`, and a written call could not run on it. A class the plugin does not export is
# its own refusal, where the stage is built.
def refuse_realtime_as_llm(vendor: str, model: str | None, builds: str | None) -> None:
    """Refuse an LLM stage that names a realtime model, by its name or by its class."""
    found = installed().get(vendor)
    named = found is not None and model is not None and model in found.realtime
    made = None if builds is None else _at(plugin(vendor), builds)
    if named or (isinstance(made, type) and issubclass(made, llm.RealtimeModel)):
        said = f"{vendor}/{model}" if model else vendor
        raise ValidationError(
            f"{said} hears and speaks itself, so it is the agent's realtime and not its llm: "
            f"@realtime('{said}') or --realtime {said}, and the llm stays the model a written call answers with"
        )


def realtime_models(module: object) -> tuple[str, ...]:
    """The models the plugin's realtime class runs, by name; none where it has no such class or names none."""
    path = realtime_path(module)
    made = None if path is None else _at(module, path)
    if not isinstance(made, type):
        return ()
    try:
        argument = inspect.signature(made, eval_str=True).parameters.get("model")
    except (NameError, TypeError, ValueError):
        argument = None
    declared = None if argument is None else argument.annotation
    typed = _literal_in(declared)
    if typed:
        return typed
    for holder in (module, getattr(module, "models", None)):
        for name in dir(holder) if holder is not None else ():
            listed = _literal_in(getattr(holder, name)) if name.endswith(REALTIME_MODELS) else ()
            if listed:
                return listed
    return ()


# A plugin may raise ImportError for a module whose extras are not installed (AWS's `realtime`): that
# module is not there, as a missing one is not.
def _at(module: object, path: str) -> object:
    found: object = module
    for part in path.split("."):
        try:
            found = getattr(found, part, None)
        except ImportError:
            return None
    return found


# The strings of a Literal, through the unions a plugin wraps it in (`NotGivenOr[Models | str]`).
def _literal_in(declared: object) -> tuple[str, ...]:
    if typing.get_origin(declared) is typing.Literal:
        return tuple(one for one in typing.get_args(declared) if isinstance(one, str))
    return tuple(name for inner in typing.get_args(declared) for name in _literal_in(inner))


# A vendor SDK puts its whole body in the message (`Error code: 401 - {'message': …}`): the
# vendor's own sentence is the body's `message`, at its top or under `error`, when it has one.
def words_of(refused: APIError) -> str:
    """What the vendor said, in its words."""
    body = refused.body
    holders: list[Mapping[str, object]] = []
    if a_mapping(body):
        holders.append(body)
        nested = body.get("error")
        if a_mapping(nested):
            holders.append(nested)
    for holder in holders:
        said = holder.get("message")
        if isinstance(said, str) and said.strip():
            return said.strip()
    return refused.message
