"""What livekit tells a session about its call, written as entries: turns, states, usage, metrics, failures."""

import asyncio
import time
from collections.abc import Callable, Iterable, Mapping

from livekit.agents import (
    AgentStateChangedEvent,
    APIStatusError,
    CloseEvent,
    CloseReason,
    ConversationItemAddedEvent,
    SessionUsageUpdatedEvent,
    UserInputTranscribedEvent,
    UserStateChangedEvent,
    llm,
    metrics,
    stt,
    tts,
    utils,
)
from livekit.agents import ErrorEvent as ComponentFailed
from livekit.agents.metrics.base import AvatarMetrics
from livekit.agents.types import TimedString
from livekit.agents.voice import AgentSession
from livekit.agents.voice.events import EventTypes
from pydantic import BaseModel

from pinecall_runtime.agents.declaration import Modality
from pinecall_runtime.providers import service as providers
from pinecall_runtime.session.call import Call
from pinecall_runtime.session.hold import HoldMusic
from pinecall_runtime.session.lookups import Lookups
from pinecall_runtime.session.writing import Writing
from pinecall_runtime.wire import events as wire
from pinecall_runtime.wire import metrics as measured
from pinecall_runtime.wire.base import WireModel

type Adapter = llm.FallbackAdapter | stt.FallbackAdapter | tts.FallbackAdapter
# What a session built and measures: the model, and on a voice call the ears and the voice.
type Built = providers.Thinking | providers.Ears | providers.Speaking

# Errors of the request itself; 408, 429 and 5xx are transient and livekit retries them.
FOREVER = frozenset({400, 401, 402, 403, 404, 422})
# The WebSocket close for a policy violation: a vendor that refuses a voice or a key sends it,
# and livekit's 4xx check misses it.
POLICY_VIOLATION = 1008
# What the session listens to on livekit's AgentSession.
LISTENED: tuple[EventTypes, ...] = (
    "user_input_transcribed",
    "user_state_changed",
    "agent_state_changed",
    "conversation_item_added",
    "session_usage_updated",
    "error",
    "close",
)
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


class Listener:
    """One call's ear on its AgentSession and its components, writing what they say."""

    def __init__(
        self,
        call: Call,
        live: AgentSession[None],
        lookups: Lookups,
        hold: HoldMusic | None,
        *,
        dead_end: Callable[[], None],
    ) -> None:
        """Listening to nothing yet."""
        self.call = call
        self.live = live
        self.lookups = lookups
        self.hold = hold
        self.dead_end = dead_end
        self.language: str | None = None
        self.usage: list[measured.ModelUsage] = []
        self.closed_for: CloseReason | None = None
        # When the person last said something: what a written call in a room is kept alive by.
        self.last_heard = time.monotonic()
        self.ended_for_good = False
        self.components: tuple[Built, ...] = ()

    def listen(self, components: Iterable[Built]) -> None:
        """Hear the session's events and its components' metrics."""
        for name in LISTENED:
            self.live.on(name, self.heard)  # pyright: ignore[reportUnknownMemberType]
        self.components = tuple(components)
        for component in self.components:
            component.on("metrics_collected", self._measured)  # pyright: ignore[reportUnknownMemberType]

    def stop(self) -> None:
        """Hear nothing more."""
        for name in LISTENED:
            self.live.off(name, self.heard)  # pyright: ignore[reportUnknownMemberType]
        for component in self.components:
            component.off("metrics_collected", self._measured)  # pyright: ignore[reportUnknownMemberType]

    def heard(self, event: object) -> None:
        """One event of the session, written as the entry it is."""
        writing = self.call.writing
        match event:
            case UserInputTranscribedEvent():
                self._transcribed(event)
            case UserStateChangedEvent():
                writing.write("user.state", wire.UserStateChanged(state=event.new_state))
            case AgentStateChangedEvent():
                if self.call.agent_speaking and event.new_state != "speaking":
                    self.call.agent_words.stopped()
                self.call.agent_speaking = event.new_state == "speaking"
                if self.hold is not None:
                    self.hold.floor(speaking=self.call.agent_speaking)
                writing.write("agent.state", wire.AgentStateChanged(state=event.new_state))
            case ConversationItemAddedEvent():
                self._turn(event.item)
            case SessionUsageUpdatedEvent():
                self.usage = [usage_of(used) for used in event.usage.model_usage]
            case ComponentFailed():
                self._failed(event)
            case CloseEvent():
                self.closed_for = event.reason
            case _:
                return

    # Every transcript starts the lookups, so recall and search run while the caller still talks or
    # while the end of the turn is weighed. Ears that write no interims (Whisper) give the final
    # alone, some 300 ms before the turn ends: left to the turn's end, the lookup spent its budget
    # waiting on the embedder (gpu.pinecall.io, 2026-10-18).
    def _transcribed(self, event: UserInputTranscribedEvent) -> None:
        self.language = event.language or self.language
        text = wire.UserTranscript(text=event.transcript, final=event.is_final, language=event.language)
        self.call.writing.write("user.transcript", text)
        self.lookups.heard_so_far(event.transcript)

    # Metrics are whole by the time an item is added, so the turns are written here.
    def _turn(self, item: object) -> None:
        if not isinstance(item, llm.ChatMessage) or item.role not in {"user", "assistant"}:
            return
        speech = self.live.current_speech.id if self.live.current_speech else item.id
        text = item.text_content or ""
        call = self.call
        if item.role == "assistant":
            call.turns += 1
            call.last_said = text or call.last_said
            replied = measured.AgentTurnMetrics.model_validate(call.replied(item.metrics))
            agent = wire.AgentTurnEnded(
                speech_id=speech, item_id=item.id, text=text, interrupted=item.interrupted, metrics=replied
            )
            call.writing.write("turn.agent", agent)
            return
        self.last_heard = time.monotonic()
        call.heard(item.metrics)
        eou = end_of_utterance(item.metrics, speech)
        if eou is not None:
            call.writing.write("metrics.eou", eou)
        user = wire.UserTurnEnded(
            speech_id=speech,
            item_id=item.id,
            text=text,
            language=self.language,
            transcript_confidence=item.transcript_confidence,
            metrics=measured.UserTurnMetrics.model_validate(dict(item.metrics)),
        )
        call.writing.write("turn.user", user)

    # livekit closes only after three unrecoverable errors. A refusal that can never succeed (a
    # bad key, a voice that does not exist) ends the call on the first.
    def _failed(self, event: ComponentFailed) -> None:
        if self.ended_for_good:
            return
        said = str(event.error)
        wrapped = getattr(event.error, "error", None)
        if not (isinstance(wrapped, APIStatusError) and fails_for_good(wrapped)):
            recoverable = bool(getattr(event.error, "recoverable", False))
            self.call.writing.write(
                "error", wire.ErrorEvent(code="component_failed", message=said, recoverable=recoverable)
            )
            return
        self.ended_for_good = True
        self.call.writing.write("error", wire.ErrorEvent(code="component_dead_end", message=said, recoverable=False))
        self.dead_end()

    # Deferred a tick: livekit stamps the speech id on the same object from a listener of its
    # own, and the order of listeners is not defined. Streaming ears report usage at their own
    # cadence; those ticks ride the stream and the total reaches the summary.
    def _measured(self, block: metrics.AgentMetrics) -> None:
        asyncio.get_running_loop().call_soon(self._write_block, block)

    def _write_block(self, block: metrics.AgentMetrics) -> None:
        written = block_of(block)
        if written is None:
            return
        kind, model = written
        tick = isinstance(block, metrics.STTMetrics) and block.streamed and not block.acquire_time
        self.call.writing.write(kind, model, ephemeral=True if tick else None)


def transcript_of(live: AgentSession[None], delta: str | TimedString) -> wire.AgentTranscript:
    """What the agent said, as the wire's transcript entry, with the word timings livekit gave."""
    speech = live.current_speech.id if live.current_speech else ""
    timed: dict[str, float] = {}
    if isinstance(delta, TimedString):
        if utils.is_given(delta.start_time):
            timed["start"] = delta.start_time
        if utils.is_given(delta.end_time):
            timed["end"] = delta.end_time
    return wire.AgentTranscript(speech_id=speech, text=str(delta), final=False, **timed)


def fails_for_good(error: APIStatusError) -> bool:
    """Whether a vendor's HTTP error will fail the same way every time it is retried."""
    return error.status_code == POLICY_VIOLATION or error.status_code in FOREVER


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


# livekit's adapter says when a vendor goes down or comes back (`<stage>_availability_changed`,
# the vendor under the stage's own name), and names the next to serve. Its emitter is untyped:
# it is read as an object.
def write_switches(writing: Writing, built: Iterable[object]) -> None:
    """Write vendor.switched each time a stage's fallback adapter loses or regains a vendor."""
    for component in built:
        match component:
            case llm.FallbackAdapter():
                stage: Modality = "llm"
            case stt.FallbackAdapter():
                stage = "stt"
            case tts.FallbackAdapter():
                stage = "tts"
            case _:
                continue
        listen: object = getattr(component, "on", None)
        if callable(listen):
            listen(f"{stage}_availability_changed", _switch(writing, stage, component))


def switch_of(stage: Modality, event: object, adapter: Adapter) -> wire.VendorSwitched | None:
    """The entry for one vendor of a stage lost or back, and the one serving from now."""
    changed: object = getattr(event, stage, None)
    available: object = getattr(event, "available", None)
    if not isinstance(changed, (llm.LLM, stt.STT, tts.TTS)) or not isinstance(available, bool):
        return None
    return wire.VendorSwitched(
        stage=stage,
        vendor=changed.provider,
        model=changed.model,
        available=available,
        serving=adapter.provider,
        serving_model=adapter.model,
    )


# livekit's rows carry the wire's names, and livekit adds fields the wire does not know
# (`input_audio_tokens` on the ears' usage in 1.8.3). The wire refuses an unknown key, and a
# listener's exception is swallowed by livekit's emitter, so the call would lose its usage in
# silence: each row is read by the fields its wire model declares.
def _read_as[T: WireModel](model: type[T], livekits: BaseModel) -> T:
    dumped = livekits.model_dump()
    return model.model_validate({name: dumped[name] for name in model.model_fields if name in dumped})


def _switch(writing: Writing, stage: Modality, adapter: Adapter) -> Callable[[object], None]:
    def written(event: object) -> None:
        switched = switch_of(stage, event, adapter)
        if switched is not None:
            writing.write("vendor.switched", switched)

    return written
