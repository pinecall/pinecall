"""The declaration under the settings: the org's knobs laid over what the class declared, and a model named."""

import dataclasses
from collections.abc import Mapping

from pinecall_runtime.agents.declaration import AgentConfig, Lexicon, Modality, Model, Tuning, Voice
from pinecall_runtime.exceptions import ValidationError
from pinecall_runtime.providers import service as providers
from pinecall_runtime.wire.parts import ModelConfig

# Model ids carry slashes of their own (`openai/gpt-5` on LiveKit Inference): the first ends the vendor.
SEPARATOR = "/"
# A vendor has no model of its own to think with: ears and a voice have a default, a model is named.
NAME_THE_MODEL = "{vendor} alone names no model: name it, `--llm {vendor}/<model>`"
REALTIME_TAKES = (
    "a realtime model takes its vendor and model, and its options: @realtime('<vendor>/<model>', { options })"
)
REALTIME_NAMES = (
    "a realtime model is named as vendor/model, or a vendor alone for its own: xai/grok-voice-3.0, "
    "as `pinecall providers` lists them; its options go with it"
)


def apply_tuning(
    declared: AgentConfig, tuning: Tuning, lexicon: Lexicon, *, defaults: Mapping[Modality, str]
) -> AgentConfig:
    """The declaration with the org's settings over it, and the class's own over those."""
    fixed = declared.fixed

    def kept[T](name: str, declared_value: T, set_value: T) -> T:
        return declared_value if name in fixed else set_value

    return dataclasses.replace(
        declared,
        greeting=kept("greeting", declared.greeting, tuning.greeting),
        language=kept("language", declared.language, declared.language if tuning.language is None else tuning.language),
        voice=kept("voice", declared.voice, _voice(declared, tuning, defaults)),
        stt=kept("stt", declared.stt, _ears(declared, tuning, defaults)),
        llm=kept("llm", declared.llm, _thinking(declared, tuning, defaults)),
        realtime=kept("realtime", declared.realtime, _talking(tuning)),
        judge=kept("judge", declared.judge, _judging(declared, tuning, defaults)),
        hangup=kept("hangup", declared.hangup, tuning.hangup),
        turn=kept("turn", declared.turn, tuning.turn),
        memory=kept("memory", declared.memory, tuning.memory),
        record=kept("record", declared.record, declared.record if tuning.record is None else tuning.record),
        max_duration_s=kept(
            "max_duration_s",
            declared.max_duration_s,
            declared.max_duration_s if tuning.max_duration_s is None else tuning.max_duration_s,
        ),
        llm_timeout_s=kept("llm_timeout_s", declared.llm_timeout_s, tuning.llm_timeout_s),
        knowledge=kept("knowledge", declared.knowledge, tuning.knowledge),
        bases=kept("docs", declared.bases, tuning.bases or ()),
        says=kept("says", declared.says, dict(lexicon.said)),
        hears=kept("hears", declared.hears, lexicon.heard),
    )


def model_from_wire(wanted: ModelConfig | None, modality: Modality) -> Model | None:
    """A model as the wire names it, its vendor checked for the stage; an LLM never one that hears and speaks itself."""
    if wanted is None:
        return None
    if wanted.end_of_turn is not None and modality != "stt":
        raise ValidationError(f"end_of_turn is the ears': @stt('<vendor>', {{ endOfTurn: '{wanted.end_of_turn}' }})")
    made = Model(
        provider=providers.vendor_doing(wanted.provider.lower(), modality),
        model=wanted.model,
        temperature=wanted.temperature,
        builds=wanted.builds,
        options=dict(wanted.options or {}),
        end_of_turn=wanted.end_of_turn,
    )
    if modality == "llm":
        providers.refuse_realtime_as_llm(made.provider, made.model or None, made.builds)
    return made


# A realtime model is named by vendor and model and takes its options; its class is the plugin's
# realtime one, never named, and its temperature is the vendor's.
def realtime_from_wire(wanted: ModelConfig | None) -> Model | None:
    """The realtime model a class declares, its vendor checked for one that hears and speaks itself."""
    if wanted is None:
        return None
    if wanted.builds is not None or wanted.temperature is not None or wanted.end_of_turn is not None:
        raise ValidationError(REALTIME_TAKES)
    return _realtime_checked(
        Model(provider=wanted.provider.lower(), model=wanted.model, options=dict(wanted.options or {}))
    )


def model_named(text: str | None, modality: Modality, *, in_use: str) -> Model | None:
    """`vendor/model`, a vendor alone (never for `llm`), or a model on the vendor in use; None when none is named."""
    if text is None:
        return None
    word = text.strip()
    vendor, slash, model = word.partition(SEPARATOR)
    if slash:
        return Model(provider=providers.vendor_doing(vendor.lower(), modality), model=model)
    if providers.is_installed(word.lower()):
        if modality == "llm":
            raise ValidationError(NAME_THE_MODEL.format(vendor=word.lower()))
        return Model(provider=providers.vendor_doing(word.lower(), modality), model="")
    return Model(provider=providers.vendor_doing(in_use, modality), model=word)


# ── private ──


def _voice(declared: AgentConfig, tuning: Tuning, defaults: Mapping[Modality, str]) -> Voice | None:
    knobs = (tuning.tts, tuning.voice, tuning.tts_model, tuning.tts_builds, tuning.tts_options)
    if all(knob is None for knob in knobs):
        return None
    in_use = defaults["tts"] if declared.voice is None else declared.voice.provider
    named = model_named(tuning.tts, "tts", in_use=in_use)
    provider = in_use if named is None else named.provider
    model = tuning.tts_model or (None if named is None else named.model or None)
    return Voice(
        provider=provider,
        model=model,
        voice_id=tuning.voice,
        builds=tuning.tts_builds,
        options=dict(tuning.tts_options or {}),
    )


def _thinking(declared: AgentConfig, tuning: Tuning, defaults: Mapping[Modality, str]) -> Model | None:
    in_use = defaults["llm"] if declared.llm is None else declared.llm.provider
    named = model_named(tuning.llm, "llm", in_use=in_use)
    if all(knob is None for knob in (tuning.temperature, tuning.llm_builds, tuning.llm_options)):
        thinking = named
    else:
        thinking = dataclasses.replace(
            named or Model(provider=in_use, model=""),
            temperature=tuning.temperature,
            builds=tuning.llm_builds,
            options=dict(tuning.llm_options or {}),
        )
    if thinking is not None:
        providers.refuse_realtime_as_llm(thinking.provider, thinking.model or None, thinking.builds)
    return thinking


# `vendor/model`, or a vendor alone for its plugin's own; a class that declares its realtime keeps it,
# so the settings name one only where the class does not.
def _talking(tuning: Tuning) -> Model | None:
    if tuning.realtime is None:
        if tuning.realtime_options is not None:
            raise ValidationError(REALTIME_NAMES)
        return None
    vendor, _, model = tuning.realtime.strip().partition(SEPARATOR)
    return _realtime_checked(Model(provider=vendor.lower(), model=model, options=dict(tuning.realtime_options or {})))


def _realtime_checked(named: Model) -> Model:
    vendor = providers.vendor_doing(named.provider, "llm")
    if not providers.hears_and_speaks(vendor):
        raise ValidationError(f"{vendor} has no model that hears and speaks itself: {providers.NOT_REALTIME}")
    return dataclasses.replace(named, provider=vendor)


def _judging(declared: AgentConfig, tuning: Tuning, defaults: Mapping[Modality, str]) -> Model | None:
    in_use = defaults["llm"] if declared.judge is None else declared.judge.provider
    named = model_named(tuning.judge, "llm", in_use=in_use)
    if tuning.judge_builds is None and tuning.judge_options is None:
        return named
    return dataclasses.replace(
        named or Model(provider=in_use, model=""), builds=tuning.judge_builds, options=dict(tuning.judge_options or {})
    )


def _ears(declared: AgentConfig, tuning: Tuning, defaults: Mapping[Modality, str]) -> Model | None:
    in_use = defaults["stt"] if declared.stt is None else declared.stt.provider
    named = model_named(tuning.stt, "stt", in_use=in_use)
    if all(knob is None for knob in (tuning.stt_builds, tuning.stt_options, tuning.end_of_turn)):
        return named
    return dataclasses.replace(
        named or Model(provider=in_use, model=""),
        builds=tuning.stt_builds,
        options=dict(tuning.stt_options or {}),
        end_of_turn=tuning.end_of_turn,
    )
