"""A voice note heard outside a call: the ears a call hears with, on the same keys, said back as text."""

import asyncio
import dataclasses
from collections.abc import AsyncIterator, Awaitable, Callable, Sequence
from dataclasses import dataclass
from typing import Never

from livekit import rtc
from livekit.agents import stt
from livekit.agents.utils.audio import AudioByteStream
from livekit.agents.utils.codecs import AudioStreamDecoder
from sqlalchemy.ext.asyncio import AsyncSession

from runtime.actor import Scope
from runtime.enums import Stage
from runtime.exceptions import UpstreamError, ValidationError
from runtime.kit.crypto import Vault
from runtime.providers.catalog import Catalog
from runtime.providers.service import plugins
from runtime.providers.service.catalog import get_catalog
from runtime.providers.service.keyring import Keyring, keys_of
from runtime.providers.service.pipeline import stage_on_its_key
from runtime.providers.service.refusals import refusing
from runtime.providers.service.stages import A_RATE, ears_outside_a_call, silence
from runtime.providers.stage import Model, Running, primary_language

# A key's notes a minute: a chat's worth, never a batch job's.
TRANSCRIPTIONS_A_MINUTE = 30
# Eight megabytes is four minutes of 16 kHz PCM, longer than any note a chat takes.
LONGEST_NOTE = 8 * 1024 * 1024
WITHIN_S = 30.0
# Raw PCM as a browser records it; anything else is a container (WAV, WebM, Ogg, MP4, MP3) decoded here.
RAW = ("audio/l16", "audio/pcm")
# Frames of 20 ms, as a call pushes them; a streaming vendor is given a breath of silence at the end so
# it settles its last words before the stream closes.
FRAME_MS = 20
TAIL_MS = 600
# Once the audio is over, the words are settled after this long without a new one, whether or not the
# vendor closes its stream: Soniox's keeps it open.
SETTLED_S = 1.0
# The words the ears are told to expect, as a call's lexicon tells them: at most this many, each short.
MOST_TERMS = 50
LONGEST_TERM = 40

_WORDS = frozenset({stt.SpeechEventType.INTERIM_TRANSCRIPT, stt.SpeechEventType.FINAL_TRANSCRIPT})

type Heard = Callable[[stt.SpeechEvent], Awaitable[None]]


@dataclass(frozen=True, slots=True)
class Asked:
    """The ears a note or a dictation asks for: a vendor and its model, or the box's default; a language; the words."""

    stt: str | None = None
    model: str | None = None
    language: str | None = None
    hear: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class Note:
    """What was recorded: raw PCM or a container's bytes, and how the request named it."""

    audio: bytes
    raw: bool
    rate: int
    channels: int


@dataclass(frozen=True, slots=True)
class Transcript:
    """What was said: the words, the language the vendor heard, how much audio there was, and whose ears heard it."""

    text: str
    language: str | None
    audio_ms: int
    vendor: str


# A voice note from a chat, said back as text by the ears a call hears with: the box's default
# vendor, or the one `stt` names (`model` too), on the org's own key or one the box lends.
async def hear_note(
    session: AsyncSession, vault: Vault, scope: Scope, audio: bytes, content_type: str, asked: Asked
) -> Transcript:
    """The note's words, heard on the keys the org's calls run on."""
    note = read_note(audio, content_type)
    running = ears_for(asked, await get_catalog(session), await keys_of(session, vault, scope))
    return await transcribe(running, note, asked.hear)


def read_asked(stt: str | None, model: str | None, language: str | None, hear: Sequence[str] | None) -> Asked:
    """What a request's query asks for: the language cut to its base, the words trimmed, each once."""
    return Asked(stt=stt or None, model=model or None, language=primary_language(language), hear=terms_of(hear))


# `stt` names a vendor, never a model: a word that is no vendor is refused as one, not tried as a model.
def ears_for(asked: Asked, catalog: Catalog, keys: Keyring) -> Running:
    """The ears asked for, on a key this org may run them on, hearing the language asked."""
    named = None if not asked.stt else Model(vendor=plugins.vendor_doing(asked.stt, Stage.stt), model=asked.model or "")
    running = stage_on_its_key(Stage.stt, named, catalog, keys)
    return dataclasses.replace(running, language=asked.language)


def terms_of(hear: Sequence[str] | None) -> tuple[str, ...]:
    """The words to expect, each once, trimmed, the long and the empty left out."""
    kept = (term.strip() for term in hear or ())
    return tuple(dict.fromkeys(term for term in kept if term and len(term) <= LONGEST_TERM))[:MOST_TERMS]


def read_note(audio: bytes, content_type: str) -> Note:
    """The note as the request names it: `audio/L16; rate=16000; channels=1` is raw PCM, the rest a container."""
    if not audio:
        raise ValidationError("the body is the audio, and it is empty")
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
    frames = [frame async for frame in _frames_of(note)]
    if not frames:
        raise ValidationError("the note holds no audio")
    audio_ms = round(sum(frame.duration for frame in frames) * 1000)
    try:
        async with ears_outside_a_call(running, None, hear) as ears, asyncio.timeout(WITHIN_S):
            with refusing(running.vendor, "the note"):
                heard = await (
                    _hear_streamed(ears, frames, running.language)
                    if ears.capabilities.streaming
                    else _hear_whole(ears, frames, running.language)
                )
    except TimeoutError as slow:
        raise UpstreamError(
            f"{running.vendor} did not finish the note within {WITHIN_S:.0f} s", vendor=running.vendor, retryable=True
        ) from slow
    text = " ".join(part for part, _ in heard if part).strip()
    spoken = next((language for _, language in heard if language), None)
    return Transcript(text=text, language=spoken or running.language, audio_ms=audio_ms, vendor=running.vendor)


# The one way audio is fed to ears that stream outside a call, for a note whole and for a dictation as
# it is spoken: the frames as they come, a breath of silence after the last, and then the wait for the
# words to settle. Each event that carries words is handed to `on_event` as it comes. Frames that
# are still coming after `at_most_s` end the input there, with no wait: whoever speaks was cut.
async def hear_out(
    stream: stt.RecognizeStream,
    frames: AsyncIterator[rtc.AudioFrame],
    tail: rtc.AudioFrame,
    on_event: Heard,
    *,
    at_most_s: float | None = None,
) -> None:
    """Feed the open stream its frames and wait until the ears have said their last word."""
    quiet = _Quiet()

    async def listen() -> None:
        async for event in stream:
            if not event.alternatives:
                continue
            if event.type in _WORDS:
                quiet.end()
            await on_event(event)

    listening = asyncio.create_task(listen())
    try:
        try:
            async with asyncio.timeout(at_most_s):
                async for frame in frames:
                    stream.push_frame(frame)
        except TimeoutError:
            stream.end_input()
            return
        stream.push_frame(tail)
        stream.end_input()
        await quiet.wait_for(listening)
    finally:
        listening.cancel()


async def _hear_streamed(
    ears: stt.STT[Never], frames: list[rtc.AudioFrame], language: str | None
) -> list[tuple[str, str | None]]:
    heard: list[tuple[str, str | None]] = []

    async def keep(event: stt.SpeechEvent) -> None:
        if event.type is stt.SpeechEventType.FINAL_TRANSCRIPT:
            best = event.alternatives[0]
            heard.append((best.text.strip(), _language_of(best)))

    tail = silence(TAIL_MS, frames[0].sample_rate, frames[0].num_channels)
    async with ears.stream(language=language) if language else ears.stream() as stream:
        await hear_out(stream, _each(frames), tail, keep)
    return heard


async def _hear_whole(
    ears: stt.STT[Never], frames: list[rtc.AudioFrame], language: str | None
) -> list[tuple[str, str | None]]:
    event = await (ears.recognize(frames, language=language) if language else ears.recognize(frames))
    return [(alternative.text.strip(), _language_of(alternative)) for alternative in event.alternatives[:1]]


class _Quiet:
    """When the ears last said a word, to know when they are done once the audio is over."""

    def __init__(self) -> None:
        self.last = asyncio.get_running_loop().time()

    def end(self) -> None:
        """A word came: the quiet starts again from now."""
        self.last = asyncio.get_running_loop().time()

    async def wait_for(self, listening: asyncio.Task[None]) -> None:
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


def _language_of(alternative: stt.SpeechData) -> str | None:
    language = getattr(alternative, "language", None)
    return str(language) if language else None


async def _each(frames: list[rtc.AudioFrame]) -> AsyncIterator[rtc.AudioFrame]:
    for frame in frames:
        yield frame


async def _frames_of(note: Note) -> AsyncIterator[rtc.AudioFrame]:
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
