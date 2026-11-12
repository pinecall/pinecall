"""An agent's settings per env and scope: read, written, their history, a diff, a rollback, and the canary."""

from typing import Annotated, Literal

from fastapi import APIRouter, Query

from runtime.agents import schemas
from runtime.agents.auth import KnownAgent, PipelineKey, WordsKey
from runtime.agents.service import canaries, settings
from runtime.agents.service.versions import Written
from runtime.handles import TheSessions, TheVault
from runtime.postgres import Session

router = APIRouter()


@router.get("/v1/agents/{slug}/settings", response_model_exclude_unset=True)
async def get_settings(slug: KnownAgent, actor: WordsKey, session: Session) -> schemas.SettingsResponse:
    """The agent's settings as this key sees them: yours, the team's and production's."""
    return schemas.SettingsResponse.of(await settings.show_settings(session, actor.scope, slug))


# A whole replacement, guarded by the version it was read at; the read shows each scope's own
# newest and never the fallthrough, because if_version names the scope being written. A field
# nobody set is left out of the answer, never sent as null: the body's fields are optional. The use
# case opens its own transactions: none is held while a vendor is tried.
@router.put("/v1/agents/{slug}/settings", response_model_exclude_unset=True)
async def put_settings(
    slug: KnownAgent, body: schemas.PutSettingsRequest, actor: WordsKey, sessions: TheSessions, vault: TheVault
) -> schemas.SettingsResponse:
    """The agent's next version in this scope or the team's, checked as a call would build it."""
    wanted = settings.parse_settings(body.config.dump())
    written = Written(author=actor.name, note=body.note, if_version=body.if_version)
    shown = await settings.put_settings(sessions, vault, actor, slug, wanted, written, team=body.team)
    return schemas.SettingsResponse.of(shown)


@router.get("/v1/agents/{slug}/settings/history", response_model_exclude_unset=True)
async def list_settings_history(
    slug: KnownAgent, actor: WordsKey, session: Session, query: Annotated[schemas.HistoryQuery, Query()]
) -> schemas.SettingsHistoryResponse:
    """One scope's versions of the agent's settings, newest first."""
    history = await settings.list_settings_history(session, actor.scope, slug, team=query.team, limit=query.limit)
    return schemas.SettingsHistoryResponse.of(history)


@router.get("/v1/agents/{slug}/settings/diff", response_model_exclude_unset=True)
async def diff_settings(
    slug: KnownAgent,
    actor: WordsKey,
    session: Session,
    against: Annotated[Literal["team", "production"], Query()] = "production",
    team: Annotated[bool, Query()] = False,
) -> schemas.SettingsDiffResponse:
    """This key's scope's newest (the team's with `team`) against the team's or production's; what differs."""
    difference = await settings.diff_settings(session, actor.scope, slug, against=against, team=team)
    return schemas.SettingsDiffResponse.of(difference)


# A rollback writes a new version copying an old one; nothing is ever deleted.
@router.post("/v1/agents/{slug}/settings/rollback", response_model_exclude_unset=True)
async def roll_back_settings(
    slug: KnownAgent, body: schemas.RollbackSettingsRequest, actor: PipelineKey, session: Session
) -> schemas.SettingsResponse:
    """An old version brought back as the scope's next one."""
    shown = await settings.roll_back_settings(
        session, actor.scope, slug, body.version, author=actor.name, team=body.team
    )
    return schemas.SettingsResponse.of(shown)


@router.get("/v1/agents/{slug}/settings/canary", response_model_exclude_unset=True)
async def get_canary(
    slug: KnownAgent, actor: WordsKey, session: Session, query: Annotated[schemas.CanaryQuery, Query()]
) -> schemas.CanaryResponse:
    """The version this scope, or the team's, runs on a share of the agent's calls, or none."""
    return schemas.CanaryResponse.of(await canaries.show_canary(session, actor.scope, slug, team=query.team))


# The pipeline's alone, as the vendors are: a canary decides what a share of the calls runs.
@router.put("/v1/agents/{slug}/settings/canary", response_model_exclude_unset=True)
async def put_canary(
    slug: KnownAgent, body: schemas.PutCanaryRequest, actor: PipelineKey, session: Session
) -> schemas.CanaryResponse:
    """One of the scope's versions on a share of the agent's calls; the rest run the others."""
    canary = canaries.Canary(body.version, body.share)
    shown = await canaries.set_canary(
        session, actor.scope, slug, canary, author=actor.name, note=body.note, team=body.team
    )
    return schemas.CanaryResponse.of(shown)


# Cleared, every call runs the scope's newest version again, the canary's included.
@router.delete("/v1/agents/{slug}/settings/canary", response_model_exclude_unset=True)
async def clear_canary(
    slug: KnownAgent, actor: PipelineKey, session: Session, query: Annotated[schemas.CanaryQuery, Query()]
) -> schemas.CanaryResponse:
    """The scope's canary cleared: one version for every call."""
    shown = await canaries.clear_canary(session, actor.scope, slug, author=actor.name, team=query.team)
    return schemas.CanaryResponse.of(shown)
