"""What a call is, kept at its open: its context and the declaration it runs on, and the turns it carries on."""

import dataclasses
import json
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from typing import Any, TypeIs

from sqlalchemy.ext.asyncio import AsyncSession

from runtime.agents.declaration import (
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
)
from runtime.calls.context import CallContext, dump_context, read_context
from runtime.calls.log.private import open_entries
from runtime.calls.repository.entries import EntryRepository
from runtime.calls.repository.openings import OpeningRepository
from runtime.calls.repository.private import PrivateRepository
from runtime.kit.crypto import Vault
from runtime.kit.text import a_mapping, sha256_of
from runtime.providers.stage import Model, Voice
from runtime.wire.base import Entry, WireModel
from runtime.wire.declaration import HoldConfig, JudgesDeclared, MonitorDeclared, PersonasDeclared, WidgetLook

# What a call that carries another on reads of it: what was said, and what the tools did.
CARRIED = frozenset({"turn.user", "turn.agent", "tool.call", "tool.result"})

# A conversation carried on and on reads its last ten calls; an older one is past what it needs.
CALLS_CARRIED = 10

# The stored word for a stage's vendor, as the wire says it and the release before 2026-11 kept it.
VENDOR_AS_KEPT = "provider"


@dataclass(frozen=True, slots=True)
class Opening:
    """A call as it opened: what the worker said of it, and the declaration it runs on."""

    context: CallContext
    declaration: Declaration


async def keep_opening(session: AsyncSession, org: str, context: CallContext, declaration: Declaration) -> None:
    """Keep what the call is: its declaration once per hash, its opening once."""
    written = dump_declaration(declaration)
    hashed = sha256_of(json.dumps(written, sort_keys=True))
    await OpeningRepository(session).keep(context.call, org, dump_context(context), hashed, written)


async def opening_of(session: AsyncSession, call: str) -> Opening | None:
    """What the call is, as it was kept when it opened; None for one opened before it was kept."""
    found = await OpeningRepository(session).find(call)
    if found is None:
        return None
    return Opening(context=read_context(found.context), declaration=read_declaration(found.config))


# Each call keeps only its own turns; the one it continued is named in its opening, and so on back.
async def list_carried(session: AsyncSession, vault: Vault, call: str) -> list[Entry]:
    """The turns of the call and of the calls it continued, oldest first, the private opened."""
    calls: list[str] = []
    at: str | None = call
    while at is not None and len(calls) < CALLS_CARRIED:
        calls.append(at)
        opening = await opening_of(session, at)
        at = None if opening is None else opening.context.continues
    turns: list[Entry] = []
    for earlier in reversed(calls):
        turns += [entry for entry in await read_whole(session, vault, earlier) if entry.type in CARRIED]
    return turns


# One way to read a log with what it sealed aside. Until 2026-11 there were two, eight lines apart:
# the store's own session for one, the request's for the other.
async def read_whole(session: AsyncSession, vault: Vault, call: str) -> list[Entry]:
    """Every entry of the call as its writer wrote it, the private values opened."""
    entries = await EntryRepository(session).whole_of(call)
    return open_entries(vault, entries, await PrivateRepository(session).list_of_log(call))


# ── a declaration as it is kept ──


# `call_configs.config` is read by whichever gateway serves the call again, of this release or of
# the one that runs beside it: every field is written, under the name the release before 2026-11
# kept it by (a stage's vendor is `provider`), a set as a sorted list so the hash is the same for
# the same declaration.
def dump_declaration(declaration: Declaration) -> dict[str, Any]:
    """The declaration a call runs on, as it is kept: JSON values under its fields' own names."""
    return {one.name: _plain(getattr(declaration, one.name)) for one in dataclasses.fields(declaration)}


# Given its shape and nothing else: no rule is asked, so an opening kept before a rule was made
# stricter still reads, and the call it names can be served again. A key this release does not know
# (`name`, of the release before) is left out.
def read_declaration(kept: Mapping[str, Any]) -> Declaration:
    """The declaration a kept config says."""
    read: dict[str, Any] = {}
    for one in dataclasses.fields(Declaration):
        if one.name not in kept:
            continue
        value = kept[one.name]
        reads = PARTS.get(one.name)
        read[one.name] = value if value is None or reads is None else reads(value)
    return Declaration(**read)


def _plain(value: object) -> object:
    if isinstance(value, WireModel):
        return value.model_dump(mode="json")
    if isinstance(value, Voice | Model):
        written = _fields_of(value)
        return {VENDOR_AS_KEPT: written.pop("vendor"), **written}
    if dataclasses.is_dataclass(value) and not isinstance(value, type):
        return _fields_of(value)
    if _a_set(value):
        return sorted(str(one) for one in value)
    if _a_tuple(value):
        return [_plain(one) for one in value]
    if a_mapping(value):
        return {name: _plain(one) for name, one in value.items()}
    return value


def _fields_of(value: object) -> dict[str, object]:
    if not dataclasses.is_dataclass(value) or isinstance(value, type):
        return {}
    return {one.name: _plain(getattr(value, one.name)) for one in dataclasses.fields(value)}


# What `isinstance` leaves as a collection of nothing known; these say what it holds, once.
def _a_set(value: object) -> TypeIs[frozenset[object]]:
    return isinstance(value, frozenset)


def _a_tuple(value: object) -> TypeIs[tuple[object, ...]]:
    return isinstance(value, tuple)


def _build[T](kind: type[T], kept: Mapping[str, Any], names: Sequence[str]) -> T:
    return kind(**{name: kept[name] for name in names if name in kept})


def _voice(kept: Mapping[str, Any]) -> Voice:
    return Voice(
        vendor=kept[VENDOR_AS_KEPT],
        model=kept.get("model"),
        voice_id=kept.get("voice_id"),
        builds=kept.get("builds"),
        options=dict(kept.get("options") or {}),
    )


def _model(kept: Mapping[str, Any]) -> Model:
    return Model(
        vendor=kept[VENDOR_AS_KEPT],
        model=kept.get("model") or "",
        temperature=kept.get("temperature"),
        builds=kept.get("builds"),
        options=dict(kept.get("options") or {}),
        end_of_turn=kept.get("end_of_turn"),
    )


def _tool(kept: Mapping[str, Any]) -> ToolSpec:
    names = [one.name for one in dataclasses.fields(ToolSpec) if one.name != "pii"]
    return dataclasses.replace(_build(ToolSpec, kept, names), pii=frozenset(kept.get("pii") or ()))


def _idle(kept: Mapping[str, Any]) -> Idle:
    return dataclasses.replace(_build(Idle, kept, ("says", "after_s", "times")), says=tuple(kept["says"]))


# Each field kept as an object or a list, with what reads it back; every other is kept as it is.
PARTS: Mapping[str, Callable[[Any], object]] = {
    "prompt": lambda kept: tuple(PromptBlock(one["name"], one["region"]) for one in kept),
    "greeting": lambda kept: _build(Greeting, kept, ("say", "reply", "allow_interruptions")),
    "voice": _voice,
    "llm": _model,
    "realtime": _model,
    "stt": _model,
    "judge": _model,
    "turn": lambda kept: _build(Turn, kept, [one.name for one in dataclasses.fields(Turn)]),
    "says": dict,
    "hears": tuple,
    "bases": lambda kept: tuple(_build(Docs, one, ("base", "mode", "k", "min_score")) for one in kept),
    "memory": lambda kept: MemoryPolicy(tuple(kept.get("remember", ())), tuple(kept.get("forget", ()))),
    "hangup": lambda kept: _build(Hangup, kept, ("when",)),
    "idle": _idle,
    "voicemail": lambda kept: _build(Voicemail, kept, ("message",)),
    "stt_fallbacks": lambda kept: tuple(_model(one) for one in kept),
    "tts_fallbacks": lambda kept: tuple(_model(one) for one in kept),
    "tools": lambda kept: tuple(_tool(one) for one in kept),
    "state_fields": dict,
    "events": lambda kept: {name: frozenset(sources) for name, sources in kept.items()},
    "judges": JudgesDeclared.model_validate,
    "personas": PersonasDeclared.model_validate,
    "hold": HoldConfig.model_validate,
    "widget": WidgetLook.model_validate,
    "monitors": lambda kept: tuple(MonitorDeclared.model_validate(one) for one in kept),
    "fixed": frozenset,
}
