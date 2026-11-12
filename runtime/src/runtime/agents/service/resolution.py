"""An agent resolved for a call: the org's settings laid under what its class declares, and a model named in a word."""

import dataclasses
from collections.abc import Mapping
from typing import Any

from runtime.agents.declaration import Declaration
from runtime.agents.settings import AgentSettings, Lexicon
from runtime.enums import Stage
from runtime.exceptions import ValidationError
from runtime.providers import service as providers
from runtime.providers.stage import Model, Voice
from runtime.wire.parts import EndOfTurn

# Model ids carry slashes of their own (`openai/gpt-5` on LiveKit Inference): the first ends the vendor.
SEPARATOR = "/"


# One row per setting the org may set, by the name its class declares it under (`setting_names.SETTINGS`):
# a row left out here is a setting of the org's that no call ever runs, so a test holds the two alike.
def resolve(
    declaration: Declaration, settings: AgentSettings, lexicon: Lexicon, *, defaults: Mapping[Stage, str]
) -> Declaration:
    """The declaration with the org's settings under it: what the class declares wins, the rest is the org's."""
    fixed = declaration.fixed

    def keep[T](name: str, of_the_class: T, of_the_org: T) -> T:
        return of_the_class if name in fixed else of_the_org

    return dataclasses.replace(
        declaration,
        greeting=keep("greeting", declaration.greeting, settings.greeting),
        language=keep(
            "language", declaration.language, declaration.language if settings.language is None else settings.language
        ),
        timezone=keep(
            "timezone", declaration.timezone, declaration.timezone if settings.timezone is None else settings.timezone
        ),
        voice=keep("voice", declaration.voice, _voice(declaration, settings, defaults)),
        stt=keep("stt", declaration.stt, _ears(declaration, settings, defaults)),
        llm=keep("llm", declaration.llm, _thinking(declaration, settings, defaults)),
        realtime=keep("realtime", declaration.realtime, _talking(settings)),
        judge=keep("judge", declaration.judge, _judging(declaration, settings, defaults)),
        hangup=keep("hangup", declaration.hangup, settings.hangup),
        turn=keep("turn", declaration.turn, settings.turn),
        memory=keep("memory", declaration.memory, settings.memory),
        record=keep("record", declaration.record, declaration.record if settings.record is None else settings.record),
        max_duration_s=keep(
            "max_duration_s",
            declaration.max_duration_s,
            declaration.max_duration_s if settings.max_duration_s is None else settings.max_duration_s,
        ),
        llm_timeout_s=keep("llm_timeout_s", declaration.llm_timeout_s, settings.llm_timeout_s),
        silence_timeout_s=keep("silence_timeout_s", declaration.silence_timeout_s, settings.silence_timeout_s),
        idle=keep("idle", declaration.idle, settings.idle),
        voicemail=keep("voicemail", declaration.voicemail, settings.voicemail),
        stt_fallbacks=keep(
            "stt_fallbacks", declaration.stt_fallbacks, _taking_over(settings.stt_fallbacks, Stage.stt, defaults)
        ),
        tts_fallbacks=keep(
            "tts_fallbacks", declaration.tts_fallbacks, _taking_over(settings.tts_fallbacks, Stage.tts, defaults)
        ),
        knowledge=keep("knowledge", declaration.knowledge, settings.knowledge),
        bases=keep("docs", declaration.bases, settings.bases or ()),
        says=keep("says", declaration.says, dict(lexicon.said)),
        hears=keep("hears", declaration.hears, lexicon.heard),
    )


def name_model(text: str | None, stage: Stage, *, in_use: str) -> Model | None:
    """`vendor/model`, a vendor alone (never for `llm`), or a model on the vendor in use; None when none is named."""
    if text is None:
        return None
    word = text.strip()
    vendor, slash, model = word.partition(SEPARATOR)
    if slash:
        return Model(vendor=providers.vendor_doing(vendor.lower(), stage), model=model)
    named = word.lower()
    if providers.is_installed(named):
        if stage is Stage.llm:
            # A vendor has no model of its own to think with: ears and a voice have a default, a model is named.
            raise ValidationError(f"{named} alone names no model: name it, `--llm {named}/<model>`")
        return Model(vendor=providers.vendor_doing(named, stage), model="")
    return Model(vendor=providers.vendor_doing(in_use, stage), model=word)


def check_realtime(named: Model) -> Model:
    """A realtime model on a vendor that has one that hears and speaks itself; refused on any other."""
    vendor = providers.vendor_doing(named.vendor, Stage.llm)
    if not providers.hears_and_speaks(vendor):
        raise ValidationError(
            f"{vendor} has no model that hears and speaks itself: "
            "`pinecall providers` lists, by vendor, the models that do"
        )
    return dataclasses.replace(named, vendor=vendor)


# ── private ──


def _taking_over(named: tuple[str, ...] | None, stage: Stage, defaults: Mapping[Stage, str]) -> tuple[Model, ...]:
    found = (name_model(word, stage, in_use=defaults[stage]) for word in named or ())
    return tuple(model for model in found if model is not None)


def _voice(declaration: Declaration, settings: AgentSettings, defaults: Mapping[Stage, str]) -> Voice | None:
    set_ = (settings.tts, settings.voice, settings.tts_model, settings.tts_builds, settings.tts_options)
    if all(value is None for value in set_):
        return None
    in_use = defaults[Stage.tts] if declaration.voice is None else declaration.voice.vendor
    named = name_model(settings.tts, Stage.tts, in_use=in_use)
    return Voice(
        vendor=in_use if named is None else named.vendor,
        model=settings.tts_model or (None if named is None else named.model or None),
        voice_id=settings.voice,
        builds=settings.tts_builds,
        options=dict(settings.tts_options or {}),
    )


# The model named in one word, with what the org set of its plugin beside it; a vendor nobody named is
# the one in use (the class's, else the row's default) on its own model.
def _with_its_plugin(
    named: Model | None,
    in_use: str,
    *,
    builds: str | None,
    options: Mapping[str, Any] | None,
    temperature: float | None = None,
    end_of_turn: EndOfTurn | None = None,
) -> Model | None:
    if builds is None and options is None and temperature is None and end_of_turn is None:
        return named
    return dataclasses.replace(
        named or Model(vendor=in_use, model=""),
        temperature=temperature,
        builds=builds,
        options=dict(options or {}),
        end_of_turn=end_of_turn,
    )


def _thinking(declaration: Declaration, settings: AgentSettings, defaults: Mapping[Stage, str]) -> Model | None:
    in_use = defaults[Stage.llm] if declaration.llm is None else declaration.llm.vendor
    thinking = _with_its_plugin(
        name_model(settings.llm, Stage.llm, in_use=in_use),
        in_use,
        builds=settings.llm_builds,
        options=settings.llm_options,
        temperature=settings.temperature,
    )
    if thinking is not None:
        providers.refuse_realtime_as_llm(thinking.vendor, thinking.model or None, thinking.builds)
    return thinking


def _judging(declaration: Declaration, settings: AgentSettings, defaults: Mapping[Stage, str]) -> Model | None:
    in_use = defaults[Stage.llm] if declaration.judge is None else declaration.judge.vendor
    named = name_model(settings.judge, Stage.llm, in_use=in_use)
    return _with_its_plugin(named, in_use, builds=settings.judge_builds, options=settings.judge_options)


def _ears(declaration: Declaration, settings: AgentSettings, defaults: Mapping[Stage, str]) -> Model | None:
    in_use = defaults[Stage.stt] if declaration.stt is None else declaration.stt.vendor
    named = name_model(settings.stt, Stage.stt, in_use=in_use)
    return _with_its_plugin(
        named, in_use, builds=settings.stt_builds, options=settings.stt_options, end_of_turn=settings.end_of_turn
    )


# `vendor/model`, or a vendor alone for its plugin's own; a class that declares its realtime keeps it,
# so the settings name one only where the class does not.
def _talking(settings: AgentSettings) -> Model | None:
    if settings.realtime is None:
        if settings.realtime_options is not None:
            raise ValidationError(
                "a realtime model is named as vendor/model, or a vendor alone for its own: xai/grok-voice-3.0, "
                "as `pinecall providers` lists them; its options go with it"
            )
        return None
    vendor, _, model = settings.realtime.strip().partition(SEPARATOR)
    return check_realtime(Model(vendor=vendor.lower(), model=model, options=dict(settings.realtime_options or {})))
