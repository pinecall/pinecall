"""A write of an agent's settings: planned as a call would build it, tried on the vendors it moves to, kept."""

import dataclasses
from collections.abc import Mapping, Sequence
from dataclasses import dataclass

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from runtime.actor import Actor, Scope
from runtime.agents.declaration import Agent
from runtime.agents.service import canaries, versions
from runtime.agents.service.declaration import agent_of
from runtime.agents.service.resolution import SEPARATOR, resolve
from runtime.agents.service.setting_names import (
    JUDGE_FIELDS,
    PIPELINE_ONLY,
    REALTIME_FIELDS,
    STAGE_FIELDS,
    refuse_what_the_class_sets,
)
from runtime.agents.service.settings import Shown, current_settings, show_settings
from runtime.agents.service.versions import Written, scope_to_write
from runtime.agents.settings import FIELDS, AgentSettings
from runtime.enums import KeyScope, Stage
from runtime.exceptions import Forbidden
from runtime.kit.crypto import Vault
from runtime.providers import service as providers
from runtime.providers.catalog import Catalog
from runtime.providers.stage import Running

THE_JUDGE = "the judge this sets"


class NotWordsKeys(Forbidden):
    """A words key touched the pipeline's settings."""

    def __init__(self, fields: Sequence[str]) -> None:
        super().__init__(f"{', '.join(fields)}: the pipeline's, and this key opens words alone")


@dataclass(frozen=True, slots=True)
class _Trial:
    """One stage a write has tried on its vendor before it is kept."""

    stage: Stage
    running: Running
    tried: Mapping[str, object]
    what: str | None = None


@dataclass(frozen=True, slots=True)
class SettingsPlan:
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
        plan = await plan_settings(session, vault, actor, target, slug, wanted)
    await try_settings(plan)
    async with sessions.begin() as session:
        await keep_settings(session, target, slug, plan, written)
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


# ── a write in its three steps ──


# The three steps apart, for a write that is one part of something larger (a definition deployed with
# the settings it was tried on): planned in a short transaction, tried with no connection held, kept in
# the transaction that keeps the rest. `agent` is the class as it will be declared in the target, where
# that is not what the target keeps yet.
async def plan_settings(
    session: AsyncSession,
    vault: Vault,
    actor: Actor,
    target: Scope,
    slug: str,
    wanted: AgentSettings,
    *,
    agent: Agent | None = None,
) -> SettingsPlan | None:
    """The write checked as a call would build it: what is kept and what the vendors are asked; None, no change."""
    newest_row = await versions.find_newest(session, versions.SETTINGS, target, slug)
    newest = AgentSettings() if newest_row is None else newest_row.value
    wanted = _name_the_vendor_in_use(wanted, newest)
    # Nothing changes, nothing is written: a version says what moved.
    if newest_row is not None and wanted == newest:
        return None
    # The class whose calls run in the scope written, not in the key's own: the two differ for a team write.
    agent = agent or await agent_of(session, target, slug)
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
        return SettingsPlan(wanted, catalog, tuple(trials))
    providers.refuse_untaken_settings(stages.stt, stages.tts, wanted.turn, sets_a_voice=wanted.voice is not None)
    running = {Stage.tts: stages.tts, Stage.llm: stages.llm, Stage.stt: stages.stt}
    for stage, names in STAGE_FIELDS.items():
        moved = _fields_moved(wanted, newest, names)
        if moved:
            trials.append(_Trial(stage, running[stage], moved))
    talks_anew = stages.realtime is not None and bool(_fields_moved(wanted, newest, REALTIME_FIELDS))
    return SettingsPlan(wanted, catalog, tuple(trials), stages.realtime if talks_anew else None)


# The turn is the ears' and the catalog a moved voice's: a stage that is neither reads neither.
async def try_settings(plan: SettingsPlan | None) -> None:
    """Ask each vendor a planned write moves to whether it takes it; refused in the vendor's own words."""
    if plan is None:
        return
    for trial in plan.trials:
        await providers.try_stage(
            trial.stage, trial.running, plan.wanted.turn, what=trial.what, tried=trial.tried, catalog=plan.catalog
        )
    if plan.realtime is not None:
        await providers.try_realtime(plan.realtime)


async def keep_settings(
    session: AsyncSession, target: Scope, slug: str, plan: SettingsPlan | None, written: Written
) -> None:
    """Keep a planned write as the target's next version; a plan of no change keeps nothing."""
    if plan is not None:
        await versions.add_version(session, versions.SETTINGS, target, slug, plan.wanted, written)


# ── private ──


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
