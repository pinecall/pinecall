"""Tests for ears that commit only when told, told by the session's VAD at each end of speech."""

import asyncio
import time
from collections.abc import Callable
from typing import Never, override

import numpy as np
from livekit import rtc
from livekit.agents import stt, vad
from livekit.agents.language import LanguageCode
from livekit.agents.types import DEFAULT_API_CONNECT_OPTIONS, NOT_GIVEN, APIConnectOptions, NotGivenOr
from livekit.agents.utils import AudioBuffer

from pinecall_runtime.providers.service.committing import CommittedByVAD
from pinecall_runtime.providers.service.plugins import Running
from pinecall_runtime.providers.service.stages import build_ears

RATE = 16000


class _Silence(vad.VAD):
    """A detector that hears the end of speech in a frame of zeros."""

    def __init__(self) -> None:
        super().__init__(capabilities=vad.VADCapabilities(update_interval=0.03))

    @override
    def stream(self) -> vad.VADStream:
        return _SilenceStream(self)


class _SilenceStream(vad.VADStream):
    @override
    async def _main_task(self) -> None:
        async for given in self._input_ch:
            if isinstance(given, rtc.AudioFrame) and not any(given.data):
                self._event_ch.send_nowait(
                    vad.VADEvent(
                        type=vad.VADEventType.END_OF_SPEECH,
                        samples_index=0,
                        timestamp=time.time(),
                        speech_duration=0.5,
                        silence_duration=0.3,
                    )
                )


class _Told(stt.STT[Never]):
    """Ears that write a line only when flushed, numbered."""

    def __init__(self) -> None:
        super().__init__(capabilities=stt.STTCapabilities(streaming=True, interim_results=True))
        self.flushed = 0

    @override
    def stream(
        self,
        *,
        language: NotGivenOr[str] = NOT_GIVEN,
        conn_options: APIConnectOptions = DEFAULT_API_CONNECT_OPTIONS,
    ) -> stt.RecognizeStream:
        return _ToldStream(self, conn_options)

    @override
    async def _recognize_impl(
        self,
        buffer: AudioBuffer,
        *,
        language: NotGivenOr[str] = NOT_GIVEN,
        conn_options: APIConnectOptions,
    ) -> stt.SpeechEvent:
        raise NotImplementedError


class _ToldStream(stt.RecognizeStream):
    def __init__(self, ears: _Told, conn_options: APIConnectOptions) -> None:
        super().__init__(stt=ears, conn_options=conn_options)  # pyright: ignore[reportUnknownMemberType]
        self._told = ears

    @override
    async def _run(self) -> None:
        async for given in self._input_ch:
            if isinstance(given, self._FlushSentinel):
                self._told.flushed += 1
                said = stt.SpeechData(language=LanguageCode("es"), text=f"told {self._told.flushed}")
                self._event_ch.send_nowait(
                    stt.SpeechEvent(type=stt.SpeechEventType.FINAL_TRANSCRIPT, alternatives=[said])
                )


def _frame(speech: bool) -> rtc.AudioFrame:
    samples = np.full(480, 1000 if speech else 0, dtype=np.int16)
    return rtc.AudioFrame(data=bytearray(samples.tobytes()), sample_rate=RATE, num_channels=1, samples_per_channel=480)


async def _until(true: Callable[[], bool]) -> None:
    deadline = time.monotonic() + 2
    while not true():
        assert time.monotonic() < deadline, "it never came"
        await asyncio.sleep(0.01)


async def test_the_vad_hearing_the_end_of_speech_tells_the_ears_to_commit_and_their_words_come_through() -> None:
    told = _Told()
    ears = CommittedByVAD(told, _Silence())
    stream = ears.stream()
    stream.push_frame(_frame(speech=True))
    stream.push_frame(_frame(speech=True))
    await asyncio.sleep(0.05)
    assert told.flushed == 0, "speech alone tells the ears nothing"
    stream.push_frame(_frame(speech=False))
    await _until(lambda: told.flushed == 1)
    # The end of the input flushes once more, as livekit's own streams do.
    stream.end_input()
    heard = [event.alternatives[0].text async for event in stream]
    assert heard == ["told 1", "told 2"]
    await stream.aclose()
    await ears.aclose()


async def test_the_ears_told_to_commit_keep_their_name_their_model_and_their_capabilities() -> None:
    told = _Told()
    ears = CommittedByVAD(told, _Silence())
    assert (ears.label, ears.model, ears.provider) == (told.label, told.model, told.provider)
    assert ears.capabilities == told.capabilities
    measured: list[object] = []
    ears.on("metrics_collected", measured.append)  # pyright: ignore[reportUnknownMemberType]
    told.emit("metrics_collected", "a measure")
    assert measured == ["a measure"]
    await ears.aclose()
    told.emit("metrics_collected", "after")
    assert measured == ["a measure"], "closed, it relays nothing"


def test_a_stage_that_commits_when_told_is_built_around_the_sessions_vad_and_the_others_are_not() -> None:
    hearing = _Silence()
    told = build_ears(Running("acme", "a-key", commits_when_told=True), None, (), hearing)
    assert isinstance(told, CommittedByVAD)
    assert type(told.ears).__name__ == "AcmeSTT"
    own = build_ears(Running("acme", "a-key"), None, (), hearing)
    assert type(own).__name__ == "AcmeSTT"
    assert type(build_ears(Running("acme", "a-key", commits_when_told=True), None)).__name__ == "AcmeSTT", (
        "with no VAD lent, the ears are left as they are"
    )
