"""A declaration: read off the wire, laid over what was declared before, checked, kept per scope, and found one way."""

import dataclasses
from collections.abc import Callable, Mapping, Sequence
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from runtime.actor import Scope
from runtime.agents.declaration import (
    DEFAULT_LAYOUT,
    DEFAULT_TOOL_TIMEOUT_S,
    DELAYED_AFTER_S,
    Agent,
    Declaration,
    Docs,
    Greeting,
    Hangup,
    Idle,
    MemoryPolicy,
    PromptBlock,
    ToolSpec,
    Turn,
    Voicemail,
    check_words,
)
from runtime.agents.repository import DeclarationRepository
from runtime.agents.service.hold_audio import check_wait
from runtime.agents.service.resolution import SEPARATOR, check_realtime
from runtime.agents.service.setting_names import FIELD_OF
from runtime.agents.service.widgets import check_look, look_of
from runtime.enums import Stage
from runtime.exceptions import ValidationError
from runtime.providers import service as providers
from runtime.providers.stage import Model, Voice
from runtime.wire import declaration as wire

NO_VENDOR = (
    "a voice names its vendor and the voice: `provider` and `voice_id` (or `name`) on the wire, "
    "@voice('<vendor>', '<voice>') in a class"
)
REALTIME_TAKES = (
    "a realtime model takes its vendor and model, and its options: @realtime('<vendor>/<model>', { options })"
)
ONE_OF_DOCS = "docs is one base and bases is several: declare one of them"


# ── what an app declares, as a value ──


# Sent as null, a setting goes back to the org's; left out, it stays as it was declared before. A
# socket's first declaration is the class whole: a setting it leaves out is the class's no longer,
# though the process before it declared it (a save that took `language` out, 2026-10-24).
#
# This gives the declaration its shape and refuses nothing: it is also how a kept row is read back,
# and a row kept before a rule was made stricter, or naming a vendor since taken out, still reads
# (until 2026-11 it did not, and no call of that agent could be built). `declare` is what a socket calls.
def apply_declaration(current: Declaration, sent: wire.AgentConfig, *, first: bool = False) -> Declaration:
    """The declaration with the fields the app sent in place, and the settings it fixes."""
    named = sent.model_fields_set
    changed = _fix_settings(current, sent, first=first)
    if "prompt" in named:
        changed["prompt"] = (
            tuple(PromptBlock(block.name, block.region) for block in sent.prompt) if sent.prompt else DEFAULT_LAYOUT
        )
    if "uses_knowledge" in named:
        changed["uses_knowledge"] = bool(sent.uses_knowledge)
    if "tools" in named:
        changed["tools"] = tuple(
            ToolSpec(
                name=tool.name,
                description=tool.description,
                parameters=tool.parameters,
                side_effect=tool.side_effect,
                pii=frozenset(tool.pii or ()),
                confirm=tool.confirm,
                announce=tool.announce,
                delayed=tool.delayed,
                delayed_after_s=DELAYED_AFTER_S if tool.delayed_after_s is None else tool.delayed_after_s,
                failed=tool.failed,
                timeout_s=DEFAULT_TOOL_TIMEOUT_S if tool.timeout_s is None else tool.timeout_s,
                quiet=bool(tool.quiet),
            )
            for tool in sent.tools or ()
        )
    if "state_fields" in named:
        changed["state_fields"] = {item.name: item.visibility for item in sent.state_fields or ()}
    if "view" in named:
        changed["view"] = None if sent.view is None else sent.view.name
    if "events" in named:
        changed["events"] = {item.name: frozenset(item.from_) for item in sent.events or ()}
    return dataclasses.replace(current, **changed)


# Checked where an app declares itself, not first on a call: a vendor nobody installed, a tool no
# model could call or a wait out of its band is refused at agent.configure, in its sentence.
def check_declaration(declaration: Declaration) -> Declaration:
    """Refuse a declaration no call could run: its words, each stage's vendor, its melody, its look, its monitors."""
    check_words(declaration)
    if declaration.voice is not None:
        _check_voice(declaration.voice)
    for stage, named in ((Stage.llm, declaration.llm), (Stage.stt, declaration.stt), (Stage.llm, declaration.judge)):
        if named is not None:
            _check_model(named, stage)
    if declaration.realtime is not None:
        _check_realtime(declaration.realtime)
    for stage, taking_over in ((Stage.stt, declaration.stt_fallbacks), (Stage.tts, declaration.tts_fallbacks)):
        for named in taking_over:
            providers.vendor_doing(named.vendor, stage)
    if declaration.hold is not None and declaration.hold.after_s is not None:
        check_wait(declaration.hold.after_s)
    if declaration.widget is not None:
        check_look(look_of(declaration.widget))
    names = [one.name for one in declaration.monitors or ()]
    if repeated := sorted({name for name in names if names.count(name) > 1}):
        raise ValidationError(f"monitor names repeat: {repeated}")
    return declaration


def declare(current: Declaration, sent: wire.AgentConfig, *, first: bool = False) -> Declaration:
    """What an app's agent.configure makes of the declaration it held: the fields sent in place, checked whole."""
    if sent.docs is not None and sent.bases is not None:
        raise ValidationError(ONE_OF_DOCS)
    return check_declaration(apply_declaration(current, sent, first=first))


def list_changes(sent: wire.AgentConfig) -> list[str]:
    """The fields a declaration sets, sorted."""
    return sorted(sent.model_fields_set)


def read_model(wanted: wire.ModelConfig | None, stage: Stage) -> Model | None:
    """A model as the wire names it, its vendor checked for the stage; an LLM never one that hears and speaks itself."""
    return None if wanted is None else _check_model(_model_of(wanted), stage)


# ── kept per scope, and found one way ──


# A socket's first declaration is the class whole and replaces the row; a later one changes the
# fields it sends, as the declaration its socket holds changes, so the row reads as that one does.
async def put_declaration(
    session: AsyncSession, scope: Scope, slug: str, sent: wire.AgentConfig, *, sdk: str | None, first: bool
) -> dict[str, Any]:
    """Keep what the app declared of the agent as the scope's, merged into what it declared before; the row's body."""
    repository = DeclarationRepository(session)
    body = sent.dump()
    before = None if first else await repository.find_own(scope, slug)
    merged = body if before is None else {**before.declaration, **body}
    await repository.put(scope, slug, merged, sdk)
    return merged


# The one answer to "what does the class of this agent declare": the scope's own row, else the org's
# own in the env. Until 2026-11 there were four (any scope with production first, the scope's newest
# holder, its newest taker, the kept row), so the settings screen and the call it configured could
# disagree on what the class fixes: a field the calls ignored was written, or one they would run refused.
async def declaration_of(session: AsyncSession, scope: Scope, slug: str) -> Declaration | None:
    """The agent as the scope's last app declared it (the org's own when the scope never did), or None."""
    row = await DeclarationRepository(session).find(scope, slug)
    if row is None:
        return None
    return apply_declaration(Declaration(slug=slug), wire.AgentConfig.model_validate(row.declaration), first=True)


async def agent_of(session: AsyncSession, scope: Scope, slug: str) -> Agent:
    """The agent by its slug with what its class declares in the scope."""
    return Agent(slug, await declaration_of(session, scope, slug))


# ── private: what the class fixes ──


# A setting the class declares is fixed: the org's settings no longer move it. Only what was sent, or
# what a first declaration lets go of, is converted.
def _fix_settings(current: Declaration, sent: wire.AgentConfig, *, first: bool) -> dict[str, Any]:
    changed: dict[str, Any] = {}
    fixed = set(current.fixed)
    named = _names_sent(sent) & VALUE_OF.keys()
    let_go = (fixed - named) if first else set[str]()
    for name in sorted(named | let_go):
        field = FIELD_OF[name]
        if name in let_go or _value_sent(sent, name) is None:
            # The class lets go of it: the field holds no value of its own, and the org's settings fill it.
            fixed.discard(name)
            changed[field] = _default_of(field)
            continue
        fixed.add(name)
        changed[field] = VALUE_OF[name](sent)
    changed["fixed"] = frozenset(fixed)
    return changed


# `bases` is `docs` said for several: one setting, however the class says it.
def _names_sent(sent: wire.AgentConfig) -> set[str]:
    return {"docs" if name == "bases" else name for name in sent.model_fields_set}


def _value_sent(sent: wire.AgentConfig, name: str) -> object:
    return getattr(sent, name) if name != "docs" or sent.bases is None else sent.bases


def _default_of(field: str) -> object:
    found = next(item for item in dataclasses.fields(Declaration) if item.name == field)
    if found.default_factory is not dataclasses.MISSING:
        return found.default_factory()
    return found.default


def _bases_of(sent: wire.AgentConfig) -> tuple[Docs, ...]:
    wanted = sent.bases if sent.bases is not None else [sent.docs] if sent.docs else []
    return tuple(Docs(base=one.base, mode=one.mode, k=one.k, min_score=one.min_score) for one in wanted)


def _voice_of(wanted: wire.VoiceConfig | None) -> Voice | None:
    if wanted is None:
        return None
    return Voice(
        vendor=(wanted.provider or "").lower(),
        model=wanted.model,
        voice_id=wanted.voice_id or wanted.name,
        builds=wanted.builds,
        options=dict(wanted.options or {}),
    )


def _model_of(wanted: wire.ModelConfig) -> Model:
    return Model(
        vendor=wanted.provider.lower(),
        model=wanted.model,
        temperature=wanted.temperature,
        builds=wanted.builds,
        options=dict(wanted.options or {}),
        end_of_turn=wanted.end_of_turn,
    )


def _models_of(words: Sequence[str] | None) -> tuple[Model, ...]:
    named = (word.strip().partition(SEPARATOR) for word in words or ())
    return tuple(Model(vendor=vendor.lower(), model=model) for vendor, _, model in named)


def _greeting_of(wanted: wire.GreetingConfig | None) -> Greeting | None:
    return None if wanted is None else Greeting(wanted.say, wanted.reply, wanted.allow_interruptions)


def _turn_of(wanted: wire.TurnConfig | None) -> Turn | None:
    return None if wanted is None else Turn(**wanted.model_dump())


def _memory_of(wanted: wire.MemoryConfig | None) -> MemoryPolicy | None:
    return None if wanted is None else MemoryPolicy(remember=tuple(wanted.remember), forget=tuple(wanted.forget))


def _idle_of(wanted: wire.IdleConfig | None) -> Idle | None:
    return None if wanted is None else Idle(tuple(wanted.says), wanted.after_s, wanted.times)


# Each setting a class may declare, by the declaration's name, as the value its field holds; the names
# are `setting_names.SETTINGS`', and a test holds the two alike.
VALUE_OF: Mapping[str, Callable[[wire.AgentConfig], object]] = {
    "language": lambda sent: sent.language,
    "timezone": lambda sent: sent.timezone,
    "voice": lambda sent: _voice_of(sent.voice),
    "llm": lambda sent: None if sent.llm is None else _model_of(sent.llm),
    "realtime": lambda sent: None if sent.realtime is None else _model_of(sent.realtime),
    "stt": lambda sent: None if sent.stt is None else _model_of(sent.stt),
    "judge": lambda sent: None if sent.judge is None else _model_of(sent.judge),
    "greeting": lambda sent: _greeting_of(sent.greeting),
    "hangup": lambda sent: None if sent.hangup is None else Hangup(sent.hangup.when),
    "turn": lambda sent: _turn_of(sent.turn),
    "says": lambda sent: {item.word: item.spoken for item in sent.says or ()},
    "hears": lambda sent: tuple(sent.hears or ()),
    "knowledge": lambda sent: None if sent.knowledge is None else sent.knowledge.text,
    "docs": _bases_of,
    "memory": lambda sent: _memory_of(sent.memory),
    "record": lambda sent: sent.record,
    "max_duration_s": lambda sent: sent.max_duration_s,
    "llm_timeout_s": lambda sent: sent.llm_timeout_s,
    "silence_timeout_s": lambda sent: sent.silence_timeout_s,
    "idle": lambda sent: _idle_of(sent.idle),
    "voicemail": lambda sent: None if sent.voicemail is None else Voicemail(sent.voicemail.message),
    "stt_fallbacks": lambda sent: _models_of(sent.stt_fallbacks),
    "tts_fallbacks": lambda sent: _models_of(sent.tts_fallbacks),
    "judges": lambda sent: sent.judges,
    "personas": lambda sent: sent.personas,
    "hold": lambda sent: sent.hold,
    "widget": lambda sent: sent.widget,
    "monitors": lambda sent: None if sent.monitors is None else tuple(sent.monitors),
}


# ── private: what a write refuses of a stage ──


def _check_voice(voice: Voice) -> None:
    if not voice.vendor or not voice.voice_id:
        raise ValidationError(NO_VENDOR)
    providers.vendor_doing(voice.vendor, Stage.tts)


def _check_model(named: Model, stage: Stage) -> Model:
    if named.end_of_turn is not None and stage is not Stage.stt:
        raise ValidationError(f"end_of_turn is the ears': @stt('<vendor>', {{ endOfTurn: '{named.end_of_turn}' }})")
    providers.vendor_doing(named.vendor, stage)
    if stage is Stage.llm:
        providers.refuse_realtime_as_llm(named.vendor, named.model or None, named.builds)
    return named


# A realtime model is named by vendor and model and takes its options; its class is the plugin's
# realtime one, never named, and its temperature is the vendor's.
def _check_realtime(named: Model) -> None:
    if named.builds is not None or named.temperature is not None or named.end_of_turn is not None:
        raise ValidationError(REALTIME_TAKES)
    check_realtime(named)
