"""Who takes the floor: what the model is told of the agent, its word on a call's audio, what the session is told."""

from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import override

import numpy as np
from livekit import rtc
from livekit.agents import vad

from runtime.session.taking_the_floor import (
    CHUNK,
    FLOOR_TAKE,
    NO_MURMUR_LASTS_S,
    NON_SPEECH,
    RATE,
    AgentsClock,
    FloorModel,
    HeardOverTheAgent,
    HeardStream,
    load_floor_model,
    quiet,
)

A_STATE = {"gru_state": (2, 1, 4)}
OUTPUTS = ["intent", "vad", "vap", "gru_state_out"]


class Says:
    """A model that answers one class with all its weight, whatever it hears, and keeps what it was asked."""

    def __init__(self, answer: int) -> None:
        """Every frame is this class."""
        self.answer = answer
        self.asked: list[Mapping[str, np.ndarray]] = []

    def run(self, output_names: Sequence[str] | None, input_feed: Mapping[str, np.ndarray]) -> list[np.ndarray]:
        self.asked.append(input_feed)
        intent = np.zeros((1, 2, 5), dtype=np.float32)
        intent[:, :, self.answer] = 1.0
        carried = input_feed["gru_state"] + 1.0
        return [intent, np.zeros((1, 2), np.float32), np.zeros((1, 2, 8), np.float32), carried]


def frame_of(samples: int, rate: int = RATE) -> rtc.AudioFrame:
    return rtc.AudioFrame(data=bytes(samples * 2), sample_rate=rate, num_channels=1, samples_per_channel=samples)


def an_event(kind: vad.VADEventType, speech_s: float = 0.0, *, speaking: bool = True) -> vad.VADEvent:
    return vad.VADEvent(
        type=kind,
        samples_index=0,
        timestamp=1.0,
        speech_duration=speech_s,
        silence_duration=0.0,
        speaking=speaking,
        raw_accumulated_speech=speech_s,
    )


class Finds(vad.VAD):
    """A detector that finds nothing by itself: its events are handed to the stream by the test."""

    def __init__(self) -> None:
        """One that updates as livekit's own does."""
        super().__init__(capabilities=vad.VADCapabilities(update_interval=0.032))

    @override
    def stream(self) -> vad.VADStream:
        return Silent(self)


class Silent(vad.VADStream):
    """A stream that takes its frames and says nothing."""

    @override
    async def _main_task(self) -> None:
        async for _ in self._input_ch:
            pass


def test_the_model_is_told_how_long_since_the_agent_began_and_stopped() -> None:
    """Before it has spoken every count is at its ceiling; speaking, the onset starts at nothing; stopped, the stop."""
    clock = AgentsClock()
    assert clock.tick(False).tolist()[:4] == [0.0, 1.0, 1.0, 1.0]
    began = clock.tick(True)
    # It had been silent 20 ms, not a pause: the onset is new, the last pause still long ago.
    assert (began[0], began[1], began[2]) == (1.0, 0.0, 1.0)
    for _ in range(50):
        clock.tick(True)
    assert abs(clock.tick(True)[1] - 51 * 0.02 / 5) < 1e-6
    stopped = clock.tick(False)
    assert (stopped[0], stopped[3]) == (0.0, 0.0)
    # After a pause of 200 ms or more, speaking again is counted from the pause too.
    for _ in range(12):
        clock.tick(False)
    again = clock.tick(True)
    assert (again[1], again[2]) == (0.0, 0.0)


def test_the_floor_is_taken_once_the_model_has_said_so_for_a_tenth_of_a_second() -> None:
    """Two chunks of 40 ms are four frames: not yet. The third makes five, and the floor is taken."""
    overlap = FloorModel(Says(FLOOR_TAKE), A_STATE, OUTPUTS).open_stream()
    overlap.hear(frame_of(CHUNK * 2), agent_speaks=True)
    assert not overlap.taken
    overlap.hear(frame_of(CHUNK), agent_speaks=True)
    assert overlap.taken
    overlap.forget()
    assert not overlap.taken


def test_agreement_is_never_a_floor_take_and_the_models_state_is_carried() -> None:
    """A model that hears no speech calls nothing; what it carried from one chunk is what it is handed at the next."""
    says = Says(NON_SPEECH)
    overlap = FloorModel(says, A_STATE, OUTPUTS).open_stream()
    overlap.hear(frame_of(CHUNK * 4), agent_speaks=True)
    assert not overlap.taken
    assert [float(asked["gru_state"].max()) for asked in says.asked] == [0.0, 1.0, 2.0, 3.0]
    # The agent's state is two frames a chunk, and the chunk is 40 ms at the model's rate with a room's noise under it.
    assert says.asked[0]["bot_state"].shape == (1, 2, 8) and says.asked[0]["chunk"].shape == (1, CHUNK)
    assert 0 < float(np.abs(says.asked[0]["chunk"]).max()) < 0.001


def test_a_calls_frames_at_another_rate_are_heard_at_the_models() -> None:
    """A session hands 50 ms of 24 kHz: two frames of it are 100 ms, two whole chunks of the model's."""
    says = Says(FLOOR_TAKE)
    overlap = FloorModel(says, A_STATE, OUTPUTS).open_stream()
    for _ in range(4):
        overlap.hear(frame_of(1200, rate=24_000), agent_speaks=True)
    assert 3 <= len(says.asked) <= 5


async def test_speech_over_the_agent_is_told_only_once_it_is_a_floor_take() -> None:
    """Held while the model calls it agreement, told from its start the moment it calls the floor taken."""
    speaks = [True]
    says = Says(NON_SPEECH)
    heard = HeardOverTheAgent(Finds(), FloorModel(says, A_STATE, OUTPUTS), lambda: speaks[0])
    stream = heard.stream()
    assert isinstance(stream, HeardStream)
    assert stream.tell(an_event(vad.VADEventType.START_OF_SPEECH, 0.25)) == []
    told = stream.tell(an_event(vad.VADEventType.INFERENCE_DONE, 0.3))
    assert [(one.type, one.speaking, one.speech_duration) for one in told] == [
        (vad.VADEventType.INFERENCE_DONE, False, 0.0)
    ]
    # The model changes its mind: the start the session was not told comes first, as long as the speech is now.
    says.answer = FLOOR_TAKE
    stream.overlap.hear(frame_of(CHUNK * 3), agent_speaks=True)
    told = stream.tell(an_event(vad.VADEventType.INFERENCE_DONE, 0.45))
    assert [(one.type, one.speech_duration) for one in told] == [
        (vad.VADEventType.START_OF_SPEECH, 0.45),
        (vad.VADEventType.INFERENCE_DONE, 0.45),
    ]
    # From then on the detector's events pass as they come.
    after = an_event(vad.VADEventType.END_OF_SPEECH, 1.0, speaking=False)
    assert stream.tell(after) == [after]
    await stream.aclose()


async def test_a_murmur_that_ends_was_never_speech_to_the_session() -> None:
    """Its start, its inferences and its end: the session hears of none of them as speech."""
    heard = HeardOverTheAgent(Finds(), FloorModel(Says(NON_SPEECH), A_STATE, OUTPUTS), lambda: True)
    stream = heard.stream()
    assert isinstance(stream, HeardStream)
    assert stream.tell(an_event(vad.VADEventType.START_OF_SPEECH, 0.25)) == []
    assert not stream.tell(an_event(vad.VADEventType.INFERENCE_DONE, 0.6))[0].speaking
    assert stream.tell(an_event(vad.VADEventType.END_OF_SPEECH, 0.7, speaking=False)) == []
    # The next speech, with the agent quiet, is told as it comes.
    stream.heard.agent_speaks = lambda: False
    start = an_event(vad.VADEventType.START_OF_SPEECH, 0.25)
    assert stream.tell(start) == [start]
    await stream.aclose()


async def test_speech_that_outlasts_any_murmur_or_the_agent_is_the_callers() -> None:
    """Past the longest murmur the session is told whatever the model says; and so when the agent stops by itself."""
    speaks = [True]
    heard = HeardOverTheAgent(Finds(), FloorModel(Says(NON_SPEECH), A_STATE, OUTPUTS), lambda: speaks[0])
    stream = heard.stream()
    assert isinstance(stream, HeardStream)
    stream.tell(an_event(vad.VADEventType.START_OF_SPEECH, 0.25))
    told = stream.tell(an_event(vad.VADEventType.INFERENCE_DONE, NO_MURMUR_LASTS_S))
    assert [one.type for one in told] == [vad.VADEventType.START_OF_SPEECH, vad.VADEventType.INFERENCE_DONE]
    stream.tell(an_event(vad.VADEventType.START_OF_SPEECH, 0.25))
    speaks[0] = False
    assert len(stream.tell(an_event(vad.VADEventType.INFERENCE_DONE, 0.3))) == 2
    await stream.aclose()


def test_an_inference_told_as_quiet_keeps_its_audio_and_its_time() -> None:
    """Only what says "speech" is taken out of it."""
    event = an_event(vad.VADEventType.INFERENCE_DONE, 0.4)
    told = quiet(event)
    assert (told.speaking, told.speech_duration, told.raw_accumulated_speech) == (False, 0.0, 0.0)
    assert (told.type, told.timestamp, told.frames) == (event.type, event.timestamp, event.frames)


def test_a_box_with_no_model_or_one_that_does_not_load_has_none(tmp_path: Path) -> None:
    """Nothing named is nothing loaded, and a file that is no model is said and left."""
    assert load_floor_model(None) is None
    not_a_model = tmp_path / "floor.onnx"
    not_a_model.write_bytes(b"not a model")
    assert load_floor_model(not_a_model) is None
