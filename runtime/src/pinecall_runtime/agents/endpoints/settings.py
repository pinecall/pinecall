"""The settings endpoints: an agent's tuning and lexicon per env and scope, its canary, a call's own."""

from datetime import UTC, datetime
from typing import Annotated, Literal

from fastapi import APIRouter, Query, Request

from pinecall_runtime.agents import schemas
from pinecall_runtime.agents.auth import CallsKey, PipelineKey, WordsKey
from pinecall_runtime.agents.declaration import Lexicon, Tuning, Version
from pinecall_runtime.agents.service import canaries, settings
from pinecall_runtime.agents.service.canaries import Canary
from pinecall_runtime.agents.service.registry import AgentRegistry
from pinecall_runtime.agents.service.settings import Written
from pinecall_runtime.calls import service as calls
from pinecall_runtime.enums import Env
from pinecall_runtime.exceptions import NotFound
from pinecall_runtime.kit.auth import THE_ORGS_OWN, Scope
from pinecall_runtime.kit.crypto import Vault
from pinecall_runtime.kit.handles import handles_of
from pinecall_runtime.kit.time import now
from pinecall_runtime.postgres import Session
from pinecall_runtime.providers import service as providers
from pinecall_runtime.wire.parts import Pronunciation

router = APIRouter()


@router.get("/v1/agents/{slug}/settings", response_model_exclude_unset=True)
async def get_settings(slug: str, actor: WordsKey, request: Request, session: Session) -> schemas.SettingsResponse:
    """The agent's settings as this key sees them: yours, the team's and production's."""
    return await _side_by_side(request, session, actor.scope, slug)


# A whole replacement, guarded by the version it was read at; the read shows each scope's own
# newest and never the fallthrough, because if_version names the scope being written. A knob
# nobody set is left out of the answer, never sent as null: the body's fields are optional.
@router.put("/v1/agents/{slug}/settings", response_model_exclude_unset=True)
async def put_settings(
    slug: str, body: schemas.PutSettingsRequest, actor: WordsKey, request: Request, session: Session
) -> schemas.SettingsResponse:
    """The agent's next version in this scope or the team's, checked as a call would build it."""
    target = settings.written_to(actor.scope, team=body.team)
    wanted = settings.parse_tuning(body.config.dump())
    written = Written(author=actor.name, note=body.note, if_version=body.if_version)
    keys = await providers.keys_of(session, _vault(request), actor.scope)
    await settings.write_tuning(
        session,
        target,
        slug,
        wanted,
        written,
        actor=actor,
        declared=_registry(request).declared(slug),
        vault_keyring=keys,
    )
    return await _side_by_side(request, session, actor.scope, slug)


@router.get("/v1/agents/{slug}/settings/history", response_model_exclude_unset=True)
async def settings_history(
    slug: str, actor: WordsKey, session: Session, query: Annotated[schemas.HistoryQuery, Query()]
) -> schemas.SettingsHistoryResponse:
    """One scope's versions of the agent's settings, newest first."""
    target = settings.written_to(actor.scope, team=query.team)
    rows = await settings.tuning_history(session, target, slug, limit=query.limit)
    return schemas.SettingsHistoryResponse(
        world=actor.env, holder=target.holder, rows=[_settings_row(row) for row in rows]
    )


@router.get("/v1/agents/{slug}/settings/diff", response_model_exclude_unset=True)
async def settings_diff(
    slug: str,
    actor: WordsKey,
    session: Session,
    against: Annotated[Literal["team", "production"], Query()] = "production",
) -> schemas.SettingsDiffResponse:
    """This key's scope's newest against the team's or production's, and which fields differ."""
    kept = await settings.tuning_side_by_side(session, actor.scope, slug)
    ours = kept.yours if actor.scope.holder else kept.team
    theirs = kept.production if against == "production" else kept.team
    return schemas.SettingsDiffResponse(
        ours=None if ours is None else _settings_row(ours),
        theirs=None if theirs is None else _settings_row(theirs),
        changed=_differing(ours, theirs),
    )


# A rollback writes a new version copying an old one; nothing is ever deleted.
@router.post("/v1/agents/{slug}/settings/rollback", response_model_exclude_unset=True)
async def rollback_settings(
    slug: str, body: schemas.RollbackSettingsRequest, actor: PipelineKey, request: Request, session: Session
) -> schemas.SettingsResponse:
    """An old version brought back as the scope's next one."""
    target = settings.written_to(actor.scope, team=body.team)
    row = await settings.tuning_at(session, target, slug, body.version)
    if row is None:
        raise canaries.NoSuchVersion(body.version, slug)
    await settings.put_tuning(
        session, target, slug, row.value, Written(author=actor.name, note=f"rollback to v{body.version}")
    )
    return await _side_by_side(request, session, actor.scope, slug)


@router.get("/v1/agents/{slug}/settings/canary", response_model_exclude_unset=True)
async def get_canary(
    slug: str, actor: WordsKey, session: Session, query: Annotated[schemas.CanaryQuery, Query()]
) -> schemas.CanaryResponse:
    """The version this scope, or the team's, runs on a share of the agent's calls, or none."""
    return await _canary_of(session, settings.written_to(actor.scope, team=query.team), slug, env=actor.env)


# The pipeline's alone, as the vendors are: a canary decides what a share of the calls runs.
@router.put("/v1/agents/{slug}/settings/canary", response_model_exclude_unset=True)
async def put_canary(
    slug: str, body: schemas.PutCanaryRequest, actor: PipelineKey, session: Session
) -> schemas.CanaryResponse:
    """One of the scope's versions on a share of the agent's calls; the rest run the others."""
    target = settings.written_to(actor.scope, team=body.team)
    await canaries.set_canary(
        session, target, slug, Canary(body.version, body.share), author=actor.name, note=body.note, at=now()
    )
    return await _canary_of(session, target, slug, env=actor.env)


# Cleared, every call runs the scope's newest version again, the canary's included.
@router.delete("/v1/agents/{slug}/settings/canary", response_model_exclude_unset=True)
async def clear_canary(
    slug: str, actor: PipelineKey, session: Session, query: Annotated[schemas.CanaryQuery, Query()]
) -> schemas.CanaryResponse:
    """The scope's canary cleared: one version for every call."""
    target = settings.written_to(actor.scope, team=query.team)
    await canaries.clear_canary(session, target, slug, author=actor.name, at=now())
    return await _canary_of(session, target, slug, env=actor.env)


# By the versions the call's head row kept, never the current ones.
@router.get("/v1/calls/{call}/settings", response_model_exclude_unset=True)
async def call_settings(call: str, actor: CallsKey, session: Session) -> schemas.CallSettingsResponse:
    """The exact settings and lexicon a call was built on."""
    head = await calls.head_of_call(session, call)
    if head is None or head.scope is None or head.scope.org != actor.org:
        raise NotFound(f"no call {call} in this org")
    versions = head.versions
    config = (
        None if versions.config is None else await settings.tuning_at(session, head.scope, head.agent, versions.config)
    )
    words = (
        None
        if versions.lexicon is None
        else await settings.lexicon_at(session, head.scope, head.agent, versions.lexicon)
    )
    ran = head.started_at is not None and await canaries.ran_the_canary(
        session, head.scope, head.agent, versions.config, datetime.fromtimestamp(head.started_at, UTC)
    )
    return schemas.CallSettingsResponse(
        config_version=versions.config,
        lexicon_version=versions.lexicon,
        config=None if config is None else _settings_row(config),
        lexicon=None if words is None else _lexicon_row(words),
        canary=ran,
    )


@router.get("/v1/agents/{slug}/lexicon")
async def get_lexicon(slug: str, actor: WordsKey, request: Request, session: Session) -> schemas.LexiconResponse:
    """The agent's words as this key sees them: yours, the team's and production's."""
    return await _lexicon_side_by_side(request, session, actor.scope, slug)


# A supervisor's key may write it: the words are theirs to fix.
@router.put("/v1/agents/{slug}/lexicon")
async def put_lexicon(
    slug: str, body: schemas.PutLexiconRequest, actor: WordsKey, request: Request, session: Session
) -> schemas.LexiconResponse:
    """The agent's next lexicon in this scope or the team's."""
    target = settings.written_to(actor.scope, team=body.team)
    wanted = Lexicon(said={item.word: item.spoken for item in body.lexicon.said}, heard=tuple(body.lexicon.heard))
    kept = await settings.lexicon_side_by_side(session, target, slug)
    newest = kept.team if target.holder == THE_ORGS_OWN else kept.yours
    before = Lexicon() if newest is None else newest.value
    changed = [
        name
        for name, is_new in (("says", wanted.said != before.said), ("hears", wanted.heard != before.heard))
        if is_new
    ]
    settings.refuse_what_the_class_sets(_registry(request).declared(slug), slug, changed)
    await settings.put_lexicon(
        session, target, slug, wanted, Written(author=actor.name, note=body.note, if_version=body.if_version)
    )
    return await _lexicon_side_by_side(request, session, actor.scope, slug)


@router.get("/v1/agents/{slug}/lexicon/history")
async def lexicon_history(
    slug: str, actor: WordsKey, session: Session, query: Annotated[schemas.HistoryQuery, Query()]
) -> schemas.LexiconHistoryResponse:
    """One scope's versions of the agent's lexicon, newest first."""
    target = settings.written_to(actor.scope, team=query.team)
    rows = await settings.lexicon_history(session, target, slug, limit=query.limit)
    return schemas.LexiconHistoryResponse(
        world=actor.env, holder=target.holder, rows=[_lexicon_row(row) for row in rows]
    )


# ── private ──


def _registry(request: Request) -> AgentRegistry:
    registry: AgentRegistry = request.app.state.registry
    return registry


def _vault(request: Request) -> Vault:
    vault: Vault = handles_of(request).vault
    return vault


def _fixed(request: Request, slug: str) -> frozenset[str]:
    declared = _registry(request).declared(slug)
    return frozenset() if declared is None else declared.fixed


async def _side_by_side(request: Request, session: Session, scope: Scope, slug: str) -> schemas.SettingsResponse:
    return await settings.settings_response(session, scope, slug, fixed=_fixed(request, slug))


async def _lexicon_side_by_side(request: Request, session: Session, scope: Scope, slug: str) -> schemas.LexiconResponse:
    kept = await settings.lexicon_side_by_side(session, scope, slug)
    return schemas.LexiconResponse(
        world=scope.env,
        yours=None if kept.yours is None else _lexicon_row(kept.yours),
        team=None if kept.team is None else _lexicon_row(kept.team),
        production=None if kept.production is None else _lexicon_row(kept.production),
        fixed=sorted(_fixed(request, slug) & {"says", "hears"}),
    )


# A key holding no agent writes the org's own scope: no call resolves in its holder's.
async def _canary_of(session: Session, scope: Scope, slug: str, *, env: Env) -> schemas.CanaryResponse:
    found = await canaries.standing_canary(session, scope, slug)
    return schemas.CanaryResponse(
        world=env,
        holder=scope.holder,
        canary=None
        if found is None
        else schemas.CanaryRow(
            holder=found.holder,
            version=found.canary.version,
            share=found.canary.share,
            author=found.author,
            note=found.note,
            set_at=found.set_at.timestamp(),
        ),
    )


def _settings_row(kept: Version[Tuning]) -> schemas.SettingsRow:
    return settings.settings_row(kept)


def _lexicon_row(kept: Version[Lexicon]) -> schemas.LexiconRow:
    return schemas.LexiconRow(
        holder=kept.holder,
        version=kept.version,
        author=kept.author,
        note=kept.note,
        set_at=kept.set_at.timestamp(),
        lexicon=schemas.LexiconBody(
            said=[Pronunciation(word=word, spoken=spoken) for word, spoken in kept.value.said.items()],
            heard=list(kept.value.heard),
        ),
    )


def _differing(ours: Version[Tuning] | None, theirs: Version[Tuning] | None) -> list[str]:
    mine = {} if ours is None else settings.dump_tuning(ours.value)
    yours = {} if theirs is None else settings.dump_tuning(theirs.value)
    return sorted(name for name in set(mine) | set(yours) if mine.get(name) != yours.get(name))
