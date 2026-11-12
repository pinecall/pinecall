"""A stage built from its Running: the plugin's class called with the key, the model and the knobs, in a call or out."""

import dataclasses
import logging
from collections.abc import AsyncGenerator, Callable, Mapping, Sequence
from contextlib import asynccontextmanager
from typing import Never

from livekit import rtc
from livekit.agents import llm, stt, tts, vad
from livekit.agents.utils import http_context

from runtime.enums import Stage
from runtime.exceptions import ValidationError
from runtime.kit.text import a_mapping
from runtime.providers.service import signatures
from runtime.providers.service.committed_ears import CommittedByVAD
from runtime.providers.service.llm_requests import LLMWithRequest
from runtime.providers.service.plugins import A_TTS, AN_LLM, AN_STT, CLASS_OF, NOT_REALTIME, plugin, realtime_path
from runtime.providers.service.signatures import (
    A_CONTEXT,
    THE_HINTS,
    THE_KEY,
    THE_LANGUAGE,
    THE_MODEL,
    THE_TERMS,
    THE_VOICE,
    TurnKnobs,
    first_of,
    options_object,
    parameters_of,
    shape_arguments,
)
from runtime.providers.stage import Credentials, Ears, Running, Speaking, Thinking, primary_language

logger = logging.getLogger(__name__)

# 16-bit PCM at the rate every plugin takes, as a note is recorded and a stage outside a call is fed.
SAMPLE_WIDTH = 2
A_RATE = 16_000

type Arguments = Mapping[str, object]


# ── one stage ──


def llm_of(running: Running) -> llm.LLM[Never]:
    """The LLM a stage runs: the plugin's class called with the key, the model and the options."""
    return LLMWithRequest(_build(Stage.llm, AN_LLM, running, {}), running.request)


def tts_of(running: Running) -> tts.TTS[Never]:
    """The voice a stage speaks with, its voice and language under the names its plugin uses."""
    return _build(Stage.tts, A_TTS, running, {})


def stt_of(running: Running, turn: TurnKnobs | None, hear: Sequence[str] = ()) -> stt.STT[Never]:
    """The ears a stage hears with: the turn's knobs where they take them, the words to expect as they name them."""
    return _build(Stage.stt, AN_STT, running, signatures.knobs_of(turn), tuple(hear))


# A model that hears and speaks itself (xAI's Grok Voice, OpenAI's Realtime API) stands for the whole
# conversation of a voice call: no ears, its own voice. It is the agent's `realtime`, built by the
# plugin's realtime class (`realtime.RealtimeModel`) whatever the row names for the vendor's LLM.
def build_realtime(running: Running) -> llm.RealtimeModel:
    """The realtime model a voice call runs on alone."""
    path = realtime_path(plugin(running.vendor))
    if path is None:
        raise ValidationError(f"{running.vendor} has no model that hears and speaks itself: {NOT_REALTIME}")
    return _build(Stage.llm, llm.RealtimeModel, dataclasses.replace(running, builds=path), {})


# ── a call's stages, over who takes over ──


# A call's three stages: with no fallback, exactly the plugin's object; with some, livekit's
# FallbackAdapter over the stage and the vendors that take over, in order. The relay between
# vendors is livekit's; here it is only decided who enters the chain.
def build_thinking(running: Running) -> Thinking:
    """The LLM a call thinks with, over its fallbacks when the stage names any."""
    primary = llm_of(running)
    if not running.fallbacks:
        return primary
    return llm.FallbackAdapter([primary, *(llm_of(fallback) for fallback in running.fallbacks)])


# livekit's adapter wraps ears that do not stream with a VAD the session does not hold, and refuses
# voices of another channel count: such a fallback is left out and the call runs on the rest.
def build_ears(
    running: Running, turn: TurnKnobs | None, hear: Sequence[str] = (), hearing: vad.VAD | None = None
) -> Ears:
    """The ears a call hears with, over the fallbacks that stream; where they wait to be told, the VAD tells them."""
    primary = stt_of(running, turn, hear)
    if hearing is not None and running.commits_when_told:
        primary = CommittedByVAD(primary, hearing)
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


# ── a stage outside a call ──


# Outside a call there is no job to lend the plugins its HTTP session, and nobody to close the plugin:
# each of these opens the one and guarantees the other, whatever the block raises. livekit's errors
# pass through untouched: the use case that opened the stage says the vendor's no (`refusing`).
@asynccontextmanager
async def thinking_outside_a_call(running: Running) -> AsyncGenerator[llm.LLM[Never]]:
    """The stage's LLM built as a call builds it, on an HTTP session of its own, and closed after."""
    async with http_context.open():
        model = llm_of(running)
        try:
            yield model
        finally:
            await model.aclose()


@asynccontextmanager
async def ears_outside_a_call(
    running: Running, turn: TurnKnobs | None = None, hear: Sequence[str] = ()
) -> AsyncGenerator[stt.STT[Never]]:
    """The stage's ears built as a call builds them, on an HTTP session of their own, and closed after."""
    async with http_context.open():
        ears = stt_of(running, turn, hear)
        try:
            yield ears
        finally:
            await ears.aclose()


@asynccontextmanager
async def voice_outside_a_call(running: Running) -> AsyncGenerator[tts.TTS[Never]]:
    """The stage's voice built as a call builds it, on an HTTP session of its own, and closed after."""
    async with http_context.open():
        voice = tts_of(running)
        try:
            yield voice
        finally:
            await voice.aclose()


def silence(ms: int, rate: int = A_RATE, channels: int = 1) -> rtc.AudioFrame:
    """A frame of that much silence: what opens the ears, or lets them settle their last words."""
    samples = rate * ms // 1000
    return rtc.AudioFrame(bytes(samples * channels * SAMPLE_WIDTH), rate, channels, samples)


# ── private: the constructor called ──


def _build[T](stage: Stage, base: type[T], running: Running, knobs: Arguments, hear: tuple[str, ...] = ()) -> T:
    made = signatures.class_of(stage, running)
    named = running.builds or made.__name__
    if not issubclass(made, base):
        raise ValidationError(f"{running.vendor} exports no {CLASS_OF[stage]} named {named!r}")
    constructor: Callable[..., T] = made
    accepts = parameters_of(made)
    plain = _with_model(stage, made, accepts, _name_arguments(running, accepts, knobs), running)
    told = _with_terms(made, accepts, plain, running, hear)
    without = None if told == plain else {**plain, **_inside_its_options(made, accepts, plain, running, ())}
    return _construct(constructor, made, told, without, f"{running.vendor} refused its {named}")


# What the runtime knows, under the name this plugin takes each: the row's options, the turn's knobs,
# the key, the voice, the language and the hints.
def _name_arguments(running: Running, accepts: frozenset[str], knobs: Arguments) -> dict[str, object]:
    given: dict[str, object] = {**running.options}
    given |= {knob: value for knob, value in knobs.items() if knob in accepts}
    given |= _credentials(running.credentials, accepts)
    given |= first_of(accepts, THE_VOICE, running.voice)
    # A row that names the language wins: a vendor may want the full tag the call cuts to its base.
    if not any(name in running.options for name in THE_LANGUAGE):
        given |= first_of(accepts, THE_LANGUAGE, primary_language(running.language))
    # And one that names the hints: Deepgram's `flux-general-en` takes none, and the row says so.
    if not any(name in running.options for name in THE_HINTS):
        given |= first_of(accepts, THE_HINTS, list(running.hints) or None)
    return given


def _with_model(
    stage: Stage, made: type, accepts: frozenset[str], given: dict[str, object], running: Running
) -> dict[str, object]:
    if running.model is not None:
        given = given | _the_model(made, accepts, given, running.model)
    # A voice whose plugin takes no voice argument is the model it speaks with: Deepgram's voices are
    # its models (`aura-2-celeste-es`), so a voice the row keeps per language reaches it this way.
    if stage is Stage.tts and running.voice is not None and not accepts & set(THE_VOICE):
        given = given | {THE_MODEL: running.voice}
    return given


def _with_terms(
    made: type, accepts: frozenset[str], plain: dict[str, object], running: Running, hear: tuple[str, ...]
) -> dict[str, object]:
    if not hear:
        return plain
    told = plain | first_of(accepts, THE_TERMS, list(hear))
    return told | _inside_its_options(made, accepts, told, running, hear)


# A plugin raises what it likes when it refuses (SpitchError, a missing variable): each is the vendor
# refusing its stage, said in its own words. A model that takes no words to expect (Cartesia's
# ink-whisper refuses `keyterm`) is built without them: the words help, never stop it.
def _construct[T](
    constructor: Callable[..., T], made: type, told: Arguments, without_terms: Arguments | None, refused_as: str
) -> T:
    try:
        return constructor(**shape_arguments(made, told))
    except Exception as refused:
        if without_terms is None:
            raise ValidationError(f"{refused_as}: {refused}") from refused
        logger.info("%s, which takes no words to expect (%s): built without them", refused_as, refused)
    try:
        return constructor(**shape_arguments(made, without_terms))
    except Exception as again:
        raise ValidationError(f"{refused_as}: {again}") from again


# The model named, where the plugin takes it: its `model` argument, or the `model` of the one options
# object it takes instead (Soniox's `params=STTOptions(model=…)`), beside what the row put there. A
# plugin that takes neither is handed the argument, and refuses it in its own words. Soniox was handed
# `model=` and refused it, so every call that named a Soniox model never started (2026-11-05).
def _the_model(made: type, accepts: frozenset[str], given: Arguments, model: str) -> dict[str, object]:
    found = None if THE_MODEL in accepts else options_object(made)
    if found is None or THE_MODEL not in found[1]:
        return {THE_MODEL: model}
    name = found[0]
    already = given.get(name)
    if already is not None and not a_mapping(already):
        return {}
    return {name: {**dict(already or {}), THE_MODEL: model}}


# A plugin that takes its options as one object (Soniox's `params`) finds the language and the words to
# expect there, not among its arguments: the call's language as its hints, the words as its context's
# terms. What the row already put in that object stands.
def _inside_its_options(
    made: type, accepts: frozenset[str], given: Arguments, running: Running, hear: tuple[str, ...]
) -> dict[str, object]:
    found = options_object(made)
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
        for field, value in first_of(fields, THE_HINTS, hints).items():
            inside.setdefault(field, value)
    if hear and not any(each in accepts for each in THE_TERMS):
        terms = first_of(fields, THE_TERMS, list(hear))
        if terms:
            for field, value in terms.items():
                inside.setdefault(field, value)
        elif A_CONTEXT in fields and A_CONTEXT not in inside:
            inside[A_CONTEXT] = {"terms": list(hear)}
    return {name: inside} if inside else {}


def _credentials(credentials: Credentials, accepts: frozenset[str]) -> dict[str, object]:
    if isinstance(credentials, Mapping):
        return dict(credentials)
    return first_of(accepts, THE_KEY, credentials)
