"""The hold melody from the console: what an agent plays while a tool runs, a file of the org's, silence, the wait."""

from typing import Annotated

from fastapi import APIRouter, Query

from runtime.agents import schemas
from runtime.agents.auth import PipelineKey, TheAgent, TheMelody
from runtime.agents.service import hold_audio
from runtime.enums import HoldPlayed
from runtime.postgres import Session
from runtime.wire import worker

router = APIRouter()


# The melody is the agent's in an env, whoever holds it.
@router.get("/v1/agents/{slug}/pipeline/hold-audio")
async def get_hold(agent: TheAgent, actor: PipelineKey, session: Session) -> worker.HoldAudio:
    """What the agent plays while a tool runs, and after how long: the runtime's melody, silence, or its own clip."""
    return worker.HoldAudio.model_validate(await hold_audio.get_hold(session, actor.scope, agent), from_attributes=True)


# The body is the file, no multipart; the name rides the query. An agent whose class declares its
# melody takes no file here: the class ships its own, through `PUT /v1/agents/{slug}/hold-audio`.
@router.put("/v1/agents/{slug}/pipeline/hold-audio")
async def put_clip(
    agent: TheAgent,
    actor: PipelineKey,
    data: TheMelody,
    session: Session,
    name: Annotated[str | None, Query(max_length=200)] = None,
) -> worker.HoldAudio:
    """A file of the org's as the agent's melody, from the next call on; 409 while its class declares the melody."""
    held = await hold_audio.put_clip(session, actor.scope, agent, data, name)
    return worker.HoldAudio.model_validate(held, from_attributes=True)


@router.put("/v1/agents/{slug}/pipeline/hold-audio/played")
async def put_played(
    agent: TheAgent, body: schemas.PlayedRequest, actor: PipelineKey, session: Session
) -> worker.HoldAudio:
    """The runtime's melody back, or silence; an uploaded clip is forgotten either way, the wait kept."""
    held = await hold_audio.put_played(session, actor.scope, agent, HoldPlayed(body.played))
    return worker.HoldAudio.model_validate(held, from_attributes=True)


@router.put("/v1/agents/{slug}/pipeline/hold-audio/after")
async def put_wait(
    agent: TheAgent, body: schemas.AfterRequest, actor: PipelineKey, session: Session
) -> worker.HoldAudio:
    """Seconds of the agent's quiet before the melody starts, from the next call on; null is the runtime's."""
    held = await hold_audio.put_wait(session, actor.scope, agent, body.after_s)
    return worker.HoldAudio.model_validate(held, from_attributes=True)
