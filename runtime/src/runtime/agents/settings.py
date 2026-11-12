"""What the org sets on an agent, over what its class declares: its settings, its lexicon, and how each is kept."""

import dataclasses
from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
from typing import Any, TypeIs

from runtime.agents.declaration import (
    BLANK,
    DEFAULT_CHUNKS_PER_TURN,
    NOT_A_TIMEOUT,
    Docs,
    Greeting,
    Hangup,
    Idle,
    MemoryPolicy,
    Turn,
    Voicemail,
    check_call_limit,
    check_parts,
    check_pronunciations,
    check_silence,
)
from runtime.exceptions import ValidationError
from runtime.kit.text import a_mapping
from runtime.kit.time import parse_zone
from runtime.wire.declaration import IDLE_AFTER_S, IDLE_TIMES
from runtime.wire.parts import EndOfTurn


# The table that keeps it is `agent_config` and its API says `config`; in here the word is settings.
@dataclass(frozen=True, slots=True)
class AgentSettings:
    """One agent's settings as the org set them; every field is None until set."""

    voice: str | None = None
    tts: str | None = None
    tts_model: str | None = None
    stt: str | None = None
    llm: str | None = None
    temperature: float | None = None
    end_of_turn: EndOfTurn | None = None
    llm_builds: str | None = None
    llm_options: Mapping[str, Any] | None = None
    # The model a voice call runs on alone, hearing and speaking itself; a written call keeps `llm`.
    realtime: str | None = None
    realtime_options: Mapping[str, Any] | None = None
    stt_builds: str | None = None
    stt_options: Mapping[str, Any] | None = None
    tts_builds: str | None = None
    tts_options: Mapping[str, Any] | None = None
    judge: str | None = None
    judge_builds: str | None = None
    judge_options: Mapping[str, Any] | None = None
    language: str | None = None
    # The IANA zone whose day and hour the agent's calls open on; unset, the gateway's day and no hour.
    timezone: str | None = None
    greeting: Greeting | None = None
    hangup: Hangup | None = None
    turn: Turn | None = None
    memory: MemoryPolicy | None = None
    record: bool | None = None
    max_duration_s: int | None = None
    llm_timeout_s: float | None = None
    knowledge: str | None = None
    bases: tuple[Docs, ...] | None = None
    # Seconds of a caller saying nothing before the call ends; unset never ends it for that.
    silence_timeout_s: int | None = None
    idle: Idle | None = None
    voicemail: Voicemail | None = None
    # The vendors that take over a stage, `vendor` or `vendor/model`, in order: over the row's own.
    stt_fallbacks: tuple[str, ...] | None = None
    tts_fallbacks: tuple[str, ...] | None = None


@dataclass(frozen=True, slots=True)
class Lexicon:
    """An agent's lexicon: TTS pronunciations and STT keyterms."""

    said: Mapping[str, str] = field(default_factory=dict[str, str])
    heard: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class Versions:
    """The versions of its settings and of its lexicon a call was built on; None where nothing was set."""

    settings: int | None = None
    lexicon: int | None = None


FIELDS: tuple[str, ...] = tuple(one.name for one in dataclasses.fields(AgentSettings))
# The text fields: one set to nothing but spaces is refused, never kept.
TEXT_FIELDS: tuple[str, ...] = tuple(one.name for one in dataclasses.fields(AgentSettings) if one.type == (str | None))


# ── what a write refuses ──


# Called where settings are written, never where they are read: a row kept before a rule was made
# stricter still reads, and its agent's calls are still built.
def check_settings(settings: AgentSettings) -> AgentSettings:
    """Refuse settings no call could run on: a blank, a zone that is none, a limit out of range, a part by its rule."""
    for name in TEXT_FIELDS:
        value: str | None = getattr(settings, name)
        if value is not None and not value.strip():
            raise ValidationError(BLANK.format(field=name))
    if settings.timezone is not None:
        parse_zone(settings.timezone)
    if settings.max_duration_s is not None:
        check_call_limit(settings.max_duration_s)
    if settings.silence_timeout_s is not None:
        check_silence(settings.silence_timeout_s)
    if any(not word.strip() for word in (*(settings.stt_fallbacks or ()), *(settings.tts_fallbacks or ()))):
        raise ValidationError(BLANK.format(field="fallback"))
    if settings.llm_timeout_s is not None and settings.llm_timeout_s <= 0:
        raise ValidationError(NOT_A_TIMEOUT)
    if settings.temperature is not None and settings.temperature < 0:
        raise ValidationError("temperature is a number from 0, in the model vendor's range")
    check_parts(
        turn=settings.turn,
        greeting=settings.greeting,
        idle=settings.idle,
        voicemail=settings.voicemail,
        memory=settings.memory,
        bases=settings.bases or (),
    )
    return settings


def check_lexicon(lexicon: Lexicon) -> Lexicon:
    """Refuse a lexicon with a blank word, a blank spoken form, or a blank word for the ears."""
    check_pronunciations(lexicon.said, "the lexicon")
    if any(not word.strip() for word in lexicon.heard):
        raise ValidationError("the lexicon: a word the ears must know is not blank")
    return lexicon


# ── as it is kept ──


def _greeting(kept: Mapping[str, Any]) -> Greeting:
    return Greeting(kept.get("say"), kept.get("reply"), kept.get("allow_interruptions"))


def _hangup(kept: Mapping[str, Any]) -> Hangup:
    return Hangup(kept.get("when", ""))


def _turn(kept: Mapping[str, Any]) -> Turn:
    return Turn(**{one.name: kept.get(one.name) for one in dataclasses.fields(Turn)})


def _memory(kept: Mapping[str, Any]) -> MemoryPolicy:
    return MemoryPolicy(tuple(kept.get("remember", ())), tuple(kept.get("forget", ())))


def _bases(kept: list[Mapping[str, Any]]) -> tuple[Docs, ...]:
    return tuple(
        Docs(one["base"], one.get("mode", "retrieved"), one.get("k", DEFAULT_CHUNKS_PER_TURN), one.get("min_score"))
        for one in kept
    )


def _idle(kept: Mapping[str, Any]) -> Idle:
    return Idle(tuple(kept["says"]), kept.get("after_s", IDLE_AFTER_S), kept.get("times", IDLE_TIMES))


def _voicemail(kept: Mapping[str, Any]) -> Voicemail:
    return Voicemail(kept.get("message"))


# The fields that are kept as an object or a list, each with what reads it back; every other is kept as it is.
PARTS: Mapping[str, Callable[[Any], object]] = {
    "greeting": _greeting,
    "hangup": _hangup,
    "turn": _turn,
    "memory": _memory,
    "bases": _bases,
    "idle": _idle,
    "voicemail": _voicemail,
    "stt_fallbacks": tuple,
    "tts_fallbacks": tuple,
}


# A field the row holds and this release does not know is left out, not refused: while two releases
# run side by side, each reads the rows the other wrote.
def read_settings(kept: Mapping[str, Any]) -> AgentSettings:
    """The settings a kept row or a body's fields say, given their shape and nothing else: no rule is asked."""
    read: dict[str, Any] = {}
    for name in FIELDS:
        value = kept.get(name)
        read[name] = PARTS[name](value) if value is not None and name in PARTS else value
    return AgentSettings(**read)


def dump_settings(settings: AgentSettings) -> dict[str, Any]:
    """Settings as they are kept and sent: each field set, by its name, as JSON values."""
    return {name: _plain(value) for name in FIELDS if (value := getattr(settings, name)) is not None}


# A part's own unset fields are left out, as the release before 2026-11 kept them; a plugin's options are
# the org's own object and kept as it wrote them.
def _plain(value: object) -> object:
    if dataclasses.is_dataclass(value) and not isinstance(value, type):
        parts = ((one.name, getattr(value, one.name)) for one in dataclasses.fields(value))
        return {name: _plain(part) for name, part in parts if part is not None}
    if _a_tuple(value):
        return [_plain(one) for one in value]
    if a_mapping(value):
        return dict(value)
    return value


# What `isinstance` leaves as a tuple of nothing known; this says what it holds, once.
def _a_tuple(value: object) -> TypeIs[tuple[object, ...]]:
    return isinstance(value, tuple)
