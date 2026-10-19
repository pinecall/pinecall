"""A stage of a call built from its vendor: the plugin's class called with the key, the model and the knobs."""

import asyncio
import dataclasses
import inspect
import logging
import types
import typing
from collections.abc import Callable, Mapping, Sequence
from typing import Any, Never, override

from livekit.agents import llm, stt, tts
from livekit.agents.llm import Tool, ToolChoice
from livekit.agents.types import DEFAULT_API_CONNECT_OPTIONS, NOT_GIVEN, APIConnectOptions, NotGivenOr
from livekit.agents.utils import is_given

from pinecall_runtime.agents.declaration import Modality, Tuning, Turn
from pinecall_runtime.exceptions import ValidationError
from pinecall_runtime.kit.text import a_mapping
from pinecall_runtime.providers.service.plugins import (
    A_CONTEXT,
    A_TTS,
    AN_LLM,
    AN_STT,
    CLASS_OF,
    KNOB_NAMES,
    LONGEST_VALUE,
    MOST_FIELDS,
    NOT_A_CREDENTIAL,
    NOT_A_CREDENTIAL_ENDS,
    THE_HINTS,
    THE_KEY,
    THE_LANGUAGE,
    THE_TERMS,
    THE_VOICE,
    Credentials,
    Ears,
    Running,
    Speaking,
    Thinking,
    class_path,
    plugin,
    primary_language,
)
from pinecall_runtime.wire.metrics import LLMModelUsage

logger = logging.getLogger(__name__)


# How a model samples is the stage's: the row's request fields and the agent's temperature, set
# where the model is named. A caller's own sampling never rides a request: livekit's intent judge
# asks every model for temperature 0 (`run_result.py`), which a vendor's SDK may no longer take
# at all, and the operator chose the model's own.
SAMPLING = frozenset({"temperature", "top_p", "top_k"})


# A plugin's constructor takes no field for every request (a model's thinking, its effort), and
# livekit hands each request extra_kwargs: the row's ride every one, a caller's own over them.
# xAI's Responses API ends a reply with usage that counts no cache writes (`cache_write_tokens: null`),
# and livekit's Responses stream passes that None on where an int is due: the reply is said whole, then
# the stream fails as a "connection error" and the turn with it. A count the vendor does not give is
# read as none written. Only a Responses stream reads such usage; any other is left as it is.
def counting_unreported_cache_as_none(stream: llm.LLMStream) -> llm.LLMStream:
    """The stream, its usage's missing cache counts read as 0 before livekit reads them."""
    processed: object = getattr(stream, "_process_event", None)
    if not callable(processed):
        return stream

    def process(event: object) -> object:
        usage = getattr(getattr(event, "response", None), "usage", None)
        details = getattr(usage, "input_tokens_details", None)
        for count in ("cached_tokens", "cache_write_tokens"):
            if details is not None and hasattr(details, count) and getattr(details, count) is None:
                setattr(details, count, 0)
        return processed(event)

    # The stream's own hook, replaced on this instance alone; object.__setattr__ names it as data.
    object.__setattr__(stream, "_process_event", process)
    return stream


class LLMWithRequest(llm.LLM[Never]):
    """A plugin's LLM whose every request carries the operator's fields for its model, and no caller's sampling."""

    def __init__(self, built: llm.LLM[Never], request: Mapping[str, Any]) -> None:
        super().__init__()
        self.built = built
        self.request = dict(request)
        self._label = built.label
        built.on("metrics_collected", self._reported_metrics)  # pyright: ignore[reportUnknownMemberType]
        built.on("error", self._reported_error)  # pyright: ignore[reportUnknownMemberType]

    @property
    @override
    def model(self) -> str:
        """The built LLM's model, so usage and metrics name it."""
        return self.built.model

    @property
    @override
    def provider(self) -> str:
        """The built LLM's vendor, so usage and metrics name it."""
        return self.built.provider

    @override
    def chat(
        self,
        *,
        chat_ctx: llm.ChatContext,
        tools: list[Tool] | None = None,
        conn_options: APIConnectOptions = DEFAULT_API_CONNECT_OPTIONS,
        parallel_tool_calls: NotGivenOr[bool] = NOT_GIVEN,
        tool_choice: NotGivenOr[ToolChoice] = NOT_GIVEN,
        extra_kwargs: NotGivenOr[dict[str, Any]] = NOT_GIVEN,
    ) -> llm.LLMStream:
        """The built LLM's request, with the row's fields and the caller's over them, its sampling aside."""
        given = {
            name: value
            for name, value in (extra_kwargs if is_given(extra_kwargs) else {}).items()
            if name not in SAMPLING
        }
        return counting_unreported_cache_as_none(
            self.built.chat(
                chat_ctx=chat_ctx,
                tools=tools,
                conn_options=conn_options,
                parallel_tool_calls=parallel_tool_calls,
                tool_choice=tool_choice,
                extra_kwargs={**self.request, **given},
            )
        )

    @override
    def prewarm(self, *, loop: asyncio.AbstractEventLoop | None = None) -> None:
        """Open the built LLM's connection before the first request."""
        self.built.prewarm(loop=loop)

    @override
    async def aclose(self) -> None:
        """Stop listening to the built LLM, and close it."""
        self.built.off("metrics_collected", self._reported_metrics)  # pyright: ignore[reportUnknownMemberType]
        self.built.off("error", self._reported_error)  # pyright: ignore[reportUnknownMemberType]
        await self.built.aclose()

    def _reported_metrics(self, *args: object) -> None:
        self.emit("metrics_collected", *args)

    def _reported_error(self, *args: object) -> None:
        self.emit("error", *args)


# ── building a stage ──


def llm_of(running: Running) -> llm.LLM[Never]:
    """The LLM a stage runs: the plugin's class called with the key, the model and the options."""
    return LLMWithRequest(_built("llm", AN_LLM, running, {}), running.request)


def tts_of(running: Running) -> tts.TTS[Never]:
    """The voice a stage speaks with, its voice and language under the names its plugin uses."""
    return _built("tts", A_TTS, running, {})


def stt_of(running: Running, turn: Turn | None, hear: Sequence[str] = ()) -> stt.STT[Never]:
    """The ears a stage hears with; the agent's turn knobs reach them where they take them, and the
    words to expect under whatever name the plugin takes them."""
    return _built("stt", AN_STT, running, _turn_knobs(turn), tuple(hear))


# A model that hears and speaks itself (xAI's `realtime.RealtimeModel`, named by the agent's `llm-builds`)
# stands for the whole conversation of a voice call: no ears, its own voice. None when the LLM stage
# builds a plain LLM, as it does unless the agent names such a class.
def build_realtime(running: Running) -> llm.RealtimeModel | None:
    """The realtime model the LLM stage builds, or None."""
    if not issubclass(_class_of("llm", running), llm.RealtimeModel):
        return None
    return _built("llm", llm.RealtimeModel, running, {})


# A call's three stages: with no fallback, exactly the plugin's object; with some, livekit's
# FallbackAdapter over the stage and the vendors that take over, in order.
def build_thinking(running: Running) -> Thinking:
    """The LLM a call thinks with, over its fallbacks when the stage names any."""
    primary = llm_of(running)
    if not running.fallbacks:
        return primary
    return llm.FallbackAdapter([primary, *(llm_of(fallback) for fallback in running.fallbacks)])


# livekit's adapter wraps ears that do not stream with a VAD the session does not hold, and refuses
# voices of another channel count: such a fallback is left out and the call runs on the rest.
def build_ears(running: Running, turn: Turn | None, hear: Sequence[str] = ()) -> Ears:
    """The ears a call hears with, over its fallbacks when the stage names any that stream."""
    primary = stt_of(running, turn, hear)
    if not primary.capabilities.streaming:
        return primary
    backups: list[stt.STT[Never]] = []
    for fallback in running.fallbacks:
        ears = stt_of(fallback, turn, hear)
        if ears.capabilities.streaming:
            backups.append(ears)
        else:
            logger.warning("%s is left out of the stage's fallbacks: it does not stream", ears.label)
    return stt.FallbackAdapter([primary, *backups]) if backups else primary


# The adapter resamples to the highest rate among them, but mixes no channels.
def build_voice(running: Running) -> Speaking:
    """The voice a call speaks with, over its fallbacks when the stage names any that fit."""
    primary = tts_of(running)
    backups: list[tts.TTS[Never]] = []
    for fallback in running.fallbacks:
        voice = tts_of(fallback)
        if voice.num_channels == primary.num_channels:
            backups.append(voice)
        else:
            logger.warning("%s is left out of the stage's fallbacks: its channels differ", voice.label)
    return tts.FallbackAdapter([primary, *backups]) if backups else primary


# What a plugin's constructor declares as its voice's default is the voice a stage that names none
# speaks with: an agent on no voice of its own and no voice of the operator's speaks in it.
def default_voice(running: Running) -> str | None:
    """The voice the stage's plugin speaks with when it is handed none."""
    try:
        declared = inspect.signature(_class_of("tts", running)).parameters
    except (TypeError, ValueError):
        return None
    named = next((declared[name] for name in THE_VOICE if name in declared), None)
    default = None if named is None else named.default
    return default if isinstance(default, str) and default != "" else None


# A model the runtime asks itself, outside a call's session: livekit meters none of it.
def completion_usage(model: llm.LLM[Never], used: llm.CompletionUsage | None) -> LLMModelUsage | None:
    """What one answer of a model cost in tokens, as the call's usage writes it."""
    if used is None:
        return None
    # Frames drop unset fields, so the discriminator is set here or the SDKs reject the entry.
    return LLMModelUsage(
        type="llm_usage",
        provider=model.provider,
        model=model.model,
        input_tokens=used.prompt_tokens,
        input_cached_tokens=used.prompt_cached_tokens,
        input_cache_creation_tokens=used.cache_creation_tokens,
        output_tokens=used.completion_tokens,
    )


# ── refusals, where a thing is set ──


# Only what the org set: the key, the language and the hints are the runtime's, and a plugin
# that takes none of them is the operator's to configure in the providers row.
def refuse_untaken_knobs(ears: Running, voice: Running, tuning: Tuning) -> None:
    """Refuse the org's turn and voice knobs that its ears or its voice take under no name."""
    turn = tuning.turn or Turn()
    heard = {
        "endpointing_ms": turn.endpointing_ms,
        "eot_threshold": turn.eot_threshold,
        "eager_eot_threshold": turn.eager_eot_threshold,
    }
    _refuse_untaken("stt", ears, [knob for knob, value in heard.items() if value is not None])
    _refuse_untaken("tts", voice, ["voice"] if tuning.voice is not None else [])


# Every field is one a constructor of the vendor takes, named for a secret and not for where it
# is sent, and a short scalar: nothing a plugin would open, dial or read a file by.
def check_credentials(vendor: str, credentials: Credentials) -> None:
    """Refuse a credentials object that names an address, a file, a session or a field untaken."""
    if not isinstance(credentials, Mapping):
        return
    if len(credentials) > MOST_FIELDS:
        raise ValidationError(f"{vendor} credentials carry {len(credentials)} fields: eight at most")
    taken = _every_parameter(vendor)
    for name, value in credentials.items():
        lowered = name.lower()
        if lowered in NOT_A_CREDENTIAL or lowered.endswith(NOT_A_CREDENTIAL_ENDS):
            raise ValidationError(
                f"{vendor} credentials carry {name!r}: an address, a file or a session is the operator's "
                "to set in the providers row, not a credential"
            )
        if name not in taken:
            fields = ", ".join(sorted(taken)) or "nothing by name"
            raise ValidationError(f"{vendor} takes no credential named {name!r}; its plugin takes {fields}")
        if not isinstance(value, str | int | float | bool) or (
            isinstance(value, str) and (len(value) > LONGEST_VALUE or "://" in value)
        ):
            raise ValidationError(
                f"{vendor} credentials: {name!r} is a string, a number or a boolean of at most 1024 characters"
            )


# A plugin whose classes take no key (an open model run in this process) runs on none: the keyring
# asks nothing of the org or the box for it.
def takes_a_key(vendor: str) -> bool:
    """Whether any class of the vendor's plugin takes a key."""
    return bool(_every_parameter(vendor) & set(THE_KEY))


# The ears that close a turn themselves take the agent's endpointing: a vendor whose STT takes none
# needs a turn model beside it (Smart Turn, LiveKit's) to say when the caller finished.
def ends_turns(vendor: str) -> bool:
    """Whether the vendor's ears take an endpointing of their own."""
    made = getattr(plugin(vendor), CLASS_OF["stt"], None)
    return isinstance(made, type) and bool(_parameters(made) & set(KNOB_NAMES["endpointing_ms"]))


# ── private ──


def _turn_knobs(turn: Turn | None) -> dict[str, object]:
    knobs: dict[str, object] = {} if turn is None else dataclasses.asdict(turn)
    given = {knob: value for knob, value in knobs.items() if value is not None}
    # The agent's endpointing is the silence that closes a turn: the ears that take it call it so.
    if turn is not None and turn.endpointing_ms is not None:
        given["eot_timeout_ms"] = turn.endpointing_ms
    return given


def _refuse_untaken(modality: Modality, running: Running, knobs: list[str]) -> None:
    if not knobs:
        return
    accepts = _parameters(_class_of(modality, running))
    untaken = [knob for knob in knobs if not any(name in accepts for name in KNOB_NAMES[knob])]
    if untaken:
        raise ValidationError(
            f"{running.vendor}'s {modality} takes no {', '.join(untaken)}, so a call would run without it: "
            "leave it out, or pick a vendor that takes it"
        )


# A class may sit in a module of the plugin: `responses.LLM` is its `responses` module's LLM.
def _class_of(modality: Modality, running: Running) -> type:
    module = plugin(running.vendor)
    name = running.builds or class_path(module, modality) or CLASS_OF[modality]
    made: object = module
    for part in name.split("."):
        made = getattr(made, part, None)
    if not isinstance(made, type):
        raise ValidationError(f"{running.vendor} exports no {CLASS_OF[modality]} named {name!r}")
    return made


def _built[T](
    modality: Modality, base: type[T], running: Running, knobs: Mapping[str, object], hear: tuple[str, ...] = ()
) -> T:
    made = _class_of(modality, running)
    named = running.builds or made.__name__
    if not issubclass(made, base):
        raise ValidationError(f"{running.vendor} exports no {CLASS_OF[modality]} named {named!r}")
    constructor: Callable[..., T] = made
    accepts = _parameters(made)
    given: dict[str, object] = {**running.options}
    given |= {knob: value for knob, value in knobs.items() if knob in accepts}
    given |= _credentials(running.credentials, accepts)
    given |= _first(accepts, THE_VOICE, running.voice)
    # A row that names the language wins: a vendor may want the full tag the call cuts to its base.
    if not any(name in running.options for name in THE_LANGUAGE):
        given |= _first(accepts, THE_LANGUAGE, primary_language(running.language))
    given |= _first(accepts, THE_HINTS, list(running.hints) or None)
    if running.model is not None:
        given["model"] = running.model
    plain = dict(given)
    if hear:
        given |= _first(accepts, THE_TERMS, list(hear))
        given |= _inside_its_options(made, accepts, given, running, hear)
    # A plugin raises what it likes when it refuses (SpitchError, a missing variable): each is
    # the vendor refusing its stage, said in its own words. A model that takes no words to expect
    # (Cartesia's ink-whisper refuses `keyterm`) is built without them: the words help, never stop it.
    try:
        return constructor(**_shaped(made, given))
    except Exception as refused:
        if given != plain:
            logger.info("%s %s takes no words to expect (%s): built without them", running.vendor, named, refused)
            try:
                return constructor(**_shaped(made, plain | _inside_its_options(made, accepts, plain, running, ())))
            except Exception as again:
                raise ValidationError(f"{running.vendor} refused its {named}: {again}") from again
        raise ValidationError(f"{running.vendor} refused its {named}: {refused}") from refused


# A plugin that takes its options as one object (Soniox's `params`) finds the language and the words to
# expect there, not among its arguments: the call's language as its hints, the words as its context's
# terms. What the row already put in that object stands.
def _inside_its_options(
    made: type, accepts: frozenset[str], given: Mapping[str, object], running: Running, hear: tuple[str, ...]
) -> dict[str, object]:
    found = _options_object(made)
    if found is None:
        return {}
    name, fields = found
    already = given.get(name)
    if already is not None and not a_mapping(already):
        return {}
    inside: dict[str, object] = dict(already or {})
    language = primary_language(running.language)
    hints = list(running.hints) or ([language] if language else [])
    if hints and not any(each in accepts for each in (*THE_HINTS, *THE_LANGUAGE)):
        for field, value in _first(fields, THE_HINTS, hints).items():
            inside.setdefault(field, value)
    if hear and not any(each in accepts for each in THE_TERMS):
        terms = _first(fields, THE_TERMS, list(hear))
        if terms:
            for field, value in terms.items():
                inside.setdefault(field, value)
        elif A_CONTEXT in fields and A_CONTEXT not in inside:
            inside[A_CONTEXT] = {"terms": list(hear)}
    return {name: inside} if inside else {}


# The argument whose declared type is a dataclass, and that dataclass's fields.
def _options_object(made: type) -> tuple[str, frozenset[str]] | None:
    try:
        declared = inspect.signature(made, eval_str=True).parameters
    except (NameError, TypeError, ValueError):
        return None
    for name, parameter in declared.items():
        shape = _dataclass_in(parameter.annotation)
        if shape is not None:
            return name, frozenset(field.name for field in dataclasses.fields(shape))
    return None


def _every_parameter(vendor: str) -> frozenset[str]:
    module = plugin(vendor)
    taken = frozenset[str]()
    for name in CLASS_OF.values():
        made = getattr(module, name, None)
        if isinstance(made, type):
            taken |= _parameters(made)
    return taken - {"self", "kwargs", "args"}


def _parameters(made: type) -> frozenset[str]:
    try:
        return frozenset(inspect.signature(made).parameters)
    except (TypeError, ValueError):
        return frozenset()


def _credentials(credentials: Credentials, accepts: frozenset[str]) -> dict[str, object]:
    if isinstance(credentials, Mapping):
        return dict(credentials)
    return _first(accepts, THE_KEY, credentials)


def _first(accepts: frozenset[str], names: tuple[str, ...], value: object) -> dict[str, object]:
    chosen = next((name for name in names if name in accepts), None)
    return {} if chosen is None or value is None else {chosen: value}


# A plugin that takes its options as one object (`params=STTOptions(...)`) is given that object,
# built from the row's mapping field by field, however deep.
def _shaped(made: type, given: Mapping[str, object]) -> dict[str, object]:
    try:
        declared = {
            name: parameter.annotation for name, parameter in inspect.signature(made, eval_str=True).parameters.items()
        }
    except (NameError, TypeError):
        return dict(given)
    return {name: _as_declared(declared.get(name), value) for name, value in given.items()}


def _as_declared(declared: object, value: object) -> object:
    shape = _dataclass_in(declared)
    if shape is None or not a_mapping(value):
        return value
    typed = typing.get_type_hints(shape)
    return shape(**{name: _as_declared(typed.get(name), given) for name, given in value.items()})


def _dataclass_in(declared: object) -> type | None:
    if isinstance(declared, type) and dataclasses.is_dataclass(declared):
        return declared
    if isinstance(declared, types.UnionType):
        return next((one for one in typing.get_args(declared) if _dataclass_in(one)), None)
    return None
