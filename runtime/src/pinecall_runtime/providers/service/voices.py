"""The voice picker: the voices a vendor lists, and a line spoken by one of them outside a call."""

import dataclasses
import inspect
import io
import time
import wave
from collections.abc import AsyncIterator, Mapping
from dataclasses import dataclass
from typing import Any

from livekit.agents import APIConnectionError, APIError, APIStatusError, APITimeoutError
from livekit.agents.tts import SynthesizedAudio
from livekit.agents.utils import http_context

from pinecall_runtime.exceptions import NotFound, UpstreamError, ValidationError
from pinecall_runtime.kit.text import a_list, a_mapping
from pinecall_runtime.providers.schemas import Catalog
from pinecall_runtime.providers.service.plugins import Running
from pinecall_runtime.providers.service.stages import tts_of

SAMPLE_WIDTH = 2  # 16-bit PCM, as every plugin emits it

# Samples cost vendor time and write no usage row, so a key gets this many a minute.
SAMPLES_A_MINUTE = 30
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
    async with http_context.open():
        speech = tts_of(running)
        try:
            if speech.capabilities.streaming:
                async with speech.stream() as stream:
                    stream.push_text(line)
                    stream.end_input()
                    return await _heard(stream)
            async with speech.synthesize(line) as chunks:
                return await _heard(chunks)
        except (APIConnectionError, APITimeoutError) as silent:
            raise _refused(running.vendor, "did not answer", silent) from silent
        except APIError as refused:
            if isinstance(refused, APIStatusError) and refused.status_code >= THE_VENDORS_OWN:
                raise _refused(running.vendor, "failed on its side", refused) from refused
            raise ValidationError(f"{running.vendor} refused the voice: {refused.message}") from refused
        finally:
            await speech.aclose()


# The vendor's own words, and its status where it answered with one.
def _refused(vendor: str, what: str, error: APIError) -> UpstreamError:
    status = f" ({error.status_code})" if isinstance(error, APIStatusError) else ""
    return UpstreamError(f"{vendor} {what}{status}: {error.message}")


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
