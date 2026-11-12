"""The vendors this process can build a stage from: livekit's plugins, installed, and what each does."""

import importlib
import importlib.util
import inspect
import logging
import pkgutil
import typing
import warnings
from collections.abc import Mapping
from dataclasses import dataclass, field
from functools import cache
from types import ModuleType
from typing import Never

from livekit.agents import llm, stt, tts

from runtime.enums import Stage
from runtime.exceptions import ServiceUnavailable, ValidationError

logger = logging.getLogger(__name__)

# LiveKit Inference: the same three classes, on the box's LiveKit key pair, models `vendor/model`.
INFERENCE = "livekit"
INFERENCE_MODULE = "livekit.agents.inference"
PLUGINS = "livekit.plugins"

STAGES: tuple[Stage, ...] = (Stage.llm, Stage.stt, Stage.tts)
CLASS_OF: dict[Stage, str] = {Stage.llm: "LLM", Stage.stt: "STT", Stage.tts: "TTS"}
# Where a plugin puts each class, in the order looked for: at the top of its module, or an LLM on the
# Responses API in its `responses` module, as xAI's Grok is (`livekit.plugins.xai.responses.LLM`).
CLASS_PATHS: dict[Stage, tuple[str, ...]] = {
    Stage.llm: ("LLM", "responses.LLM"),
    Stage.stt: ("STT",),
    Stage.tts: ("TTS",),
}
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


@dataclass(frozen=True, slots=True)
class Vendor:
    """A vendor this process can build: what it does, or why its plugin does not import."""

    name: str
    does: frozenset[Stage]
    broken: str | None = None
    # The models that hear and speak themselves, by name: the agent's `realtime` names one for its voice calls.
    realtime: tuple[str, ...] = ()
    # The model each stage's class builds when none is named, where its constructor says one (Deepgram's
    # `nova-3`); a plugin that decides inside says nothing here.
    defaults: Mapping[Stage, str] = field(default_factory=dict[Stage, str])


# Nobody keeps a list of vendors: it is what is installed. livekit's own `Plugin.registered_plugins`
# knows a plugin only once it was imported, so the namespace is walked.
@cache
def list_vendors() -> dict[str, Vendor]:
    """Every vendor of this process: each livekit plugin exporting an LLM, an STT or a TTS."""
    found = {INFERENCE: _read_vendor(INFERENCE, INFERENCE_MODULE)}
    spec = importlib.util.find_spec(PLUGINS)
    locations = spec.submodule_search_locations if spec is not None else None
    for module in pkgutil.iter_modules(locations or []):
        vendor = _read_vendor(module.name, f"{PLUGINS}.{module.name}")
        if vendor.does or vendor.broken:
            found[vendor.name] = vendor
    return found


def is_installed(vendor: str) -> bool:
    """Whether a plugin of that name is installed here."""
    return vendor in list_vendors()


def parse_vendor(vendor: str) -> str:
    """The vendor's name as installed; refused naming the ones this build runs."""
    named = vendor.strip().lower()
    if named not in list_vendors():
        raise ValidationError(f"no vendor named {vendor!r}; this build runs: {', '.join(sorted(list_vendors()))}")
    return named


def vendor_doing(vendor: str, stage: Stage) -> str:
    """The vendor's name, once it is installed and does that stage; refused if not."""
    found = list_vendors().get(vendor)
    if found is None:
        raise ValidationError(
            f"no vendor named {vendor!r} is installed here: `pinecall providers catalog` lists every one"
        )
    if found.broken is None and stage not in found.does:
        raise ValidationError(f"{vendor} has no {stage}: it does {', '.join(sorted(found.does))}")
    return vendor


# A plugin that did not import is tried again: what broke it (a package missing) may have been
# fixed since the process started.
def plugin(vendor: str) -> ModuleType:
    """The installed module of a vendor; refused when it is not installed or does not import."""
    found = list_vendors().get(vendor)
    if found is None:
        raise ValidationError(
            f'no vendor named {vendor!r} is installed; `pip install "livekit-agents[{vendor}]"` adds its plugin'
        )
    module = INFERENCE_MODULE if vendor == INFERENCE else f"{PLUGINS}.{vendor}"
    if found.broken is not None:
        found = _read_vendor(vendor, module)
        list_vendors()[vendor] = found
    if found.broken is not None:
        raise ServiceUnavailable(f"the {vendor} plugin is installed and does not import: {found.broken}")
    return importlib.import_module(module)


def class_path(module: object, stage: Stage) -> str | None:
    """Where the module keeps its class for that stage (`LLM`, `responses.LLM`), or None."""
    return next((path for path in CLASS_PATHS[stage] if isinstance(_at(module, path), type)), None)


def default_models(module: object, does: set[Stage]) -> dict[Stage, str]:
    """The model each stage's class builds when none is named, where its `model` argument defaults to one."""
    found: dict[Stage, str] = {}
    for stage in sorted(does):
        path = class_path(module, stage)
        made = None if path is None else _at(module, path)
        if not isinstance(made, type):
            continue
        try:
            argument = inspect.signature(made).parameters.get("model")
        except (TypeError, ValueError):
            continue
        if argument is not None and isinstance(argument.default, str) and argument.default:
            found[stage] = argument.default
    return found


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
    found = list_vendors().get(vendor)
    named = found is not None and model is not None and model in found.realtime
    made = None if builds is None else _at(plugin(vendor), builds)
    if named or (isinstance(made, type) and issubclass(made, llm.RealtimeModel)):
        said = f"{vendor}/{model}" if model else vendor
        raise ValidationError(
            f"{said} hears and speaks itself, so it is the agent's realtime and not its llm: "
            f"@realtime('{said}') or --realtime {said}, and the llm stays the model a written call answers with"
        )


def models_listed(module: object, path: str) -> tuple[str, ...]:
    """The models the class at the path types its `model` argument with (a Literal); none where it types none."""
    made = _at(module, path)
    if not isinstance(made, type):
        return ()
    try:
        argument = inspect.signature(made, eval_str=True).parameters.get("model")
    except (NameError, TypeError, ValueError):
        return ()
    return () if argument is None else _literal_in(argument.annotation)


def realtime_models(module: object) -> tuple[str, ...]:
    """The models the plugin's realtime class runs, by name; none where it has no such class or names none."""
    path = realtime_path(module)
    if path is None:
        return ()
    typed = models_listed(module, path)
    if typed:
        return typed
    for holder in (module, getattr(module, "models", None)):
        for name in dir(holder) if holder is not None else ():
            listed = _literal_in(getattr(holder, name)) if name.endswith(REALTIME_MODELS) else ()
            if listed:
                return listed
    return ()


# A plugin's own imports warn about what only it would use (clova's pydub: "Couldn't find ffmpeg"),
# on every command of the operator's CLI; what a plugin says while it is imported is not ours to say.
def _read_vendor(name: str, module: str) -> Vendor:
    try:
        with warnings.catch_warnings():
            warnings.simplefilter("ignore", (RuntimeWarning, SyntaxWarning))
            imported = importlib.import_module(module)
    except ImportError as broken:
        logger.warning("the %s plugin does not import, so it builds nothing", name, exc_info=True)
        return Vendor(name, frozenset(), broken=str(broken))
    does: set[Stage] = {stage for stage in STAGES if class_path(imported, stage) is not None}
    # A realtime model is the LLM stage of the calls it runs, whatever else the plugin exports.
    if realtime_path(imported) is not None:
        does.add(Stage.llm)
    return Vendor(name, frozenset(does), realtime=realtime_models(imported), defaults=default_models(imported, does))


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
def _literal_in(annotation: object) -> tuple[str, ...]:
    if typing.get_origin(annotation) is typing.Literal:
        return tuple(one for one in typing.get_args(annotation) if isinstance(one, str))
    return tuple(name for inner in typing.get_args(annotation) for name in _literal_in(inner))
