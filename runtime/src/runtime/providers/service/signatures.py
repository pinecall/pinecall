"""What a plugin's constructor takes: the names it spells each argument with, its one options object, its knobs."""

import dataclasses
import inspect
import types
import typing
from collections.abc import Collection, Mapping
from typing import Protocol

from runtime.enums import Stage
from runtime.exceptions import ServiceUnavailable, ValidationError
from runtime.kit.text import a_mapping
from runtime.providers.service.plugins import CLASS_OF, class_path, plugin
from runtime.providers.stage import Running

# No vendor is named in code: what each plugin accepts is read off its constructor's signature, against
# the names below. This module is the one home of that vocabulary. Plugins spell the same argument
# differently; the first one a constructor declares gets it. `voice_id` comes before `voice`: a
# plugin that declares both reads the id.
THE_KEY = ("api_key", "speech_key", "secret")
THE_VOICE = ("voice_id", "voice_uuid", "voice", "speaker", "voice_name")
THE_LANGUAGE = ("language", "language_code")
THE_HINTS = ("language_hint", "language_hints")
# The words the ears are told to expect: an argument of its own (Deepgram's and Cartesia's `keyterm`),
# or, in a plugin that takes its options as one object, that object's `context` as `{terms: [...]}`
# (Soniox's).
THE_TERMS = ("keyterm",)
A_CONTEXT = "context"
# The argument a plugin names its model by, and the field of its options object when it takes one.
THE_MODEL = "model"

# The org's own knobs and the names a plugin may take each under; one it takes under none is
# refused where the org sets it, not dropped on the next call. The ears that take the endpointing
# may call it `eot_timeout_ms`.
ENDPOINTING = "endpointing_ms"
EOT_TIMEOUT = "eot_timeout_ms"
VOICE = "voice"
SETTING_NAMES: dict[str, tuple[str, ...]] = {
    ENDPOINTING: (ENDPOINTING, EOT_TIMEOUT),
    "eot_threshold": ("eot_threshold",),
    "eager_eot_threshold": ("eager_eot_threshold",),
    VOICE: THE_VOICE,
}


# What an agent says about turns belongs to `agents`, above this domain: the five knobs the ears may
# take are read through this, and whatever declares them is handed in.
class TurnSettings(Protocol):
    """How the session decides the caller has finished, as far as a plugin's ears may be told."""

    @property
    def min_interruption_words(self) -> int | None:
        """The words a caller says before they interrupt."""
        ...

    @property
    def endpointing_ms(self) -> int | None:
        """The silence that closes a turn."""
        ...

    @property
    def eot_threshold(self) -> float | None:
        """The bar for the turn being over."""
        ...

    @property
    def eager_eot_threshold(self) -> float | None:
        """The bar for guessing the turn is over."""
        ...

    @property
    def min_interruption_ms(self) -> int | None:
        """How long a caller speaks before they interrupt."""
        ...


def options_of(turn: TurnSettings | None) -> dict[str, object]:
    """The turn's knobs that are set, by name, the endpointing also under the name some ears call it."""
    if turn is None:
        return {}
    options: dict[str, object] = {
        "min_interruption_words": turn.min_interruption_words,
        ENDPOINTING: turn.endpointing_ms,
        "eot_threshold": turn.eot_threshold,
        "eager_eot_threshold": turn.eager_eot_threshold,
        "min_interruption_ms": turn.min_interruption_ms,
    }
    given = {name: value for name, value in options.items() if value is not None}
    # The agent's endpointing is the silence that closes a turn: the ears that take it call it so.
    if turn.endpointing_ms is not None:
        given[EOT_TIMEOUT] = turn.endpointing_ms
    return given


# ── the class a stage builds, and what it takes ──


# A class may sit in a module of the plugin: `responses.LLM` is its `responses` module's LLM.
def class_of(stage: Stage, running: Running) -> type:
    """The plugin's class for the stage: the one `builds` names, else where the plugin keeps it."""
    module = plugin(running.vendor)
    name = running.builds or class_path(module, stage) or CLASS_OF[stage]
    made: object = module
    for part in name.split("."):
        made = getattr(made, part, None)
    if not isinstance(made, type):
        raise ValidationError(f"{running.vendor} exports no {CLASS_OF[stage]} named {name!r}")
    return made


def parameters_of(made: type) -> frozenset[str]:
    """The names the class's constructor declares; none where its signature does not read."""
    try:
        return frozenset(inspect.signature(made).parameters)
    except (TypeError, ValueError):
        return frozenset()


def every_parameter_of(vendor: str) -> frozenset[str]:
    """The names any of the vendor's three classes takes."""
    module = plugin(vendor)
    taken = frozenset[str]()
    for name in CLASS_OF.values():
        made = getattr(module, name, None)
        if isinstance(made, type):
            taken |= parameters_of(made)
    return taken - {"self", "kwargs", "args"}


def first_of(accepts: frozenset[str], names: tuple[str, ...], value: object) -> dict[str, object]:
    """The value under the first of the names the constructor declares; nothing where it declares none."""
    chosen = next((name for name in names if name in accepts), None)
    return {} if chosen is None or value is None else {chosen: value}


# ── a plugin's one options object ──


def options_object(made: type) -> tuple[str, frozenset[str]] | None:
    """The argument whose declared type is a dataclass, and that dataclass's fields; None when it takes none."""
    try:
        parameters = inspect.signature(made, eval_str=True).parameters
    except (NameError, TypeError, ValueError):
        return None
    for name, parameter in parameters.items():
        shape = dataclass_in(parameter.annotation)
        if shape is not None:
            return name, frozenset(each.name for each in dataclasses.fields(shape))
    return None


# A plugin that takes its options as one object (`params=STTOptions(...)`) is given that object,
# built from the row's mapping field by field, however deep.
def shape_arguments(made: type, given: Mapping[str, object]) -> dict[str, object]:
    """The arguments with each mapping built into the dataclass the plugin declares for it, however deep."""
    try:
        annotations = {
            name: parameter.annotation for name, parameter in inspect.signature(made, eval_str=True).parameters.items()
        }
    except (NameError, TypeError):
        return dict(given)
    return {name: _as_annotated(annotations.get(name), value) for name, value in given.items()}


def dataclass_in(annotation: object) -> type | None:
    """The dataclass a declared type is, or holds in a union; None for any other."""
    if isinstance(annotation, type) and dataclasses.is_dataclass(annotation):
        return annotation
    if isinstance(annotation, types.UnionType):
        return next((one for one in typing.get_args(annotation) if dataclass_in(one)), None)
    return None


def _as_annotated(annotation: object, value: object) -> object:
    shape = dataclass_in(annotation)
    if shape is None:
        # JSON has one number: `speed=1.0` arrives as 1, and a parameter typed float alone takes 1.0.
        return float(value) if type(value) is int and _takes_a_float(annotation) else value
    if not a_mapping(value):
        return value
    typed = typing.get_type_hints(shape)
    return shape(**{name: _as_annotated(typed.get(name), given) for name, given in value.items()})


def _takes_a_float(annotation: object) -> bool:
    options = typing.get_args(annotation) or (annotation,)
    return float in options and int not in options


# ── what a vendor's plugin says of itself ──


# A plugin whose classes take no key (an open model run in this process) runs on none: the keyring
# asks nothing of the org or the box for it.
def takes_a_key(vendor: str) -> bool:
    """Whether any class of the vendor's plugin takes a key."""
    return bool(every_parameter_of(vendor) & set(THE_KEY))


# The ears that close a turn themselves take the agent's endpointing: a vendor whose STT takes none
# needs a turn model beside it (Smart Turn, LiveKit's) to say when the caller finished.
def ends_turns(vendor: str) -> bool:
    """Whether the vendor's ears take an endpointing of their own."""
    made = getattr(plugin(vendor), CLASS_OF[Stage.stt], None)
    return isinstance(made, type) and bool(parameters_of(made) & set(SETTING_NAMES[ENDPOINTING]))


# What a plugin's constructor declares as its voice's default is the voice a stage that names none
# speaks with: an agent on no voice of its own and no voice of the operator's speaks in it.
def default_voice(running: Running) -> str | None:
    """The voice the stage's plugin speaks with when it is handed none."""
    try:
        parameters = inspect.signature(class_of(Stage.tts, running)).parameters
    except (TypeError, ValueError):
        return None
    named = next((parameters[name] for name in THE_VOICE if name in parameters), None)
    default = None if named is None else named.default
    return default if isinstance(default, str) and default != "" else None


# A plugin lists its voices when its TTS class has a `list_voices`; nothing is built to ask.
def lists_voices(vendor: str, does: Collection[Stage]) -> bool:
    """Whether the vendor's plugin can list its voices."""
    if Stage.tts not in does:
        return False
    try:
        speech = getattr(plugin(vendor), CLASS_OF[Stage.tts], None)
    except (ValidationError, ServiceUnavailable):
        return False
    return callable(getattr(speech, "list_voices", None))


# ── refusals, where a knob is set ──


# Only what the org set: the key, the language and the hints are the runtime's, and a plugin
# that takes none of them is the operator's to configure in the providers row.
def refuse_untaken_settings(ears: Running, voice: Running, turn: TurnSettings | None, *, sets_a_voice: bool) -> None:
    """Refuse the org's turn and voice settings that its ears or its voice take under no name."""
    heard: dict[str, object] = {
        ENDPOINTING: None if turn is None else turn.endpointing_ms,
        "eot_threshold": None if turn is None else turn.eot_threshold,
        "eager_eot_threshold": None if turn is None else turn.eager_eot_threshold,
    }
    # Ears that leave the turn open never take the silence: the session's detector does. On Scribe
    # `endpointing_ms` was refused as untaken, and the agent spoke over callers who paused (2026-11-06).
    if not ears.ends_the_turn:
        heard.pop(ENDPOINTING)
    refuse_untaken(Stage.stt, ears, [name for name, value in heard.items() if value is not None])
    refuse_untaken(Stage.tts, voice, [VOICE] if sets_a_voice else [])


# A voice is never untaken by a tts: a plugin with no voice argument speaks it as its model.
def refuse_untaken(stage: Stage, running: Running, settings: list[str]) -> None:
    """Refuse the settings the stage's class takes under none of their names."""
    if not settings:
        return
    accepts = parameters_of(class_of(stage, running))
    untaken = [
        setting
        for setting in settings
        if not any(name in accepts for name in SETTING_NAMES[setting]) and not (stage is Stage.tts and setting == VOICE)
    ]
    if untaken:
        raise ValidationError(
            f"{running.vendor}'s {stage} takes no {', '.join(untaken)}, so a call would run without it: "
            "leave it out, or pick a vendor that takes it"
        )
