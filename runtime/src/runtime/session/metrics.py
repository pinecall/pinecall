"""livekit's metrics and usage as the wire writes them: each block, each model's usage, the end of an utterance."""

import time
from collections.abc import Mapping
from typing import Any, Protocol

from livekit.agents import metrics
from livekit.agents.metrics.base import AvatarMetrics

from runtime.wire import metrics as measured
from runtime.wire.base import WireModel

# Each block is read by the wire's fields, under livekit's own names.
BLOCKS: tuple[tuple[type[metrics.AgentMetrics], str, type[WireModel]], ...] = (
    (metrics.LLMMetrics, "metrics.llm", measured.LLMMetrics),
    (metrics.STTMetrics, "metrics.stt", measured.STTMetrics),
    (metrics.TTSMetrics, "metrics.tts", measured.TTSMetrics),
    (metrics.VADMetrics, "metrics.vad", measured.VADMetrics),
    (metrics.EOUMetrics, "metrics.eou", measured.EOUMetrics),
    (metrics.InterruptionMetrics, "metrics.interruption", measured.InterruptionMetrics),
    (metrics.RealtimeModelMetrics, "metrics.realtime", measured.RealtimeModelMetrics),
    (metrics.EOTInferenceMetrics, "metrics.eot", measured.EOTInferenceMetrics),
    (AvatarMetrics, "metrics.avatar", measured.AvatarMetrics),
)


class Dumped(Protocol):
    """A row of livekit's, as far as it is read here: its fields by name."""

    def model_dump(self) -> dict[str, Any]:
        """The row's fields."""
        ...


def usage_of(used: metrics.ModelUsage) -> measured.ModelUsage:
    """The usage of one model livekit measured, as the wire writes it."""
    match used:
        case metrics.LLMModelUsage():
            return _read_as(measured.LLMModelUsage, used)
        case metrics.TTSModelUsage():
            return _read_as(measured.TTSModelUsage, used)
        case metrics.STTModelUsage():
            return _read_as(measured.STTModelUsage, used)
        case metrics.InterruptionModelUsage():
            return _read_as(measured.InterruptionModelUsage, used)
        case _:
            return _read_as(measured.EOTModelUsage, used)


def block_of(block: metrics.AgentMetrics) -> tuple[str, WireModel] | None:
    """The metrics livekit measured for one step, as the entry type and model the log keeps."""
    for livekits, kind, ours in BLOCKS:
        if isinstance(block, livekits):
            return kind, _read_as(ours, block)
    return None


# livekit emits the end-of-utterance block on the session only, so it is built again from the
# user turn's report, as livekit builds it.
def end_of_utterance(report: Mapping[str, object], speech: str) -> measured.EOUMetrics | None:
    """The end-of-turn metrics livekit reports, as the wire's; None when a field is missing."""
    delays = ("end_of_turn_delay", "transcription_delay", "on_user_turn_completed_delay")
    if not any(key in report for key in delays):
        return None
    # Said, or dump() drops the default and the SDKs refuse the entry.
    return measured.EOUMetrics.model_validate(
        {
            "type": "eou_metrics",
            "timestamp": time.time(),
            "end_of_utterance_delay": report.get("end_of_turn_delay", 0.0),
            "transcription_delay": report.get("transcription_delay", 0.0),
            "on_user_turn_completed_delay": report.get("on_user_turn_completed_delay", 0.0),
            "speech_id": speech,
        }
    )


# livekit's rows carry the wire's names, and livekit adds fields the wire does not know
# (`input_audio_tokens` on the ears' usage in 1.8.3). The wire refuses an unknown key, and a
# listener's exception is swallowed by livekit's emitter, so the call would lose its usage in
# silence: each row is read by the fields its wire model declares.
def _read_as[T: WireModel](model: type[T], livekits: Dumped) -> T:
    dumped = livekits.model_dump()
    return model.model_validate({name: dumped[name] for name in model.model_fields if name in dumped})
