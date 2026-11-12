"""The voice picker: a vendor's voices listed, and one of them saying a line."""

from typing import Annotated

from fastapi import APIRouter, Query, Response

from runtime.handles import TheVault
from runtime.postgres import Session
from runtime.providers import schemas
from runtime.providers.auth import PipelineKey, a_sample_a_time
from runtime.providers.service import speech, voices

router = APIRouter()

WAV = "audio/wav"


# Built as a call builds the stage: the operator's options, on the key a call would use.
@router.get("/v1/voices")
async def list_voices(
    actor: PipelineKey,
    vault: TheVault,
    session: Session,
    tts: Annotated[str, Query(min_length=1)],
    language: Annotated[str | None, Query()] = None,
) -> schemas.VoicesListed:
    """The voices the providers row lists for a vendor, else its plugin's; neither is a 404."""
    return schemas.VoicesListed.of(await voices.list_for(session, vault, actor.scope, tts, language))


# The answer is the WAV itself, its latencies in Server-Timing, which a browser shows.
@router.post("/v1/voices/sample", dependencies=[a_sample_a_time])
async def sample_voice(
    body: schemas.VoiceSampleRequest, actor: PipelineKey, vault: TheVault, session: Session
) -> Response:
    """The line said by that vendor's voice, over the path a call speaks on."""
    asked = speech.Asked(tts=body.tts, voice=body.voice, model=body.model, language=body.language, text=body.text)
    heard = await speech.sample_for(session, vault, actor.scope, asked)
    return Response(content=heard.wav, media_type=WAV, headers={"Server-Timing": heard.timing})
