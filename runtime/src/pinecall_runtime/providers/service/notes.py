"""A voice note transcribed outside a call, whole or as it is spoken: the ears a call hears with, on the same keys."""

import asyncio
import hashlib
import hmac
import time
from collections.abc import AsyncIterator, Awaitable, Callable
from dataclasses import dataclass
from typing import Never

import jwt
from livekit import rtc
from livekit.agents import APIConnectionError, APIError, APIStatusError, APITimeoutError, stt
from livekit.agents.utils import http_context
from livekit.agents.utils.audio import AudioByteStream
from livekit.agents.utils.codecs import AudioStreamDecoder
from pydantic import BaseModel, ConfigDict
from pydantic import ValidationError as PydanticValidationError

from pinecall_runtime.accounts.service.tokens import OUR_KEY_ID
from pinecall_runtime.enums import Env
from pinecall_runtime.exceptions import UpstreamError, ValidationError
from pinecall_runtime.kit.auth import Scope
from pinecall_runtime.providers.service.plugins import Running, words_of
from pinecall_runtime.providers.service.stages import stt_of

# A key's notes a minute: a chat's worth, never a batch job's.
TRANSCRIPTIONS_A_MINUTE = 30
# Eight megabytes is four minutes of 16 kHz PCM, longer than any note a chat takes.
LONGEST_NOTE = 8 * 1024 * 1024
WITHIN_S = 30.0
# Raw PCM as a browser records it; anything else is a container (WAV, WebM, Ogg, MP4, MP3) decoded here.
RAW = ("audio/l16", "audio/pcm")
SAMPLE_WIDTH = 2
# Frames of 20 ms, as a call pushes them; a streaming vendor is given a breath of silence at the end so
# it settles its last words before the stream closes.
FRAME_MS = 20
TAIL_MS = 600
# Once the audio is over, the words are settled after this long without a new one, whether or not the
# vendor closes its stream: Soniox's keeps it open.
SETTLED_S = 1.0
A_RATE = 16000
# A dictation token opens one stream, within the minute it was minted in, for the org it names.
DICTATION_TOKEN_TTL_S = 60
# A dictation is a message spoken, not a meeting: two minutes, then the stream is closed.
LONGEST_DICTATION_S = 120
# The words the ears are told to expect, as a call's lexicon tells them: at most this many, each short.
MOST_TERMS = 50
LONGEST_TERM = 40

# What the stream is told once the words are settled, and what ends the audio.
DONE = "done"
END = "end"


@dataclass(frozen=True, slots=True)
class Note:
    """What was recorded: raw PCM or a container's bytes, and how the request named it."""

    audio: bytes
    raw: bool
    rate: int
    channels: int


@dataclass(frozen=True, slots=True)
class Transcript:
    """What was said: the words, the language the vendor heard, and how much audio there was."""

    text: str
    language: str | None
    audio_ms: int


def note_of(audio: bytes, content_type: str) -> Note:
    """The note as the request names it: `audio/L16; rate=16000; channels=1` is raw PCM, the rest a container."""
    media, _, rest = content_type.partition(";")
    if media.strip().lower() not in RAW:
        return Note(audio=audio, raw=False, rate=A_RATE, channels=1)
    params = {k.strip().lower(): v.strip() for k, _, v in (p.partition("=") for p in rest.split(";")) if k.strip()}
    try:
        rate = int(params.get("rate", A_RATE))
        channels = int(params.get("channels", 1))
    except ValueError as bad:
        raise ValidationError(f"rate and channels are whole numbers: {content_type}") from bad
    if not 8000 <= rate <= 48000 or not 1 <= channels <= 2:
        raise ValidationError(f"rate is 8000 to 48000 and channels 1 or 2: {content_type}")
    return Note(audio=audio, raw=True, rate=rate, channels=channels)


# The plugin is built as a call builds it: the same vendor, model, key and operator's options. One
# that streams is fed the note frame by frame and closed; one that does not hears it whole.
async def transcribe(running: Running, note: Note, hear: tuple[str, ...] = ()) -> Transcript:
    """The note heard by the stage's ears; the vendor's refusal in its own words."""
    frames = [frame async for frame in _frames(note)]
    if not frames:
        raise ValidationError("the note holds no audio")
    audio_ms = round(sum(frame.duration for frame in frames) * 1000)
    async with http_context.open():
        ears = stt_of(running, None, hear)
        try:
            async with asyncio.timeout(WITHIN_S):
                heard = await (
                    _streamed(ears, frames, running.language)
                    if ears.capabilities.streaming
                    else _whole(ears, frames, running.language)
                )
        except TimeoutError as slow:
            raise UpstreamError(f"{running.vendor} did not finish the note within {WITHIN_S:.0f} s") from slow
        except (APIConnectionError, APITimeoutError) as silent:
            raise UpstreamError(f"{running.vendor} did not answer: {words_of(silent)}") from silent
        except APIError as refused:
            status = f" ({refused.status_code})" if isinstance(refused, APIStatusError) else ""
            raise UpstreamError(f"{running.vendor} refused the note{status}: {words_of(refused)}") from refused
        finally:
            await ears.aclose()
    text = " ".join(part for part, _ in heard if part).strip()
    spoken = next((language for _, language in heard if language), None)
    return Transcript(text=text, language=spoken or running.language, audio_ms=audio_ms)


async def _streamed(
    ears: stt.STT[Never], frames: list[rtc.AudioFrame], language: str | None
) -> list[tuple[str, str | None]]:
    stream = ears.stream(language=language) if language else ears.stream()
    rate, channels = frames[0].sample_rate, frames[0].num_channels
    silence = rtc.AudioFrame(
        bytes(rate * channels * SAMPLE_WIDTH * TAIL_MS // 1000), rate, channels, rate * TAIL_MS // 1000
    )
    heard: list[tuple[str, str | None]] = []
    words = _Words()

    async def listen() -> None:
        async for event in stream:
            if event.alternatives and event.type in _WORDS:
                words.came()
            if event.type is stt.SpeechEventType.FINAL_TRANSCRIPT and event.alternatives:
                best = event.alternatives[0]
                heard.append((best.text.strip(), _language(best)))

    async with stream:
        listening = asyncio.create_task(listen())
        try:
            for frame in frames:
                stream.push_frame(frame)
            stream.push_frame(silence)
            stream.end_input()
            await words.settled(listening)
        finally:
            listening.cancel()
    return heard


_WORDS = frozenset({stt.SpeechEventType.INTERIM_TRANSCRIPT, stt.SpeechEventType.FINAL_TRANSCRIPT})


class _Words:
    """When the ears last said a word, to know when they are done once the audio is over."""

    def __init__(self) -> None:
        self.last = asyncio.get_running_loop().time()

    def came(self) -> None:
        self.last = asyncio.get_running_loop().time()

    async def settled(self, listening: asyncio.Task[None]) -> None:
        """Until the vendor closes its stream, or SETTLED_S passes with no new word; WITHIN_S at most."""
        loop = asyncio.get_running_loop()
        ended = loop.time()
        self.last = max(self.last, ended)
        while not listening.done():
            now = loop.time()
            if now - self.last >= SETTLED_S or now - ended >= WITHIN_S:
                return
            await asyncio.wait({listening}, timeout=0.1)
        listening.result()


async def _whole(
    ears: stt.STT[Never], frames: list[rtc.AudioFrame], language: str | None
) -> list[tuple[str, str | None]]:
    event = await (ears.recognize(frames, language=language) if language else ears.recognize(frames))
    return [(alternative.text.strip(), _language(alternative)) for alternative in event.alternatives[:1]]


def _language(alternative: stt.SpeechData) -> str | None:
    language = getattr(alternative, "language", None)
    return str(language) if language else None


async def _frames(note: Note) -> AsyncIterator[rtc.AudioFrame]:
    if note.raw:
        chunker = AudioByteStream(note.rate, note.channels, samples_per_channel=note.rate * FRAME_MS // 1000)
        for frame in [*chunker.push(note.audio), *chunker.flush()]:
            yield frame
        return
    decoder = AudioStreamDecoder(sample_rate=A_RATE, num_channels=1)
    decoder.push(note.audio)
    decoder.end_input()
    try:
        async for frame in decoder:
            yield frame
    except Exception as unread:
        raise ValidationError(f"the note is no audio this server reads: {unread}") from unread
    finally:
        await decoder.aclose()


# ── dictation: the words as they are spoken, over a socket a page opens with a short token ──


class Dictation(BaseModel):
    """What a dictation token carries: whose keys hear it, and the ears and language asked for."""

    model_config = ConfigDict(frozen=True, extra="ignore")
    org: str
    env: Env
    holder: str
    stt: str | None = None
    model: str | None = None
    language: str | None = None
    hear: tuple[str, ...] = ()

    @property
    def scope(self) -> Scope:
        """The org and env whose keys the ears run on."""
        return Scope(self.org, self.env, self.holder)


# Signed with a key of its own, derived from the gateway's: a dictation token is never read as
# another of the gateway's tokens, nor another as one, and the key is always 32 bytes.
def _signing_key(own_key: str) -> bytes:
    return hmac.new(own_key.encode(), b"pinecall dictation", hashlib.sha256).digest()


def terms_of(hear: list[str] | None) -> tuple[str, ...]:
    """The words to expect, each once, trimmed, the long and the empty left out."""
    kept = (term.strip() for term in hear or ())
    return tuple(dict.fromkeys(term for term in kept if term and len(term) <= LONGEST_TERM))[:MOST_TERMS]


def dictation_token(
    own_key: str,
    scope: Scope,
    stt: str | None,
    model: str | None,
    language: str | None,
    hear: tuple[str, ...] = (),
) -> str:
    """A token a page opens one dictation with: the org's keys, never the org's key itself."""
    moment = int(time.time())
    claims = {
        "hear": list(hear),
        "org": scope.org,
        "env": scope.env.value,
        "holder": scope.holder,
        "stt": stt,
        "model": model,
        "language": language,
    }
    return jwt.encode(
        {"iat": moment, "exp": moment + DICTATION_TOKEN_TTL_S, "dictates": claims},
        _signing_key(own_key),
        algorithm="HS256",
        headers={"kid": OUR_KEY_ID},
    )


def dictation_of(own_key: str, token: str) -> Dictation | None:
    """What a dictation token carries; None for any other token, or one expired."""
    try:
        decoded = jwt.decode(token, _signing_key(own_key), algorithms=["HS256"], options={"require": ["exp"]}, leeway=0)
        return Dictation.model_validate(decoded.get("dictates"))
    except (jwt.PyJWTError, PydanticValidationError, AttributeError):
        return None


type Said = Callable[[str, str], Awaitable[None]]


async def dictate(running: Running, heard: AsyncIterator[bytes | None], said: Said, hear: tuple[str, ...] = ()) -> None:
    """Raw 16 kHz PCM in, as it is spoken, until `heard` yields None or ends; each interim and final
    transcript out through `said(kind, text)`, then `done`. Ears that do not stream are refused."""
    async with http_context.open():
        ears = stt_of(running, None, hear)
        if not ears.capabilities.streaming:
            await ears.aclose()
            raise ValidationError(f"{running.vendor} does not stream: send the note whole to POST /v1/transcriptions")
        stream = ears.stream(language=running.language) if running.language else ears.stream()
        chunker = AudioByteStream(A_RATE, 1, samples_per_channel=A_RATE * FRAME_MS // 1000)
        silence = rtc.AudioFrame(bytes(A_RATE * SAMPLE_WIDTH * TAIL_MS // 1000), A_RATE, 1, A_RATE * TAIL_MS // 1000)

        words = _Words()

        async def relay() -> None:
            async for event in stream:
                if not event.alternatives:
                    continue
                if event.type in _WORDS:
                    words.came()
                text = event.alternatives[0].text.strip()
                if event.type is stt.SpeechEventType.INTERIM_TRANSCRIPT:
                    await said("interim", text)
                elif event.type is stt.SpeechEventType.FINAL_TRANSCRIPT and text:
                    await said("final", text)

        relaying = asyncio.create_task(relay())
        try:
            async with asyncio.timeout(LONGEST_DICTATION_S):
                async for chunk in heard:
                    if chunk is None:
                        break
                    for frame in chunker.push(chunk):
                        stream.push_frame(frame)
            for frame in chunker.flush():
                stream.push_frame(frame)
            stream.push_frame(silence)
            stream.end_input()
            await words.settled(relaying)
            await said(DONE, "")
        except TimeoutError:
            stream.end_input()
            await said(DONE, "")
        except (APIConnectionError, APITimeoutError) as silent:
            raise UpstreamError(f"{running.vendor} did not answer: {words_of(silent)}") from silent
        except APIError as refused:
            status = f" ({refused.status_code})" if isinstance(refused, APIStatusError) else ""
            raise UpstreamError(f"{running.vendor} refused the dictation{status}: {words_of(refused)}") from refused
        finally:
            relaying.cancel()
            await stream.aclose()
            await ears.aclose()
