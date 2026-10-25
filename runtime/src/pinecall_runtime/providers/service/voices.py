"""The voice picker: the voices a vendor lists, and a line spoken by one of them outside a call, timed word by word."""

import dataclasses
import inspect
import io
import time
import wave
from collections.abc import AsyncIterator, Awaitable, Callable, Mapping, Sequence
from dataclasses import dataclass
from typing import Any

from livekit.agents import APIConnectionError, APIError, APIStatusError, APITimeoutError
from livekit.agents.tts import SynthesizedAudio
from livekit.agents.types import USERDATA_TIMED_TRANSCRIPT, TimedString
from livekit.agents.utils import http_context

from pinecall_runtime.exceptions import NotFound, UpstreamError, ValidationError
from pinecall_runtime.kit.text import a_list, a_mapping
from pinecall_runtime.providers.schemas import Catalog
from pinecall_runtime.providers.service.plugins import Running, words_of
from pinecall_runtime.providers.service.stages import tts_of

SAMPLE_WIDTH = 2  # 16-bit PCM, as every plugin emits it

# Samples cost vendor time and write no usage row, so a key gets this many a minute.
SAMPLES_A_MINUTE = 30
NOT_LISTED = "it has no voice called {voice}: `pinecall voices list --tts {vendor}` lists the ones it has"
# Plugins name a voice's id and name differently; the first a row carries is it.
THE_ID = ("id", "voice_id", "voice")
THE_NAME = ("name", "voice_name", "display_name")


class NotListed(NotFound):
    """The vendor lists no voices here."""

    def __init__(self, vendor: str) -> None:
        super().__init__(f"{vendor} lists no voices here: its voice is the vendor's own id, set as it is")


@dataclass(frozen=True, slots=True)
class ListedVoice:
    """A voice as the picker shows it: its id, its name, and the vendor's row whole."""

    id: str
    name: str
    detail: Mapping[str, Any]


@dataclass(frozen=True, slots=True)
class Sample:
    """A line spoken as WAV, with when its first audio came and when it ended."""

    wav: bytes
    # Includes setting up the connection, which a call already warmed.
    first_audio_ms: int
    total_ms: int


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


async def listed_by_vendor(running: Running) -> list[ListedVoice]:
    """The voices a vendor lists on the stage's key, where its plugin lists any; NotFound if not."""
    async with http_context.open():
        speech = tts_of(running)
        listing = getattr(speech, "list_voices", None)
        if not callable(listing):
            raise NotListed(running.vendor)
        try:
            answer = listing()
            if not inspect.isawaitable(answer):
                raise NotListed(running.vendor)
            answered: object = await answer
        except APIError as refused:
            raise _refused(running.vendor, "did not list its voices", refused) from refused
        finally:
            await speech.aclose()
    return [voice for row in _rows(answered) if (voice := _listed(row)) is not None]


# A vendor that speaks a voice it does not have in its default one (Google's Gemini voices) answers
# the trial, so the lists decide: one the providers row lists is kept; else the vendor's own list on
# the stage's key, cloned voices among them; a vendor that lists none (or an empty list) has the
# row's alone, and with none there either it is left to the trial.
async def check_listed(running: Running, catalog: Catalog) -> None:
    """Refuse a voice neither the providers row nor the vendor lists; ValidationError naming the list."""
    if running.voice is None:
        return
    in_the_row = listed_in_catalog(catalog, running.vendor, None)
    if _names(in_the_row, running.voice):
        return
    try:
        listed = await listed_by_vendor(running)
    except NotListed:
        listed = []
    known = listed or in_the_row
    if known and not _names(known, running.voice):
        raise ValidationError(NOT_LISTED.format(vendor=running.vendor, voice=running.voice))


def _names(listed: Sequence[ListedVoice], voice: str) -> bool:
    return any(voice in (each.id, each.name) for each in listed)


def listed_in_catalog(catalog: Catalog, vendor: str, language: str | None) -> list[ListedVoice]:
    """The voices the providers row lists for a vendor, in that language or in every one."""
    found: list[ListedVoice] = []
    for key, listed in catalog.listed.items():
        named, _, spoken = key.partition("/")
        if named != vendor or (language is not None and spoken != language):
            continue
        for voice in listed:
            found.append(ListedVoice(id=voice.id, name=voice.name, detail={**voice.model_dump(), "language": spoken}))
    return found


# A status at or past it is the vendor failing, not the voice asked for.
THE_VENDORS_OWN = 500


# A vendor that turns the voice down (a typo in its id, a model it does not run, silence for a
# voice it has not) is the request's fault, refused as the settings refuse it; a vendor that does
# not answer, or fails on its side, is the vendor's.
async def sample(running: Running, line: str) -> Sample:
    """The line spoken by the stage's voice, built as a call builds it; its refusal in the vendor's words."""
    return await _voiced(running, line, _heard)


# Only a streaming voice times its words (Cartesia's over its websocket, not its HTTP endpoint),
# each from the start of the whole audio, across the sentences of the line (measured 2026-10-25).
async def speak(running: Running, line: str) -> Spoken:
    """The line spoken by the stage's voice as a call speaks it, and each word's time where the voice gives them."""
    return await _voiced(running, line, _spoken)


type Taken[T] = Callable[[AsyncIterator[SynthesizedAudio]], Awaitable[T]]


async def _voiced[T](running: Running, line: str, taken: Taken[T]) -> T:
    async with http_context.open():
        speech = tts_of(running)
        try:
            if speech.capabilities.streaming:
                async with speech.stream() as stream:
                    stream.push_text(line)
                    stream.end_input()
                    return await taken(stream)
            async with speech.synthesize(line) as chunks:
                return await taken(chunks)
        except (APIConnectionError, APITimeoutError) as silent:
            raise _refused(running.vendor, "did not answer", silent) from silent
        except APIError as refused:
            if isinstance(refused, APIStatusError) and refused.status_code >= THE_VENDORS_OWN:
                raise _refused(running.vendor, "failed on its side", refused) from refused
            raise ValidationError(f"{running.vendor} refused the voice: {words_of(refused)}") from refused
        finally:
            await speech.aclose()


# The vendor's own words, and its status where it answered with one.
def _refused(vendor: str, what: str, error: APIError) -> UpstreamError:
    status = f" ({error.status_code})" if isinstance(error, APIStatusError) else ""
    return UpstreamError(f"{vendor} {what}{status}: {words_of(error)}")


# A listing is a list of rows, each a dataclass or a mapping; one that is a mapping of names
# is read as rows named by its keys.
def _rows(answered: object) -> list[dict[str, Any]]:
    if a_mapping(answered):
        return [{"id": key, "name": key} for key in answered]
    return [_row(item) for item in answered] if a_list(answered) else []


def _row(item: object) -> dict[str, Any]:
    if dataclasses.is_dataclass(item) and not isinstance(item, type):
        return _json(dataclasses.asdict(item))
    return _json(item) if a_mapping(item) else {}


def _json(fields: Mapping[str, object]) -> dict[str, Any]:
    return {name: _value(value) for name, value in fields.items()}


def _value(value: object) -> Any:
    if isinstance(value, str | int | float | bool) or value is None:
        return value
    if a_mapping(value):
        return _json(value)
    if a_list(value):
        return [_value(item) for item in value]
    return str(value)


# A plugin that lists its voices with no language cannot be narrowed by one: every voice would pass
# the filter, and a person asking for Spanish would read 150 voices in every tongue.
NO_LANGUAGE_LISTED = (
    "{vendor} lists its voices with no language, so --language {language} cannot narrow them: drop it and pick by name"
)


def check_narrowable(vendor: str, listed: Sequence[ListedVoice], language: str | None) -> None:
    """Refuse a language on a listing that carries none; nothing on a listing that does, or on no language."""
    if language is not None and listed and not any(item.detail.get("language") for item in listed):
        raise ValidationError(NO_LANGUAGE_LISTED.format(vendor=vendor, language=language))


def _listed(row: Mapping[str, Any]) -> ListedVoice | None:
    named = next((str(row[name]) for name in THE_ID if row.get(name)), None)
    if named is None:
        return None
    shown = next((str(row[name]) for name in THE_NAME if row.get(name)), named)
    return ListedVoice(id=named, name=shown, detail=row)


# livekit refuses a synthesis that pushed no audio, so what reaches here has some.
async def _heard(audio: AsyncIterator[SynthesizedAudio]) -> Sample:
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
        wav=_wav(bytes(pcm), rate, channels), first_audio_ms=_ms(started, first or ended), total_ms=_ms(started, ended)
    )


async def _spoken(audio: AsyncIterator[SynthesizedAudio]) -> Spoken:
    pcm = bytearray()
    rate, channels = 0, 0
    words: list[TimedWord] = []
    async for chunk in audio:
        pcm += bytes(chunk.frame.data)
        rate, channels = chunk.frame.sample_rate, chunk.frame.num_channels
        timed: object = chunk.frame.userdata.get(USERDATA_TIMED_TRANSCRIPT)
        for piece in timed if a_list(timed) else []:
            word = _timed(piece)
            if word is not None:
                words.append(word)
    return Spoken(pcm=bytes(pcm), rate=rate, channels=channels, words=tuple(words))


def _timed(piece: object) -> TimedWord | None:
    if not isinstance(piece, TimedString):
        return None
    start, end = piece.start_time, piece.end_time
    if not isinstance(start, int | float) or not isinstance(end, int | float):
        return None
    return TimedWord(text=str(piece).strip(), start_s=float(start), end_s=float(end))


def _wav(pcm: bytes, rate: int, channels: int) -> bytes:
    out = io.BytesIO()
    with wave.open(out, "wb") as file:
        file.setnchannels(channels)
        file.setsampwidth(SAMPLE_WIDTH)
        file.setframerate(rate)
        file.writeframes(pcm)
    return out.getvalue()


def _ms(started: float, at: float) -> int:
    return round((at - started) * 1000)
