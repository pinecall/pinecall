"""An agent's settings: what a call in a scope is built on, and a write checked as a call would build it."""

import dataclasses
import json
from collections.abc import Collection, Mapping, Sequence
from dataclasses import dataclass, replace
from datetime import datetime
from typing import Any, Literal

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from runtime.actor import Actor, Scope
from runtime.agents.declaration import Declaration
from runtime.agents.repository import AgentConfigRepository, LexiconRepository
from runtime.agents.service import canaries, versions
from runtime.agents.service.declaration import agent_of
from runtime.agents.service.resolution import SEPARATOR, resolve
from runtime.agents.service.setting_names import (
    JUDGE_FIELDS,
    PIPELINE_ONLY,
    REALTIME_FIELDS,
    STAGE_FIELDS,
    TEST_FIELDS,
    refuse_what_the_class_sets,
)
from runtime.agents.service.versions import Version, Written, scope_to_write
from runtime.agents.settings import (
    FIELDS,
    AgentSettings,
    Lexicon,
    Versions,
    check_settings,
    dump_settings,
    read_settings,
)
from runtime.enums import Env, KeyScope, Stage
from runtime.exceptions import Forbidden, ValidationError
from runtime.kit.crypto import Vault
from runtime.kit.text import a_mapping
from runtime.providers import service as providers
from runtime.providers.catalog import Catalog
from runtime.providers.stage import Running

NOT_FOR_A_TEST = "a test room changes only the voice and the models, so {names} {are} not its to set"
NOT_AN_OBJECT = "test is the test room's values as a JSON object"
NOT_THAT_KIND = "a test room's {name} is {kind}"
THE_JUDGE = "the judge this sets"
END_OF_TURNS = ("stt", "livekit", "smart-turn")


class NotWordsKeys(Forbidden):
    """A words key touched the pipeline's settings."""

    def __init__(self, fields: Sequence[str]) -> None:
        super().__init__(f"{', '.join(fields)}: the pipeline's, and this key opens words alone")


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


# ── writing ──


@dataclass(frozen=True, slots=True)
class _Trial:
    """One stage a write has tried on its vendor before it is kept."""

    stage: Stage
    running: Running
    tried: Mapping[str, object]
    what: str | None = None


@dataclass(frozen=True, slots=True)
class _Plan:
    """A write checked as a call would build it: what is kept, and what is asked of the vendors first."""

    wanted: AgentSettings
    catalog: Catalog
    trials: tuple[_Trial, ...] = ()
    realtime: Running | None = None


# A whole replacement, guarded by the version it was read at: what the class declares is refused,
# a words key carries the pipeline over untouched, and a changed stage is tried before it is kept.
#
# Three steps, and no connection held across the middle one. Until 2026-11 the vendors were asked
# inside the request's transaction: up to five tries of twelve seconds each with a connection of the
# pool idle in its transaction, past the minute Postgres gives one, and then the insert failed.
async def put_settings(
    sessions: async_sessionmaker[AsyncSession],
    vault: Vault,
    actor: Actor,
    slug: str,
    wanted: AgentSettings,
    written: Written,
    *,
    team: bool,
) -> Shown[AgentSettings]:
    """The agent's next version in the key's scope or the team's, checked as a call would build it."""
    target = scope_to_write(actor.scope, team=team)
    async with sessions.begin() as session:
        plan = await _plan(session, vault, actor, target, slug, wanted)
    if plan is not None:
        await _try(plan)
    async with sessions.begin() as session:
        if plan is not None:
            await versions.add_version(session, versions.SETTINGS, target, slug, plan.wanted, written)
        return await show_settings(session, actor.scope, slug)


# A rollback writes a new version copying an old one; nothing is ever deleted. It asks nothing of a
# vendor and refuses nothing a class fixes, as it never did: the version it brings back was checked
# when it was written, a field its class has fixed since is the class's at the call anyway, and the
# way back from a bad write must not wait on the vendor that write moved to.
async def roll_back_settings(
    session: AsyncSession, scope: Scope, slug: str, version: int, *, author: str, team: bool
) -> Shown[AgentSettings]:
    """An old version brought back as the scope's next one."""
    target = scope_to_write(scope, team=team)
    kept = await versions.find_version(session, versions.SETTINGS, target, slug, version)
    if kept is None:
        raise canaries.NoSuchVersion(version, slug)
    back = Written(author=author, note=f"rollback to v{version}")
    await versions.add_version(session, versions.SETTINGS, target, slug, kept.value, back)
    return await show_settings(session, scope, slug)


# ── private ──


async def _plan(
    session: AsyncSession, vault: Vault, actor: Actor, target: Scope, slug: str, wanted: AgentSettings
) -> _Plan | None:
    newest_row = await versions.find_newest(session, versions.SETTINGS, target, slug)
    newest = AgentSettings() if newest_row is None else newest_row.value
    wanted = _name_the_vendor_in_use(wanted, newest)
    # Nothing changes, nothing is written: a version says what moved.
    if newest_row is not None and wanted == newest:
        return None
    # The class whose calls run in the scope written, not in the key's own: the two differ for a team write.
    agent = await agent_of(session, target, slug)
    refuse_what_the_class_sets(agent, [name for name in FIELDS if _changes(wanted, newest, name)])
    opens_the_pipeline = actor.opens(KeyScope.pipeline)
    if not opens_the_pipeline:
        wanted = _carry_the_pipeline(wanted, newest)
    catalog = await providers.get_catalog(session)
    keys = await providers.keys_of(session, vault, actor.scope)
    lexicon = (await current_settings(session, target, slug)).lexicon
    resolved = resolve(agent.whole, wanted, lexicon, defaults=catalog.default_vendors)
    stages = providers.build_pipeline(resolved, catalog, keys)
    trials: list[_Trial] = []
    # Not a stage of the call, but a judge nobody keyed, or whose options its vendor refuses, fails every hang-up.
    if resolved.judge is not None:
        judge = providers.stage_on_its_key(Stage.llm, resolved.judge, catalog, keys)
        moved = _fields_moved(wanted, newest, JUDGE_FIELDS)
        if opens_the_pipeline and moved:
            trials.append(_Trial(Stage.llm, judge, moved, what=THE_JUDGE))
    if not opens_the_pipeline:
        return _Plan(wanted, catalog, tuple(trials))
    providers.refuse_untaken_settings(stages.stt, stages.tts, wanted.turn, sets_a_voice=wanted.voice is not None)
    running = {Stage.tts: stages.tts, Stage.llm: stages.llm, Stage.stt: stages.stt}
    for stage, names in STAGE_FIELDS.items():
        moved = _fields_moved(wanted, newest, names)
        if moved:
            trials.append(_Trial(stage, running[stage], moved))
    talks_anew = stages.realtime is not None and bool(_fields_moved(wanted, newest, REALTIME_FIELDS))
    return _Plan(wanted, catalog, tuple(trials), stages.realtime if talks_anew else None)


# The turn is the ears' and the catalog a moved voice's: a stage that is neither reads neither.
async def _try(plan: _Plan) -> None:
    for trial in plan.trials:
        await providers.try_stage(
            trial.stage, trial.running, plan.wanted.turn, what=trial.what, tried=trial.tried, catalog=plan.catalog
        )
    if plan.realtime is not None:
        await providers.try_realtime(plan.realtime)


# A field set, and one cleared: the body is the scope whole, so a field it leaves out is one taken out.
def _changes(wanted: AgentSettings, newest: AgentSettings, name: str) -> bool:
    value: object = getattr(wanted, name)
    return bool(value != getattr(newest, name))


def _fields_moved(wanted: AgentSettings, newest: AgentSettings, names: Sequence[str]) -> dict[str, object]:
    return {name: getattr(wanted, name) for name in names if _changes(wanted, newest, name)}


# `--llm claude-sonnet-5` names a model on the vendor the scope runs now, and is kept as that vendor's
# (`anthropic/claude-sonnet-5`), so what is stored says it whole; a vendor nobody set yet leaves the model
# alone for the class's vendor, else the default. The judge reads the same way.
def _name_the_vendor_in_use(wanted: AgentSettings, newest: AgentSettings) -> AgentSettings:
    return dataclasses.replace(
        wanted, llm=_say_the_vendor(wanted.llm, newest.llm), judge=_say_the_vendor(wanted.judge, newest.judge)
    )


def _say_the_vendor(text: str | None, before: str | None) -> str | None:
    if text is None or before is None:
        return text
    word = text.strip()
    vendor, slash, _ = before.partition(SEPARATOR)
    if slash and SEPARATOR not in word and not providers.is_installed(word.lower()):
        return f"{vendor}{SEPARATOR}{word}"
    return text


def _carry_the_pipeline(wanted: AgentSettings, newest: AgentSettings) -> AgentSettings:
    carried = {name: getattr(newest, name) for name in PIPELINE_ONLY if getattr(wanted, name) is None}
    touched = [
        name
        for name in PIPELINE_ONLY
        if getattr(wanted, name) is not None and getattr(wanted, name) != getattr(newest, name)
    ]
    opening = wanted.greeting
    if (
        opening is not None
        and opening != newest.greeting
        and (opening.reply is not None or opening.allow_interruptions is not None)
    ):
        touched = [*touched, "greeting.reply"]
    if touched:
        raise NotWordsKeys(touched)
    return dataclasses.replace(wanted, **carried)


# A body's fields are typed where the body is read; a test room's come back from a worker as loose JSON.
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
