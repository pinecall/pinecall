"""An agent's settings: what a call in a scope is built on, and a write checked as a call would build it."""

import json
from collections.abc import Collection, Mapping, Sequence
from dataclasses import dataclass, replace
from datetime import datetime
from typing import Any, Literal

from sqlalchemy.ext.asyncio import AsyncSession

from runtime.actor import Scope
from runtime.agents.declaration import Declaration
from runtime.agents.repository import AgentConfigRepository, LexiconRepository
from runtime.agents.service import canaries, versions
from runtime.agents.service.declaration import agent_of
from runtime.agents.service.resolution import resolve
from runtime.agents.service.setting_names import (
    TEST_FIELDS,
)
from runtime.agents.service.versions import Version, scope_to_write
from runtime.agents.settings import (
    AgentSettings,
    Lexicon,
    Versions,
    check_settings,
    dump_settings,
    read_settings,
)
from runtime.enums import Env
from runtime.exceptions import Forbidden, ValidationError
from runtime.kit.text import a_mapping
from runtime.providers import service as providers
from runtime.providers.catalog import Catalog

NOT_FOR_A_TEST = "a test room changes only the voice and the models, so {names} {are} not its to set"
NOT_AN_OBJECT = "test is the test room's values as a JSON object"
NOT_THAT_KIND = "a test room's {name} is {kind}"
END_OF_TURNS = ("stt", "livekit", "smart-turn")


@dataclass(frozen=True, slots=True)
class Picked:
    """Which of a scope's versions a read is for: a call's, a version named, or the rest's."""

    call: str | None = None
    version: int | None = None


@dataclass(frozen=True, slots=True)
class Current:
    """The settings and the lexicon a call in the scope is built on, and their versions."""

    settings: AgentSettings
    lexicon: Lexicon
    versions: Versions


@dataclass(frozen=True, slots=True)
class Resolved:
    """An agent as a call in a scope runs it: its declaration over the scope's settings, and their versions."""

    declaration: Declaration
    versions: Versions


@dataclass(frozen=True, slots=True)
class Shown[T]:
    """What a settings screen answers: the env, each level's own newest, and what the agent's class fixes of it."""

    env: Env
    yours: Version[T] | None
    team: Version[T] | None
    production: Version[T] | None
    fixed: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class History[T]:
    """One scope's versions, newest first."""

    env: Env
    holder: str
    rows: list[Version[T]]


@dataclass(frozen=True, slots=True)
class Difference:
    """One scope's newest settings against another's, and the fields that differ."""

    ours: Version[AgentSettings] | None
    theirs: Version[AgentSettings] | None
    changed: list[str]


@dataclass(frozen=True, slots=True)
class CallSettings:
    """The exact settings and lexicon a call was built on, and whether it ran a canary's version."""

    settings_version: int | None
    lexicon_version: int | None
    settings: Version[AgentSettings] | None
    lexicon: Version[Lexicon] | None
    canary: bool


# ── what a call is built on ──


async def current_settings(session: AsyncSession, scope: Scope, agent: str, picked: Picked | None = None) -> Current:
    """What a call in the scope is built on: each field from the nearest level that sets it."""
    wanted = picked or Picked()
    standing = await canaries.standing_per_level(session, scope, agent)
    named = [canary.version for canary in standing.values()]
    if wanted.version is not None:
        named.append(wanted.version)
    rows = await AgentConfigRepository(session).list_candidates(scope, agent, named)
    bucket = None if wanted.call is None else canaries.bucket_of(wanted.call)
    chain = canaries.pick(rows, standing, holder=scope.holder, bucket=bucket, version=wanted.version)
    merged = merge_chain([versions.SETTINGS.version_of(row) for row in chain])
    words = await LexiconRepository(session).find_nearest(scope, agent)
    return Current(
        settings=AgentSettings() if merged is None else merged.value,
        lexicon=Lexicon() if words is None else versions.LEXICON.read(words),
        versions=Versions(
            settings=None if merged is None else merged.version, lexicon=None if words is None else words.version
        ),
    )


# `test` is a test room's own values, checked at its token, laid over the settings for this call alone.
async def resolve_for_call(
    session: AsyncSession,
    declaration: Declaration,
    scope: Scope,
    catalog: Catalog,
    picked: Picked | None = None,
    test: Mapping[str, Any] | None = None,
) -> Resolved:
    """The declaration over the scope's current settings, for a call: as it runs, and the versions it runs on."""
    current = await current_settings(session, scope, declaration.slug, picked)
    settings = overlay_test_values(current.settings, test)
    resolved = resolve(declaration, settings, current.lexicon, defaults=catalog.default_vendors)
    return Resolved(resolved, current.versions)


async def declaration_for_call(
    session: AsyncSession,
    declaration: Declaration,
    scope: Scope,
    picked: Picked | None = None,
    test: Mapping[str, Any] | None = None,
) -> Declaration:
    """The agent as the scope runs it, for the call named: its declaration over the settings, on the box's defaults."""
    catalog = await providers.get_catalog(session)
    return (await resolve_for_call(session, declaration, scope, catalog, picked, test)).declaration


async def find_settings_version(
    session: AsyncSession, scope: Scope, agent: str, version: int
) -> Version[AgentSettings] | None:
    """One version of the agent's settings, the scope's own or the org's it fell through to; None when there is none."""
    return await versions.find_version(session, versions.SETTINGS, scope, agent, version)


async def list_settings(session: AsyncSession, scope: Scope) -> dict[str, AgentSettings]:
    """Every agent's settings as they stand in the scope."""
    chains: dict[str, list[Version[AgentSettings]]] = {}
    for row in await AgentConfigRepository(session).list_newest_per_agent(scope):
        chains.setdefault(row.agent, []).append(versions.SETTINGS.version_of(row))
    merged = {agent: merge_chain(chain) for agent, chain in chains.items()}
    return {agent: kept.value for agent, kept in merged.items() if kept is not None}


async def list_noted_versions(
    session: AsyncSession, scope: Scope, agent: str, named: Collection[int], since: datetime, until: datetime
) -> list[Version[AgentSettings]]:
    """The versions named, and those set in [since, until), oldest first: what a drift explains itself by."""
    rows = await AgentConfigRepository(session).list_noted(scope, agent, list(named), since, until)
    return [versions.SETTINGS.version_of(row) for row in rows]


# A field is set when it is not None, so a falsy value is set and does not fall through:
# `bases: []` is "no bases", not "the team's". The version is the nearest row that set any.
def merge_chain(chain: Sequence[Version[AgentSettings]]) -> Version[AgentSettings] | None:
    """Merge a nearest-first chain field by field; None when no row sets any field."""
    supplying = [(row, kept) for row in chain if (kept := dump_settings(row.value))]
    if not supplying:
        return None
    merged: dict[str, Any] = {}
    for _, kept in reversed(supplying):
        merged.update(kept)
    nearest, _ = supplying[0]
    return replace(nearest, value=read_settings(merged))


# By the versions the call's head kept, never the current ones.
async def settings_of_call(
    session: AsyncSession, scope: Scope, agent: str, built_on: Versions, opened_at: datetime | None
) -> CallSettings:
    """The exact settings and lexicon a call was built on."""
    settings = built_on.settings
    lexicon = built_on.lexicon
    return CallSettings(
        settings_version=settings,
        lexicon_version=lexicon,
        settings=None
        if settings is None
        else await versions.find_version(session, versions.SETTINGS, scope, agent, settings),
        lexicon=None
        if lexicon is None
        else await versions.find_version(session, versions.LEXICON, scope, agent, lexicon),
        canary=opened_at is not None and await canaries.is_canary_run(session, scope, agent, settings, opened_at),
    )


# ── a test room's own values ──


# A test room's own values ride its signed dispatch to the worker, which says them again as JSON:
# checked again, so a worker's request can never change what a test room may not.
def parse_test_values(text: str | None, *, env: Env) -> dict[str, Any]:
    """The values a test room asks for, as the worker says them back in a query; none for no text."""
    if not text:
        return {}
    try:
        body: object = json.loads(text)
    except ValueError as bad:
        raise ValidationError(NOT_AN_OBJECT) from bad
    if not a_mapping(body):
        raise ValidationError(NOT_AN_OBJECT)
    return check_test_values(body, env=env)


def check_test_values(body: Mapping[str, Any] | None, *, env: Env) -> dict[str, Any]:
    """The values a test room asks for, checked: the sandbox's alone, and only those fields."""
    if not body:
        return {}
    if env is not Env.sandbox:
        raise Forbidden("a test room's own voice and models are the sandbox's: production runs the settings it has")
    stray = sorted(set(body) - TEST_FIELDS)
    if stray:
        raise ValidationError(NOT_FOR_A_TEST.format(names=", ".join(stray), are="is" if len(stray) == 1 else "are"))
    for name, value in body.items():
        _check_test_kind(name, value)
    return dump_settings(parse_settings(body))


def overlay_test_values(settings: AgentSettings, values: Mapping[str, Any] | None) -> AgentSettings:
    """The settings with a test room's values over them, field by field."""
    if not values:
        return settings
    return read_settings({**dump_settings(settings), **dump_settings(parse_settings(values))})


def parse_settings(body: Mapping[str, Any]) -> AgentSettings:
    """Settings from a body's fields, refused in the words of the rule they break."""
    return check_settings(read_settings(body))


# ── reading, as a screen shows it ──


async def show_settings(session: AsyncSession, scope: Scope, slug: str) -> Shown[AgentSettings]:
    """The agent's settings as the key sees them: yours, the team's and production's, and what its class fixes."""
    kept = await versions.side_by_side(session, versions.SETTINGS, scope, slug)
    agent = await agent_of(session, scope, slug)
    return Shown(scope.env, kept.yours, kept.team, kept.production, tuple(sorted(agent.fixed)))


async def list_settings_history(
    session: AsyncSession, scope: Scope, slug: str, *, team: bool, limit: int
) -> History[AgentSettings]:
    """One scope's versions of the agent's settings, newest first."""
    target = scope_to_write(scope, team=team)
    rows = await versions.list_history(session, versions.SETTINGS, target, slug, limit=limit)
    return History(scope.env, target.holder, rows)


async def diff_settings(
    session: AsyncSession, scope: Scope, slug: str, *, against: Literal["team", "production"], team: bool
) -> Difference:
    """This key's scope's newest (the team's with `team`) against the team's or production's; what differs."""
    kept = await versions.side_by_side(session, versions.SETTINGS, scope, slug)
    ours = kept.team if team or not scope.holder else kept.yours
    theirs = kept.production if against == "production" else kept.team
    mine = {} if ours is None else dump_settings(ours.value)
    yours = {} if theirs is None else dump_settings(theirs.value)
    changed = sorted(name for name in set(mine) | set(yours) if mine.get(name) != yours.get(name))
    return Difference(ours, theirs, changed)


def _check_test_kind(name: str, value: object) -> None:
    if value is None:
        return
    if name == "temperature":
        if isinstance(value, bool) or not isinstance(value, int | float):
            raise ValidationError(NOT_THAT_KIND.format(name=name, kind="a number"))
    elif name == "end_of_turn":
        if value not in END_OF_TURNS:
            raise ValidationError(NOT_THAT_KIND.format(name=name, kind=f"one of {', '.join(END_OF_TURNS)}"))
    elif not isinstance(value, str):
        raise ValidationError(NOT_THAT_KIND.format(name=name, kind="text"))
