"""A dictation: the words as they are spoken, over a socket a page opens with a minute's token."""

import hashlib
import hmac
import time
from collections.abc import AsyncIterator, Awaitable, Callable, Mapping
from dataclasses import dataclass

import jwt
from livekit import rtc
from livekit.agents import stt
from livekit.agents.utils.audio import AudioByteStream
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from runtime.actor import Scope
from runtime.enums import Env
from runtime.exceptions import ServiceUnavailable, Unauthorized, ValidationError
from runtime.kit.crypto import Vault
from runtime.kit.text import a_list, a_mapping
from runtime.providers.service.catalog import get_catalog
from runtime.providers.service.keyring import keys_of
from runtime.providers.service.refusals import refusing
from runtime.providers.service.stages import A_RATE, ears_outside_a_call, silence
from runtime.providers.service.transcription import FRAME_MS, TAIL_MS, Asked, ears_for, hear_out
from runtime.providers.stage import Running

# A dictation token opens one stream, within the minute it was minted in, for the org it names.
DICTATION_TOKEN_TTL_S = 60
# A dictation is a message spoken, not a meeting: two minutes, then the stream is closed.
LONGEST_DICTATION_S = 120
# Where a page opens the stream its token is for.
STREAM_PATH = "/v1/transcriptions/stream"
# The claim that says a token is a dictation's, and the header of a token the gateway signs with a key
# of its own: a LiveKit token names no key id, so a dictation token is never tried as one.
CLAIM = "dictates"
OUR_KEY_ID = "pinecall"

# What the stream is told once the words are settled, and what ends the audio.
DONE = "done"
END = "end"

NOT_OURS = "the token is no dictation token of this gateway's, or it expired: ask for a new one"
SIGNS_NO_TOKENS = "this gateway signs no tokens: PINECALL_TOKEN_KEY is unset"

type Said = Callable[[str, str], Awaitable[None]]


@dataclass(frozen=True, slots=True)
class Dictation:
    """What a dictation token carries: whose keys hear it, and the ears and language asked for."""

    scope: Scope
    asked: Asked


@dataclass(frozen=True, slots=True)
class Minted:
    """What a page opens one dictation with, for a minute: the token, where to open it, and whose ears will hear."""

    token: str
    vendor: str

    @property
    def path(self) -> str:
        """The socket's path, the token in it."""
        return f"{STREAM_PATH}?token={self.token}"

    @property
    def expires_in(self) -> int:
        """The seconds the token opens a stream for."""
        return DICTATION_TOKEN_TTL_S


# The words as they are spoken: a page asks its server for a token (the org's key mints it, the
# page never holds the key), then opens the socket with it and sends raw 16 kHz PCM as it records.
async def mint(session: AsyncSession, vault: Vault, scope: Scope, asked: Asked, own_key: str | None) -> Minted:
    """A minute's token for one dictation on the org's keys, with the ears and language asked for."""
    # Refused now, not when the page opens the socket: the ears must run on a key this org may use.
    running = ears_for(asked, await get_catalog(session), await keys_of(session, vault, scope))
    return Minted(token=sign_token(own_key, scope, asked), vendor=running.vendor)


# The page's socket carries no key: the token is all it has. The org's catalog and keys are read in a
# transaction of their own, closed before the stream opens, so a dictation holds no connection.
async def open_with(
    sessions: async_sessionmaker[AsyncSession], vault: Vault, own_key: str | None, token: str
) -> tuple[Dictation, Running]:
    """What a token asks for and the ears that will hear it; Unauthorized for any other token, or one expired."""
    dictation = read_token(own_key, token)
    if dictation is None:
        raise Unauthorized(NOT_OURS)
    async with sessions.begin() as session:
        catalog = await get_catalog(session)
        keys = await keys_of(session, vault, dictation.scope)
    return dictation, ears_for(dictation.asked, catalog, keys)


def sign_token(own_key: str | None, scope: Scope, asked: Asked) -> str:
    """A token a page opens one dictation with: the org's keys, never the org's key itself."""
    moment = int(time.time())
    claims = {
        "hear": list(asked.hear),
        "org": scope.org,
        "env": scope.env.value,
        "holder": scope.holder,
        "stt": asked.stt,
        "model": asked.model,
        "language": asked.language,
    }
    return jwt.encode(
        {"iat": moment, "exp": moment + DICTATION_TOKEN_TTL_S, CLAIM: claims},
        _signing_key(own_key),
        algorithm="HS256",
        headers={"kid": OUR_KEY_ID},
    )


def read_token(own_key: str | None, token: str) -> Dictation | None:
    """What a dictation token carries; None for any other token, or one expired."""
    try:
        decoded = jwt.decode(token, _signing_key(own_key), algorithms=["HS256"], options={"require": ["exp"]}, leeway=0)
    except jwt.PyJWTError:
        return None
    return _read_claims(decoded.get(CLAIM))


async def dictate(running: Running, heard: AsyncIterator[bytes | None], said: Said, hear: tuple[str, ...] = ()) -> None:
    """Raw 16 kHz PCM in until `heard` yields None or ends; each interim and final transcript out, then `done`."""

    async def relay(event: stt.SpeechEvent) -> None:
        text = event.alternatives[0].text.strip()
        if event.type is stt.SpeechEventType.INTERIM_TRANSCRIPT:
            await said("interim", text)
        elif event.type is stt.SpeechEventType.FINAL_TRANSCRIPT and text:
            await said("final", text)

    # The stream is opened inside what closes the ears: until 2026-11 it was opened before, and ears
    # whose `stream()` failed were never closed.
    async with ears_outside_a_call(running, None, hear) as ears:
        if not ears.capabilities.streaming:
            raise ValidationError(f"{running.vendor} does not stream: send the note whole to POST /v1/transcriptions")
        with refusing(running.vendor, "the dictation"):
            async with ears.stream(language=running.language) if running.language else ears.stream() as stream:
                spoken = _frames_of(heard)
                await hear_out(stream, spoken, silence(TAIL_MS), relay, at_most_s=LONGEST_DICTATION_S)
                await said(DONE, "")


async def _frames_of(heard: AsyncIterator[bytes | None]) -> AsyncIterator[rtc.AudioFrame]:
    chunker = AudioByteStream(A_RATE, 1, samples_per_channel=A_RATE * FRAME_MS // 1000)
    async for chunk in heard:
        if chunk is None:
            break
        for frame in chunker.push(chunk):
            yield frame
    for frame in chunker.flush():
        yield frame


# Signed with a key of its own, derived from the gateway's: a dictation token is never read as
# another of the gateway's tokens, nor another as one, and the key is always 32 bytes.
def _signing_key(own_key: str | None) -> bytes:
    if own_key is None:
        raise ServiceUnavailable(SIGNS_NO_TOKENS)
    return hmac.new(own_key.encode(), b"pinecall dictation", hashlib.sha256).digest()


# A claim that does not read as a dictation's is no dictation token: nothing of it is trusted.
def _read_claims(claims: object) -> Dictation | None:
    if not a_mapping(claims):
        return None
    org, holder, hear = claims.get("org"), claims.get("holder"), claims.get("hear", [])
    try:
        env = Env(str(claims.get("env")))
    except ValueError:
        return None
    if not isinstance(org, str) or not isinstance(holder, str) or not a_list(hear):
        return None
    asked = Asked(
        stt=_text_in(claims, "stt"),
        model=_text_in(claims, "model"),
        language=_text_in(claims, "language"),
        hear=tuple(str(term) for term in hear),
    )
    return Dictation(scope=Scope(org, env, holder), asked=asked)


def _text_in(claims: Mapping[str, object], name: str) -> str | None:
    said = claims.get(name)
    return said if isinstance(said, str) and said else None
