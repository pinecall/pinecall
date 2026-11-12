"""A voice note said back as text, and a dictation heard as it is spoken over a socket a minute's token opens."""

import contextlib
from collections.abc import AsyncIterator
from typing import Annotated

from fastapi import APIRouter, Header, WebSocket, WebSocketDisconnect

from runtime.exceptions import PinecallError
from runtime.handles import TheSessions, TheVault
from runtime.kit.websockets import close_reason, code_of, refuse_socket
from runtime.postgres import Session
from runtime.providers import schemas
from runtime.providers.auth import (
    EarsKey,
    TheEarsAsked,
    TheNoteAudio,
    TheTokenKey,
    a_dictation_a_time,
    a_note_a_time,
)
from runtime.providers.service import dictation, transcription

router = APIRouter()


# A voice note from a chat, said back as text by the ears a call hears with: the box's default
# vendor, or the one `stt` names (`model` too), on the org's own key or one the box lends.
# `language` is the note's, as a call's.
@router.post("/v1/transcriptions", dependencies=[a_note_a_time])
async def transcribe_note(
    actor: EarsKey,
    audio: TheNoteAudio,
    asked: TheEarsAsked,
    vault: TheVault,
    session: Session,
    content_type: Annotated[str, Header()] = "",
) -> schemas.TranscriptionResponse:
    """The note's words, heard on the keys the org's calls run on."""
    heard = await transcription.hear_note(session, vault, actor.scope, audio, content_type, asked)
    return schemas.TranscriptionResponse.of(heard)


# The words as they are spoken: a page asks its server for a token (the org's key mints it, the
# page never holds the key), then opens the socket with it and sends raw 16 kHz PCM as it records.
@router.post("/v1/transcriptions/token", dependencies=[a_dictation_a_time])
async def mint_dictation_token(
    actor: EarsKey, asked: TheEarsAsked, own_key: TheTokenKey, vault: TheVault, session: Session
) -> schemas.DictationTokenResponse:
    """A minute's token for one dictation on the org's keys, with the ears and language asked for."""
    return schemas.DictationTokenResponse.of(await dictation.mint(session, vault, actor.scope, asked, own_key))


# Raw 16 kHz PCM frames in, `{type: interim|final, text}` out as it is heard; `end` closes the audio
# and `{type: done}` follows once the words are settled.
@router.websocket("/v1/transcriptions/stream")
async def stream_dictation(
    websocket: WebSocket, sessions: TheSessions, vault: TheVault, own_key: TheTokenKey, token: str = ""
) -> None:
    """One dictation, heard as it is spoken by the ears its token asked for."""
    try:
        opened, running = await dictation.open_with(sessions, vault, own_key, token)
    except PinecallError as refused:
        await refuse_socket(websocket, refused)
        return
    await websocket.accept()

    async def say(kind: str, text: str) -> None:
        await websocket.send_json({"type": kind, "text": text})

    try:
        await dictation.dictate(running, _audio_from(websocket), say, opened.asked.hear)
        await websocket.close()
    except PinecallError as refused:
        with contextlib.suppress(RuntimeError, WebSocketDisconnect):
            await websocket.close(code=code_of(refused), reason=close_reason(str(refused)))
    except (RuntimeError, WebSocketDisconnect):
        return


# The socket's framing: binary frames are audio, the text `end` closes it, a disconnect ends it.
async def _audio_from(websocket: WebSocket) -> AsyncIterator[bytes | None]:
    try:
        while True:
            message = await websocket.receive()
            if message["type"] == "websocket.disconnect":
                return
            if message.get("bytes"):
                yield message["bytes"]
            elif message.get("text") == dictation.END:
                yield None
                return
    except WebSocketDisconnect:
        return
