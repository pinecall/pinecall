"""What a worker asks of an agent before a call: the agent as the call runs it, its stages on their keys, its melody."""

from typing import Annotated

from fastapi import APIRouter, Query, Response

from runtime.agents.auth import (
    DeclarationKey,
    KnownAgent,
    TheAgent,
    TheHeldAgent,
    TheMelody,
    ThePicked,
    TheTestValues,
    TheVendorHealth,
    WorkerKey,
)
from runtime.agents.service import hold_audio, pipeline, settings
from runtime.handles import TheVault
from runtime.postgres import Session
from runtime.wire import worker

router = APIRouter()

OGG = "audio/ogg"


@router.get("/v1/agents/{slug}/config")
async def get_config(
    agent: TheHeldAgent, actor: DeclarationKey, session: Session, picked: ThePicked, test: TheTestValues
) -> worker.AgentConfigResponse:
    """The agent as the scope runs it, for the call named: its declaration under the settings."""
    running = await settings.declaration_for_call(session, agent.whole, actor.scope, picked, test)
    return worker.AgentConfigResponse.model_validate(running, from_attributes=True)


# The one answer that carries keys: to the fleet's key, or the org's own worker's.
@router.get("/v1/agents/{slug}/provider-keys")
async def get_provider_keys(
    agent: TheHeldAgent,
    actor: WorkerKey,
    vault: TheVault,
    health: TheVendorHealth,
    session: Session,
    picked: ThePicked,
    test: TheTestValues,
) -> worker.PipelineKeys:
    """The three stages a call of the agent runs, each on its key, and the org's collector."""
    stages = await pipeline.stages_for_worker(session, vault, actor, agent.whole, health, picked=picked, test=test)
    return worker.PipelineKeys.model_validate(stages, from_attributes=True)


@router.get("/v1/agents/{slug}/hold-audio")
async def get_hold(agent: TheAgent, actor: WorkerKey, session: Session) -> worker.HoldAudio:
    """What a caller of the agent hears while a tool runs."""
    return worker.HoldAudio.model_validate(await hold_audio.get_hold(session, actor.scope, agent), from_attributes=True)


# The class's own melody comes in here, on the app's key: only the file the class declared, by its
# hash, and nothing for an agent whose class declares none (the pipeline's endpoint is the org's).
@router.put("/v1/agents/{slug}/hold-audio")
async def ship_clip(
    agent: TheAgent,
    actor: WorkerKey,
    data: TheMelody,
    session: Session,
    name: Annotated[str | None, Query(max_length=200)] = None,
) -> worker.HoldAudio:
    """The file the agent's class declares as its melody, uploaded by the process that holds it."""
    held = await hold_audio.ship_clip(session, actor.scope, agent, data, name)
    return worker.HoldAudio.model_validate(held, from_attributes=True)


@router.get("/v1/agents/{slug}/hold-audio/audio")
async def get_clip(slug: KnownAgent, actor: WorkerKey, session: Session) -> Response:
    """The org's own clip, Ogg Opus."""
    return Response(await hold_audio.get_clip(session, actor.scope, slug), media_type=OGG)
