"""A line spoken by a stage's voice outside a call: as WAV with its latencies, or as PCM timed word by word."""

import dataclasses
import io
import time
import wave
from collections.abc import AsyncIterator, Awaitable, Callable
from dataclasses import dataclass

from livekit.agents.tts import SynthesizedAudio
from livekit.agents.types import USERDATA_TIMED_TRANSCRIPT, TimedString
from sqlalchemy.ext.asyncio import AsyncSession

from runtime.actor import Scope
from runtime.enums import Stage
from runtime.exceptions import ValidationError
from runtime.kit.crypto import Vault
from runtime.kit.text import a_list
from runtime.providers.service import plugins
from runtime.providers.service.catalog import get_catalog
from runtime.providers.service.keyring import keys_of
from runtime.providers.service.pipeline import stage_on_its_key
from runtime.providers.service.refusals import refusing
from runtime.providers.service.stages import SAMPLE_WIDTH, voice_outside_a_call
from runtime.providers.stage import Running, Voice, primary_language

# Samples cost vendor time and write no usage row, so a key gets this many a minute.
SAMPLES_A_MINUTE = 30
# Long enough for a greeting, short enough to keep the vendor's cost to seconds.
LONGEST_SAMPLE = 400
# What a voice says when the picker names no line and the providers row has none in the language.
A_LINE = "Hello, this is the voice you are listening to."
# What a vendor that turned the voice down refused, in the sentence its no is told with.
THE_VOICE = "the voice"


@dataclass(frozen=True, slots=True)
class Asked:
    """What a sample was asked for: which vendor, voice, model and words to hear."""

    tts: str
    voice: str
    model: str | None = None
    language: str | None = None
    text: str | None = None


@dataclass(frozen=True, slots=True)
class Sample:
    """A line spoken as WAV, with when its first audio came and when it ended."""

    wav: bytes
    # Includes setting up the connection, which a call already warmed.
    first_audio_ms: int
    total_ms: int

    @property
    def timing(self) -> str:
        """The latencies as a Server-Timing header says them, which a browser shows."""
        return f"first-audio;dur={self.first_audio_ms}, total;dur={self.total_ms}"


@dataclass(frozen=True, slots=True)
class TimedWord:
    """A word as the voice timed it, its seconds from the start of the audio."""

    text: str
    start_s: float
    end_s: float


@dataclass(frozen=True, slots=True)
class Spoken:
    """A line spoken as 16-bit PCM, and the words the voice timed; none from a voice that times none."""

    pcm: bytes
    rate: int
    channels: int
    words: tuple[TimedWord, ...]


# The three words are read exactly as the settings endpoint reads them, so what plays is what saves.
async def sample_for(session: AsyncSession, vault: Vault, scope: Scope, asked: Asked) -> Sample:
    """The line said by that vendor's voice, on the key and with the options a call of the org would speak with."""
    catalog = await get_catalog(session)
    language = primary_language(asked.language)
    line = asked.text or catalog.lines.get(language or "", A_LINE)
    if len(line) > LONGEST_SAMPLE:
        raise ValidationError(f"a sample says a sentence: {len(line)} characters, and the ceiling is {LONGEST_SAMPLE}")
    # `tts` names a vendor, never a model: a word that is no vendor is refused as one, not tried as a model.
    vendor = catalog.defaults[Stage.tts].vendor if not asked.tts else plugins.vendor_doing(asked.tts, Stage.tts)
    voice = Voice(vendor=vendor, model=asked.model or None, voice_id=asked.voice)
    running = stage_on_its_key(Stage.tts, voice, catalog, await keys_of(session, vault, scope))
    return await sample(dataclasses.replace(running, voice=voice.voice_id, language=language), line)


async def sample(running: Running, line: str) -> Sample:
    """The line spoken by the stage's voice, built as a call builds it; its refusal in the vendor's words."""
    with refusing(running.vendor, THE_VOICE):
        return await say(running, line, hear_sample)


# Only a streaming voice times its words (Cartesia's over its websocket, not its HTTP endpoint),
# each from the start of the whole audio, across the sentences of the line (measured 2026-10-25).
async def speak(running: Running, line: str) -> Spoken:
    """The line spoken by the stage's voice as a call speaks it, and each word's time where the voice gives them."""
    with refusing(running.vendor, THE_VOICE):
        return await say(running, line, _time_words)


type Taken[T] = Callable[[AsyncIterator[SynthesizedAudio]], Awaitable[T]]


# One way to say a line, two ways to take the audio. livekit's errors pass through: who asked for the
# line says the vendor's no, in the words of what it was asking (a sample, a setting tried).
async def say[T](running: Running, line: str, taken: Taken[T]) -> T:
    """The line said by the stage's voice outside a call, its audio handed to `taken` as it comes."""
    async with voice_outside_a_call(running) as speech:
        if speech.capabilities.streaming:
            async with speech.stream() as stream:
                stream.push_text(line)
                stream.end_input()
                return await taken(stream)
        async with speech.synthesize(line) as chunks:
            return await taken(chunks)


# livekit refuses a synthesis that pushed no audio, so what reaches here has some.
async def hear_sample(audio: AsyncIterator[SynthesizedAudio]) -> Sample:
    """The audio as it comes, kept as WAV, with when its first chunk came and when it ended."""
    started = time.perf_counter()
    first: float | None = None
    pcm = bytearray()
    rate, channels = 0, 0
    async for chunk in audio:
        first = first or time.perf_counter()
        pcm += bytes(chunk.frame.data)
        rate, channels = chunk.frame.sample_rate, chunk.frame.num_channels
    ended = time.perf_counter()
    return Sample(
        wav=_wav_of(bytes(pcm), rate, channels),
        first_audio_ms=_ms_between(started, first or ended),
        total_ms=_ms_between(started, ended),
    )


async def _time_words(audio: AsyncIterator[SynthesizedAudio]) -> Spoken:
    pcm = bytearray()
    rate, channels = 0, 0
    words: list[TimedWord] = []
    async for chunk in audio:
        pcm += bytes(chunk.frame.data)
        rate, channels = chunk.frame.sample_rate, chunk.frame.num_channels
        timed: object = chunk.frame.userdata.get(USERDATA_TIMED_TRANSCRIPT)
        for piece in timed if a_list(timed) else []:
            word = _read_timed(piece)
            if word is not None:
                words.append(word)
    return Spoken(pcm=bytes(pcm), rate=rate, channels=channels, words=tuple(words))


def _read_timed(piece: object) -> TimedWord | None:
    if not isinstance(piece, TimedString):
        return None
    start, end = piece.start_time, piece.end_time
    if not isinstance(start, int | float) or not isinstance(end, int | float):
        return None
    return TimedWord(text=str(piece).strip(), start_s=float(start), end_s=float(end))


def _wav_of(pcm: bytes, rate: int, channels: int) -> bytes:
    out = io.BytesIO()
    with wave.open(out, "wb") as file:
        file.setnchannels(channels)
        file.setsampwidth(SAMPLE_WIDTH)
        file.setframerate(rate)
        file.writeframes(pcm)
    return out.getvalue()


def _ms_between(started: float, at: float) -> int:
    return round((at - started) * 1000)
