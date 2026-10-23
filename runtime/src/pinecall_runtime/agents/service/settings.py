"""An agent's settings and lexicon: versioned per scope, read as a call is built, written checked."""

import dataclasses
from collections.abc import Collection, Iterable, Mapping, Sequence
from dataclasses import dataclass, replace
from datetime import datetime
from typing import Any

from pydantic import TypeAdapter
from pydantic import ValidationError as PydanticValidationError
from sqlalchemy.ext.asyncio import AsyncSession

from pinecall_runtime.agents import schemas
from pinecall_runtime.agents.declaration import (
    AgentConfig,
    Lexicon,
    Modality,
    Tuning,
    Version,
    Versions,
)
from pinecall_runtime.agents.models import AgentConfig as AgentConfigRow
from pinecall_runtime.agents.models import Lexicon as LexiconRow
from pinecall_runtime.agents.repository import (
    AgentConfigRepository,
    CanaryRepository,
    LexiconRepository,
)
from pinecall_runtime.agents.service.canaries import bucket_of
from pinecall_runtime.agents.service.tuning import apply_tuning
from pinecall_runtime.enums import Env, KeyScope
from pinecall_runtime.exceptions import Conflict, Forbidden, ValidationError
from pinecall_runtime.kit.auth import THE_ORGS_OWN, Actor, Scope
from pinecall_runtime.providers import service as providers

TUNING: TypeAdapter[Tuning] = TypeAdapter(Tuning)
HISTORY_LIMIT = 20

# A `words` key (a supervisor's) sets the opening's words, what is remembered and the lexicon; the
# rest is the pipeline's.
PIPELINE_ONLY = (
    "voice",
    "tts",
    "tts_model",
    "stt",
    "llm",
    "temperature",
    "end_of_turn",
    "llm_builds",
    "llm_options",
    "realtime",
    "realtime_options",
    "stt_builds",
    "stt_options",
    "tts_builds",
    "tts_options",
    "judge",
    "judge_builds",
    "judge_options",
    "language",
    "hangup",
    "turn",
    "bases",
    "record",
    "max_duration_s",
    "llm_timeout_s",
)
TUNING_KNOBS = tuple(field.name for field in dataclasses.fields(Tuning))
# Every knob's name in the declaration, where the two differ.
DECLARED_AS = {
    "tts": "voice",
    "tts_model": "voice",
    "tts_builds": "voice",
    "tts_options": "voice",
    "temperature": "llm",
    "llm_builds": "llm",
    "llm_options": "llm",
    "realtime_options": "realtime",
    "stt_builds": "stt",
    "end_of_turn": "stt",
    "stt_options": "stt",
    "judge_builds": "judge",
    "judge_options": "judge",
    "bases": "docs",
}
# A set that changes a stage's knobs has the stage tried before it is kept.
STAGE_KNOBS: dict[Modality, tuple[str, ...]] = {
    "tts": ("voice", "tts", "tts_model", "tts_builds", "tts_options", "language"),
    "llm": ("llm", "temperature", "llm_builds", "llm_options"),
    "stt": ("stt", "stt_builds", "stt_options", "end_of_turn", "turn", "language"),
}
REALTIME_KNOBS = ("realtime", "realtime_options")


class VersionMoved(Conflict):
    """The scope was written since the writer read it."""

    def __init__(self, newest: int) -> None:
        super().__init__(f"this scope is at v{newest} now, not the version you read: read it again, then set again")


class SetByTheClass(Conflict):
    """The class's declaration wins over a setting it declares."""

    def __init__(self, fields: Collection[str], slug: str) -> None:
        super().__init__(
            f"{', '.join(sorted(fields))} set by the class of {slug}: the class's declaration wins over these "
            "settings, so change it there, or take it out of the class to set it here"
        )


class NotWordsKeys(Forbidden):
    """A words key touched the pipeline's knobs."""

    def __init__(self, fields: Sequence[str]) -> None:
        super().__init__(f"{', '.join(fields)}: the pipeline's, and this key opens words alone")


@dataclass(frozen=True, slots=True)
class Picked:
    """Which of a scope's versions a read is for: a call's, a version named, or the rest's."""

    call: str | None = None
    version: int | None = None


@dataclass(frozen=True, slots=True)
class Written:
    """Who writes a version, why, and the version they read when they want no other."""

    author: str
    note: str | None = None
    if_version: int | None = None


@dataclass(frozen=True, slots=True)
class SideBySide[T]:
    """What a settings screen shows side by side: yours, the team's and production's newest."""

    yours: Version[T] | None
    team: Version[T] | None
    production: Version[T] | None


@dataclass(frozen=True, slots=True)
class Current:
    """The tuning and the lexicon a call in the scope is built on, and their versions."""

    tuning: Tuning
    lexicon: Lexicon
    versions: Versions


# ── reading ──


async def tuning_history(
    session: AsyncSession, scope: Scope, agent: str, *, limit: int = HISTORY_LIMIT
) -> list[Version[Tuning]]:
    """The scope's own versions of the agent's tuning, newest first."""
    return [_tuning_version(row) for row in await AgentConfigRepository(session).history(scope, agent, limit=limit)]


async def lexicon_history(
    session: AsyncSession, scope: Scope, agent: str, *, limit: int = HISTORY_LIMIT
) -> list[Version[Lexicon]]:
    """The scope's own versions of the agent's lexicon, newest first."""
    return [_lexicon_version(row) for row in await LexiconRepository(session).history(scope, agent, limit=limit)]


async def tuning_at(session: AsyncSession, scope: Scope, agent: str, version: int) -> Version[Tuning] | None:
    """One version of the agent's tuning, the scope's own or the org's it fell through to."""
    row = await AgentConfigRepository(session).at(scope, agent, version)
    return None if row is None else _tuning_version(row)


async def lexicon_at(session: AsyncSession, scope: Scope, agent: str, version: int) -> Version[Lexicon] | None:
    """One version of the agent's lexicon, the scope's own or the org's it fell through to."""
    row = await LexiconRepository(session).at(scope, agent, version)
    return None if row is None else _lexicon_version(row)


async def tuning_side_by_side(session: AsyncSession, scope: Scope, agent: str) -> SideBySide[Tuning]:
    """The agent's tuning as yours, the team's and production's, none falling through."""
    configs = AgentConfigRepository(session)

    async def newest(where: Scope) -> Version[Tuning] | None:
        rows = await configs.history(where, agent, limit=1)
        return _tuning_version(rows[0]) if rows else None

    return SideBySide(
        yours=await newest(scope) if scope.holder else None,
        team=await newest(replace(scope, holder=THE_ORGS_OWN)),
        production=await newest(Scope(scope.org, Env.production)),
    )


async def lexicon_side_by_side(session: AsyncSession, scope: Scope, agent: str) -> SideBySide[Lexicon]:
    """The agent's lexicon as yours, the team's and production's, none falling through."""
    lexicons = LexiconRepository(session)

    async def newest(where: Scope) -> Version[Lexicon] | None:
        rows = await lexicons.history(where, agent, limit=1)
        return _lexicon_version(rows[0]) if rows else None

    return SideBySide(
        yours=await newest(scope) if scope.holder else None,
        team=await newest(replace(scope, holder=THE_ORGS_OWN)),
        production=await newest(Scope(scope.org, Env.production)),
    )


async def current_settings(session: AsyncSession, scope: Scope, agent: str, picked: Picked | None = None) -> Current:
    """What a call in the scope is built on: each knob from the nearest level that sets it."""
    wanted = picked or Picked()
    canaries = await CanaryRepository(session).standing_per_level(scope, agent)
    standing: dict[str, tuple[int | None, int | None]] = {
        holder: (row.version, row.share) for holder, row in canaries.items() if row.version is not None
    }
    bucket = None if wanted.call is None else bucket_of(wanted.call)
    chain = await AgentConfigRepository(session).chain(
        scope, agent, standing=standing, bucket=bucket, version=wanted.version
    )
    tuned = resolve_chain([_tuning_version(row) for row in chain])
    words = await LexiconRepository(session).newest(scope, agent)
    return Current(
        tuning=Tuning() if tuned is None else tuned.value,
        lexicon=Lexicon() if words is None else _lexicon_version(words).value,
        versions=Versions(
            config=None if tuned is None else tuned.version,
            lexicon=None if words is None else words.version,
        ),
    )


async def every_tuning(session: AsyncSession, scope: Scope) -> dict[str, Tuning]:
    """Every agent's tuning as it stands in the scope."""
    chains: dict[str, list[Version[Tuning]]] = {}
    for row in await AgentConfigRepository(session).newest_per_agent(scope):
        chains.setdefault(row.agent, []).append(_tuning_version(row))
    resolved = {agent: resolve_chain(chain) for agent, chain in chains.items()}
    return {agent: kept.value for agent, kept in resolved.items() if kept is not None}


# A knob is set when it is not None, so a falsy value is set and does not fall through:
# `bases: []` is "no bases", not "the team's". The version is the nearest row that set any.
async def versions_noted(
    session: AsyncSession, scope: Scope, agent: str, versions: Collection[int], since: datetime, until: datetime
) -> list[Version[Tuning]]:
    """The versions named, and those set in [since, until), oldest first: what a drift explains itself by."""
    rows = await AgentConfigRepository(session).noted(scope, agent, list(versions), since, until)
    return [_tuning_version(row) for row in rows]


def resolve_chain(chain: Sequence[Version[Tuning]]) -> Version[Tuning] | None:
    """Merge a nearest-first chain knob by knob; None when no row sets any knob."""
    supplying = [(row, stored) for row in chain if (stored := dump_tuning(row.value))]
    if not supplying:
        return None
    merged: dict[str, Any] = {}
    for _, stored in reversed(supplying):
        merged.update(stored)
    nearest, _ = supplying[0]
    return replace(nearest, value=TUNING.validate_python(merged))


def dump_tuning(tuning: Tuning) -> dict[str, Any]:
    """A tuning as it is stored and sent: each knob set, by its name."""
    dumped: dict[str, Any] = TUNING.dump_python(tuning, mode="json", exclude_none=True)
    return dumped


# What a test room may change for its own call: the voice, the models and the language they run in.
TEST_KNOBS = frozenset({"stt", "llm", "tts", "tts_model", "voice", "language", "temperature"})
NOT_FOR_A_TEST = "a test room changes only the voice and the models, so {names} {are} not its to set"


def check_test_values(body: Mapping[str, Any] | None, *, env: Env) -> dict[str, Any]:
    """The values a test room asks for, checked: the sandbox's alone, and only those knobs."""
    if not body:
        return {}
    if env is not Env.sandbox:
        raise Forbidden("a test room's own voice and models are the sandbox's: production runs the settings it has")
    stray = sorted(set(body) - TEST_KNOBS)
    if stray:
        raise ValidationError(NOT_FOR_A_TEST.format(names=", ".join(stray), are="is" if len(stray) == 1 else "are"))
    return dump_tuning(parse_tuning(body))


def overlay_tuning(tuning: Tuning, values: Mapping[str, Any] | None) -> Tuning:
    """The tuning with a test room's values over it, knob by knob."""
    if not values:
        return tuning
    return TUNING.validate_python({**dump_tuning(tuning), **dump_tuning(parse_tuning(values))})


def parse_tuning(body: Mapping[str, Any]) -> Tuning:
    """A tuning from a body, refused in the dataclass's own words."""
    try:
        return TUNING.validate_python(dict(body))
    except PydanticValidationError as invalid:
        for error in invalid.errors():
            cause = error.get("ctx", {}).get("error")
            if isinstance(cause, ValidationError):
                raise cause from invalid
        raise ValidationError(str(invalid)) from invalid


# ── writing ──


async def put_tuning(session: AsyncSession, scope: Scope, agent: str, tuning: Tuning, written: Written) -> int:
    """Write the agent's next tuning in the scope; a scope moved since it was read refuses."""
    configs = AgentConfigRepository(session)
    newest = await configs.newest_version(scope, agent)
    if written.if_version is not None and newest != written.if_version:
        raise VersionMoved(newest)
    row = await configs.put(scope, agent, dump_tuning(tuning), written.author, written.note)
    return row.version


async def put_lexicon(session: AsyncSession, scope: Scope, agent: str, lexicon: Lexicon, written: Written) -> int:
    """Write the agent's next lexicon in the scope; a scope moved since it was read refuses."""
    lexicons = LexiconRepository(session)
    newest = await lexicons.newest_version(scope, agent)
    if written.if_version is not None and newest != written.if_version:
        raise VersionMoved(newest)
    row = await lexicons.put(scope, agent, dict(lexicon.said), list(lexicon.heard), written.author, written.note)
    return row.version


# A whole replacement, guarded by the version it was read at: what the class declares is refused,
# a words key carries the pipeline over untouched, and a changed stage is tried before it is kept.
async def write_tuning(
    session: AsyncSession,
    scope: Scope,
    agent: str,
    wanted: Tuning,
    written: Written,
    *,
    actor: Actor,
    declared: AgentConfig | None,
    vault_keyring: providers.Keyring,
) -> int:
    """The agent's next version in the scope, checked as a call would build it."""
    kept = await tuning_side_by_side(session, scope, agent)
    newest_row = kept.team if scope.holder == THE_ORGS_OWN else kept.yours
    newest = Tuning() if newest_row is None else newest_row.value
    # Nothing changes, nothing is written: a version says what moved.
    if newest_row is not None and wanted == newest:
        return newest_row.version
    changed = [knob for knob in TUNING_KNOBS if _changes(wanted, newest, knob)]
    refuse_what_the_class_sets(declared, agent, changed)
    opens_the_pipeline = KeyScope.pipeline in actor.scopes
    if not opens_the_pipeline:
        wanted = _words_only(wanted, newest)
    catalog = await providers.get_catalog(session)
    config = await resolved_config(session, declared or AgentConfig(slug=agent), scope, wanted, catalog)
    stages = providers.build_pipeline(config, catalog, vault_keyring)
    # The judge is not a stage of the call, but a judge nobody can key fails every hang-up.
    if config.judge is not None:
        providers.stage_on_its_key("llm", config.judge, catalog, vault_keyring)
    if opens_the_pipeline:
        providers.refuse_untaken_knobs(stages.stt, stages.tts, wanted)
        for stage, knobs in STAGE_KNOBS.items():
            if any(_changes(wanted, newest, knob) for knob in knobs):
                await providers.try_stage(stage, getattr(stages, stage), wanted.turn)
        if stages.realtime is not None and any(_changes(wanted, newest, knob) for knob in REALTIME_KNOBS):
            await providers.try_realtime(stages.realtime)
    return await put_tuning(session, scope, agent, wanted, written)


async def resolved_config(
    session: AsyncSession, declared: AgentConfig, scope: Scope, tuning: Tuning, catalog: providers.Catalog
) -> AgentConfig:
    """The declaration with this tuning and the scope's lexicon applied."""
    current = await current_settings(session, scope, declared.slug)
    return apply_tuning(declared, tuning, current.lexicon, defaults=catalog.default_vendors)


async def tuned_for_call(
    session: AsyncSession,
    declared: AgentConfig,
    scope: Scope,
    catalog: providers.Catalog,
    picked: Picked | None = None,
    test: Mapping[str, Any] | None = None,
) -> tuple[AgentConfig, Versions]:
    """The declaration under the scope's current settings, for a call: the config and its versions.

    `test` is a test room's own values, checked at its token, laid over the settings for this call alone.
    """
    current = await current_settings(session, scope, declared.slug, picked)
    tuning = overlay_tuning(current.tuning, test)
    return apply_tuning(declared, tuning, current.lexicon, defaults=catalog.default_vendors), current.versions


def refuse_what_the_class_sets(declared: AgentConfig | None, slug: str, knobs: Sequence[str]) -> None:
    """Refuse a write that changes what the class of the agent declares."""
    fixed = frozenset[str]() if declared is None else declared.fixed
    taken = {DECLARED_AS.get(knob, knob) for knob in knobs} & fixed
    if taken:
        raise SetByTheClass(taken, slug)


def written_to(scope: Scope, *, team: bool) -> Scope:
    """The scope a write lands in: the key's own, or the team's."""
    return replace(scope, holder=THE_ORGS_OWN) if team else scope


# ── private ──


def _changes(wanted: Tuning, newest: Tuning, knob: str) -> bool:
    value: object = getattr(wanted, knob)
    return value is not None and value != getattr(newest, knob)


def _words_only(wanted: Tuning, newest: Tuning) -> Tuning:
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


def _tuning_version(row: AgentConfigRow) -> Version[Tuning]:
    return Version(row.holder, row.version, row.author, row.note, row.set_at, TUNING.validate_python(row.config))


def _lexicon_version(row: LexiconRow) -> Version[Lexicon]:
    said = {str(word): str(spoken) for word, spoken in row.said.items()}
    heard = tuple(str(word) for word in row.heard)
    return Version(row.holder, row.version, row.author, row.note, row.set_at, Lexicon(said=said, heard=heard))


# ── as the endpoints answer it ──


async def settings_response(
    session: AsyncSession, scope: Scope, agent: str, *, fixed: Iterable[str]
) -> schemas.SettingsResponse:
    """The agent's settings in the scope, yours and the team's and production's newest, side by side."""
    kept = await tuning_side_by_side(session, scope, agent)
    return schemas.SettingsResponse(
        world=scope.env,
        yours=None if kept.yours is None else settings_row(kept.yours),
        team=None if kept.team is None else settings_row(kept.team),
        production=None if kept.production is None else settings_row(kept.production),
        fixed=sorted(fixed),
    )


def settings_row(kept: Version[Tuning]) -> schemas.SettingsRow:
    """One kept version as the endpoints send it."""
    return schemas.SettingsRow(
        holder=kept.holder,
        version=kept.version,
        author=kept.author,
        note=kept.note,
        set_at=kept.set_at.timestamp(),
        config=schemas.SettingsBody.model_validate(dump_tuning(kept.value)),
    )
