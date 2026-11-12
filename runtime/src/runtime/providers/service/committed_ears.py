"""Ears that commit a segment only when told, told by the session's own VAD at each end of speech."""

import asyncio
from collections.abc import AsyncIterable
from typing import Any, Never, override

from livekit.agents import stt, utils, vad
from livekit.agents.types import DEFAULT_API_CONNECT_OPTIONS, NOT_GIVEN, APIConnectOptions, NotGivenOr
from livekit.agents.utils import AudioBuffer
from livekit.agents.voice.events import ConversationItemAddedEvent

# Some ears close no segment on their own: Scribe realtime with no `server_vad` among its options
# sends the commit only when its stream is flushed, and livekit never flushes the ears at the end
# of speech, so a call on it heard nothing and said nothing for its whole length (2026-11-05). The
# row says so (`commits_when_told`), and the session's VAD tells them: the same Silero that opens
# the turn detector, so the commit and the turn are read off the same silence.


class CommittedByVAD(stt.STT[Never]):
    """The ears told to commit at each end of speech the VAD hears; everything else is theirs."""

    def __init__(self, ears: stt.STT[Never], hearing: vad.VAD) -> None:
        super().__init__(capabilities=ears.capabilities)
        self.ears = ears
        self._hearing = hearing
        self._label = ears.label
        ears.on("metrics_collected", self._report_metrics)  # pyright: ignore[reportUnknownMemberType]

    @property
    @override
    def model(self) -> str:
        return self.ears.model

    @property
    @override
    def provider(self) -> str:
        return self.ears.provider

    # livekit hands the session's keyterms and conversation items to the ears through two hooks with
    # no public name, as its own StreamAdapter forwards them.
    @override
    def _update_session_keyterms(self, keyterms: list[str]) -> None:
        self.ears._update_session_keyterms(keyterms)

    @override
    def _push_conversation_item(self, ev: ConversationItemAddedEvent) -> None:
        self.ears._push_conversation_item(ev)

    @override
    async def _recognize_impl(
        self,
        buffer: AudioBuffer,
        *,
        language: NotGivenOr[str] = NOT_GIVEN,
        conn_options: APIConnectOptions,
    ) -> stt.SpeechEvent:
        return await self.ears.recognize(buffer=buffer, language=language, conn_options=conn_options)

    @override
    def stream(
        self,
        *,
        language: NotGivenOr[str] = NOT_GIVEN,
        conn_options: APIConnectOptions = DEFAULT_API_CONNECT_OPTIONS,
    ) -> stt.RecognizeStream:
        return _Committed(self, self.ears.stream(language=language, conn_options=conn_options), self._hearing.stream())

    @override
    def prewarm(self) -> None:
        self.ears.prewarm()

    # The ears' own stream meters itself; what it measures is reported as this stage's.
    def _report_metrics(self, *args: Any, **kwargs: Any) -> None:
        self.emit("metrics_collected", *args, **kwargs)

    @override
    async def aclose(self) -> None:
        self.ears.off("metrics_collected", self._report_metrics)  # pyright: ignore[reportUnknownMemberType]
        await self.ears.aclose()


# The ears' stream reconnects on its own and its failure, relayed, ends this one: no retry here, as
# livekit's own StreamAdapter has none, and the error is reported once, by this stream's run.
class _Committed(stt.RecognizeStream):
    def __init__(self, ears: CommittedByVAD, inner: stt.RecognizeStream, hearing: vad.VADStream) -> None:
        super().__init__(stt=ears, conn_options=APIConnectOptions(max_retry=0))  # pyright: ignore[reportUnknownMemberType]
        self._inner = inner
        self._heard = hearing

    @override
    async def _metrics_monitor_task(self, event_aiter: AsyncIterable[stt.SpeechEvent]) -> None:
        async for _ in event_aiter:
            pass

    @override
    async def _run(self) -> None:
        ended = False

        # A flush of this stream reaches the ears with the next frame, or with the end of the input,
        # which flushes once itself: forwarded at once, the end of the input would commit twice.
        async def forward() -> None:
            nonlocal ended
            owed = False
            async for given in self._input_ch:
                if isinstance(given, self._FlushSentinel):
                    owed = True
                    continue
                if owed:
                    self._inner.flush()
                    owed = False
                self._inner.push_frame(given)
                self._heard.push_frame(given)
            ended = True
            self._inner.end_input()
            self._heard.end_input()

        async def commit() -> None:
            async for heard in self._heard:
                if heard.type == vad.VADEventType.END_OF_SPEECH and not ended:
                    self._inner.flush()

        async def relay() -> None:
            async for event in self._inner:
                self._event_ch.send_nowait(event)

        tasks = [
            asyncio.create_task(forward(), name="committed.forward"),
            asyncio.create_task(commit(), name="committed.commit"),
            asyncio.create_task(relay(), name="committed.relay"),
        ]
        try:
            await asyncio.gather(*tasks)
        finally:
            await utils.aio.cancel_and_wait(*tasks)
            await self._inner.aclose()
            await self._heard.aclose()
