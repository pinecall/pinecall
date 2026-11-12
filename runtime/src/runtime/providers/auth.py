"""Providers' dependencies: the keys that open its endpoints, the guards that pace a key, what a note asks for."""

from collections.abc import Callable
from dataclasses import dataclass
from typing import Annotated

from fastapi import Depends, Query, Request
from starlette.requests import HTTPConnection

from runtime.actor import Actor
from runtime.auth import Authenticator
from runtime.enums import KeyScope
from runtime.exceptions import TooManyRequests
from runtime.handles import settings_of
from runtime.kit.http import read_capped_body
from runtime.kit.time import A_MINUTE_S
from runtime.platform import service as platform
from runtime.providers.service import transcription

a_providers_key = Authenticator(KeyScope.providers)
a_pipeline_key = Authenticator(KeyScope.pipeline)
# A note is transcribed on the key a chat runs on (talk) or on one that tunes the pipeline.
an_ears_key = Authenticator(KeyScope.talk, KeyScope.pipeline)

ProvidersKey = Annotated[Actor, Depends(a_providers_key)]
PipelineKey = Annotated[Actor, Depends(a_pipeline_key)]
EarsKey = Annotated[Actor, Depends(an_ears_key)]


def samples_of(connection: HTTPConnection) -> platform.AttemptThrottle:
    """The voice samples a key may ask for a minute."""
    throttle: platform.AttemptThrottle = connection.state.samples
    return throttle


def transcriptions_of(connection: HTTPConnection) -> platform.AttemptThrottle:
    """The notes a key may send a minute, and the dictations it may open."""
    throttle: platform.AttemptThrottle = connection.state.transcriptions
    return throttle


# A sample, a note and a dictation each cost vendor time and write no usage row, so a key gets so many of
# each a minute. Each guard counts under a name of its own: until 2026-11 the three counted under the
# key's bare id, so thirty samples left a key with no note to send, told it had sent "its 30 notes".
@dataclass(frozen=True, slots=True)
class Paced:
    """A dependency: one more of something a key asks for this minute, or the refusal that says the ceiling."""

    key: Authenticator
    throttle_of: Callable[[HTTPConnection], platform.AttemptThrottle]
    # What the count is kept under, after the key's id.
    counted: str
    # The sentence a key past the ceiling reads, the ceiling as `{tries}`.
    refusal: str

    async def __call__(self, request: Request) -> None:
        """Count this attempt; TooManyRequests past the minute's ceiling."""
        actor = await self.key(request)
        throttle = self.throttle_of(request)
        if not await throttle.is_allowed(f"{actor.key_id} {self.counted}"):
            raise TooManyRequests(self.refusal.format(tries=throttle.tries), retry_after_s=A_MINUTE_S)


a_sample_a_time = Depends(
    Paced(
        a_pipeline_key,
        samples_of,
        "voices/sample",
        "this key asked for its {tries} samples this minute: the ceiling is {tries} a minute",
    )
)
a_note_a_time = Depends(
    Paced(
        an_ears_key,
        transcriptions_of,
        "transcriptions",
        "this key sent its {tries} notes this minute: the ceiling is {tries} a minute",
    )
)
a_dictation_a_time = Depends(
    Paced(
        an_ears_key,
        transcriptions_of,
        "transcriptions/token",
        "this key asked for its {tries} dictations this minute: the ceiling is {tries} a minute",
    )
)


# The key a dictation token is signed with is derived from the gateway's own; None on a gateway that
# was given none, which the use case refuses in its sentence (a socket is refused with a close frame).
def token_key_of(connection: HTTPConnection) -> str | None:
    """The gateway's own signing key, or None where PINECALL_TOKEN_KEY is unset."""
    key = settings_of(connection).token_key
    return None if key is None else key.get_secret_value()


TheTokenKey = Annotated[str | None, Depends(token_key_of)]


# The body is the audio: raw PCM as a browser records it (`Content-Type: audio/L16; rate=16000;
# channels=1`), or a container (WAV, WebM, Ogg, MP4, MP3) decoded by the use case.
async def read_note_audio(request: Request) -> bytes:
    """A note's audio, read up to what a note may weigh."""
    return await read_capped_body(request, transcription.LONGEST_NOTE, "a note")


TheNoteAudio = Annotated[bytes, Depends(read_note_audio)]


def read_ears_asked(
    stt: str | None = None,
    model: str | None = None,
    language: str | None = None,
    hear: Annotated[list[str] | None, Query()] = None,
) -> transcription.Asked:
    """The ears a note or a dictation asks for in its query: a vendor and model, the language, the words to expect."""
    return transcription.read_asked(stt, model, language, hear)


TheEarsAsked = Annotated[transcription.Asked, Depends(read_ears_asked)]
