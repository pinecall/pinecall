"""Whether a caller speaking over the agent is taking the floor or only agreeing: a model's word on the audio itself."""

import asyncio
import contextlib
import dataclasses
import importlib
import logging
from collections import deque
from collections.abc import AsyncGenerator, AsyncIterator, Callable, Mapping, Sequence
from pathlib import Path
from typing import Literal, Protocol, override

import numpy as np
from livekit import rtc
from livekit.agents import stt, vad

logger = logging.getLogger(__name__)

# Until 2026-11 a caller stopped the agent by two words of the transcript, and by nothing else: the
# ears had to write them first, 0.8 to 1.1 s after the caller began (measured on four calls), and
# an "mm-hmm" the ears wrote as two words stopped it as a sentence would. The model here listens to
# the caller's audio while the agent speaks and says, every 20 ms, whether they are agreeing or
# taking the floor: Pipecat's backchannel detector, a causal convolution and a GRU of 734 k
# parameters, BSD-2-Clause, on a CPU. Measured on the test box (2026-11-15), synthetic voices over
# the agent's real answers, four voices a line: every interruption of 32 in English and of 32 in
# Spanish called within 0.6 s, most within 0.3; no "mm", "ajá", "uh-huh" or "yeah" of 68 called
# one. What it gets wrong is agreement said as a word, and more so in Spanish, the language it
# was not trained on: "sí, sí", "vale", "entiendo" and "I see" every time. Bernardo's call, that
# day: such a word stopping the agent is fine, and better than waiting for the ears.
# It is no replacement for the voice detector: it only says what the speech the detector found is.
# While the agent speaks, the session is told of the caller's speech when the model calls it a
# floor-take, or once it has lasted so long that it is no agreement whatever the model says; the
# rest of the time the detector's events pass as they come.
# The ears write a speech after it was said, and after the model's word on it: the "mm-hmm" the
# session was never told of comes back as a transcript half a second later, and livekit stops the
# agent on any transcript that arrives over it. Until 2026-11-15 a list of words per language said
# which transcripts were agreement. A list is not what heard the speech: it did not know the "ajá"
# the ears wrote as "Uh-huh.", and no list of any length is the caller's voice. What the ears write
# of the caller's last speech over the agent follows the model's word on that speech (SaidOverTheAgent
# below), as livekit holds the transcripts of an overlap for its own hosted detector.

# The model's own rate, the samples it takes at a time (40 ms) and the frames it answers per chunk.
RATE = 16_000
CHUNK = 640
FRAME_S = 0.02
# Its five answers per frame, in its order: two ways of agreeing, two of taking the floor, no speech.
CONTINUER, ASSESSMENT, NEGATIVE, FLOOR_TAKE, NON_SPEECH = range(5)
# How sure it must be, and for how many frames together (200 ms). An interruption holds the model's
# floor score near 0.9 for as long as it lasts; a murmur crosses 0.8 for an instant and falls. The
# model is trained on English alone (its page says so), and how long it holds its word is what tells
# the two apart in a language it never heard. Measured on the recordings of 2026-11-15's simulated
# calls, the caller's channel replayed through the model: held for 100 ms, as it was until then, 3 of
# 76 English murmurs and 9 of 31 Spanish ones were called a floor-take (the Spanish calls of that day
# stopped their agent as often); held for 200 ms, 2 and 3, and every interruption called before is
# still called (49 of 51 in English, 21 of 21 in Spanish), a median 440 ms after the caller began
# where it was 340. Held for 300 ms, one Spanish interruption of the 21 is lost.
TAKEN_AT = 0.8
JUDGED_OVER = 10
# Speech over the agent this long is the caller's whatever the model says: no murmur measured ran
# past 0.9 s, and its own page uses the same backstop.
NO_MURMUR_LASTS_S = 1.2
# A line that carries nothing is digital silence (a carrier sends it between words), which nothing the model learnt
# from has: under 8 of 32767 of noise it called 16 % of the murmurs a floor-take where it called
# 26 % on silence itself.
A_ROOMS_OWN_NOISE = 8.0
# The noise's index starts over after this many samples (six seconds, a prime): the sine it is drawn
# from is read where a float still tells one sample from the next.
A_LONG_WHILE = 100_003
FULL_SCALE = 32768.0
# What it is told of the agent, per frame: speaking or not, and the seconds since it began, since
# its last pause of this long ended, and since it stopped, each no more than CLIPPED_S and over it.
A_PAUSE_S = 0.2
CLIPPED_S = 5.0


# What the model is given beside the state it carries from one chunk to the next, and where it runs.
GIVEN = ("chunk", "bot_state")
ON_A_CPU = "CPUExecutionProvider"


class _Runs(Protocol):
    def run(self, output_names: Sequence[str] | None, input_feed: Mapping[str, np.ndarray]) -> list[np.ndarray]: ...


class _Tensor(Protocol):
    name: str
    shape: Sequence[int]


class _Session(_Runs, Protocol):
    def get_inputs(self) -> Sequence[_Tensor]: ...
    def get_outputs(self) -> Sequence[_Tensor]: ...


class _Threads(Protocol):
    intra_op_num_threads: int
    inter_op_num_threads: int


class FloorModel:
    """The model as a process holds it: loaded once, every call a stream of its own state."""

    def __init__(self, runs: _Runs, states: Mapping[str, tuple[int, ...]], outputs: Sequence[str]) -> None:
        """What runs it, the state it carries from one chunk to the next by name and shape, and what it answers."""
        self.runs = runs
        self.states = dict(states)
        self.outputs = list(outputs)

    def open_stream(self) -> "Overlap":
        """A stream for one call: nothing of another call's audio is in its state."""
        return Overlap(self)


class AgentsClock:
    """What the model is told of the agent each frame: whether it speaks, how long since it began, paused, stopped."""

    def __init__(self) -> None:
        """An agent that has not spoken on this call: every count at its ceiling."""
        self.since_onset = self.since_pause = self.since_stop = CLIPPED_S
        self.silent_for = 0.0
        self.spoke = False

    def tick(self, speaking: bool) -> np.ndarray:
        """One 20 ms frame's eight numbers: the flag, the three counts over their ceiling, no filler, three unused."""
        if speaking and not self.spoke:
            self.since_onset = 0.0
            if self.silent_for >= A_PAUSE_S:
                self.since_pause = 0.0
        if self.spoke and not speaking:
            self.since_stop = 0.0
        self.silent_for = 0.0 if speaking else self.silent_for + FRAME_S
        told = np.zeros(8, dtype=np.float32)
        told[:4] = [
            float(speaking),
            min(self.since_onset, CLIPPED_S) / CLIPPED_S,
            min(self.since_pause, CLIPPED_S) / CLIPPED_S,
            min(self.since_stop, CLIPPED_S) / CLIPPED_S,
        ]
        self.since_onset += FRAME_S
        self.since_pause += FRAME_S
        self.since_stop += FRAME_S
        self.spoke = speaking
        return told


class Overlap:
    """One call's audio through the model: after each frame, how sure it is that the caller is taking the floor."""

    def __init__(self, model: FloorModel) -> None:
        """A call nobody was heard on yet."""
        self.model = model
        self.state = {name: np.zeros(shape, dtype=np.float32) for name, shape in model.states.items()}
        self.clock = AgentsClock()
        self.resampler: rtc.AudioResampler | None = None
        self.rate = 0
        self.waiting = np.zeros(0, dtype=np.float32)
        self.recent: deque[float] = deque(maxlen=JUDGED_OVER)
        # The samples judged so far: where the noise under the next chunk is drawn from.
        self.heard = 0

    @property
    def taken(self) -> bool:
        """Whether the model has called the floor taken, over the last frames together."""
        return len(self.recent) == JUDGED_OVER and sum(self.recent) / JUDGED_OVER >= TAKEN_AT

    def hear(self, frame: rtc.AudioFrame, *, agent_speaks: bool) -> None:
        """Take the caller's next frame, at whatever rate it comes, and judge every whole chunk of it."""
        for piece in self._at_the_models_rate(frame):
            samples = np.frombuffer(piece.data.tobytes(), dtype=np.int16).astype(np.float32)
            self.waiting = np.concatenate([self.waiting, samples])
        while len(self.waiting) >= CHUNK:
            self._judge(self.waiting[:CHUNK], agent_speaks)
            self.waiting = self.waiting[CHUNK:]

    def forget(self) -> None:
        """What was judged of the speech that just ended says nothing of the next."""
        self.recent.clear()

    # The resampler is livekit's own handle: let go while the call still has its room, not as the
    # process exits, when livekit has nothing left to free it with.
    def close(self) -> None:
        """Let go of what the stream held."""
        self.resampler = None

    def _at_the_models_rate(self, frame: rtc.AudioFrame) -> list[rtc.AudioFrame]:
        if frame.sample_rate == RATE:
            return [frame]
        if self.resampler is None or self.rate != frame.sample_rate:
            self.resampler = rtc.AudioResampler(input_rate=frame.sample_rate, output_rate=RATE)
            self.rate = frame.sample_rate
        return self.resampler.push(frame)

    # A hash of the sample's index, as kit.noise draws its own: the same on every machine, and no
    # generator's state to carry. Uniform, at the level whose spread is A_ROOMS_OWN_NOISE.
    def _a_rooms_noise(self) -> np.ndarray:
        index = np.arange(self.heard, self.heard + CHUNK, dtype=np.float64) % A_LONG_WHILE
        self.heard += CHUNK
        drawn = np.mod(np.sin(index * 12.9898) * 43758.5453, 1.0) - 0.5
        noise: np.ndarray = (drawn * np.sqrt(12.0) * A_ROOMS_OWN_NOISE).astype(np.float32)
        return noise

    def _judge(self, chunk: np.ndarray, agent_speaks: bool) -> None:
        heard = (chunk + self._a_rooms_noise()) / FULL_SCALE
        told = np.stack([self.clock.tick(agent_speaks), self.clock.tick(agent_speaks)])
        feed = {"chunk": heard[None, :].astype(np.float32), "bot_state": told[None, :, :], **self.state}
        answered = dict(zip(self.model.outputs, self.model.runs.run(self.model.outputs, feed), strict=True))
        self.state = {name: answered[f"{name}_out"] for name in self.state}
        for frame in answered["intent"][0]:
            self.recent.append(float(frame[NEGATIVE] + frame[FLOOR_TAKE]))


# The model's word on the caller's last speech over the agent: theirs, agreement, or none yet.
Word = Literal["theirs", "agreement", "none yet"]


class SaidOverTheAgent:
    """What the ears wrote of the caller's last speech over the agent, passed on by the model's word on that speech."""

    def __init__(self, agent_speaks: Callable[[], bool]) -> None:
        """A call nobody has spoken over: what the ears write is the caller's."""
        self.agent_speaks = agent_speaks
        self.word: Word = "theirs"
        # What the ears wrote of a speech the model has no word on yet, in their order.
        self.kept: list[stt.SpeechEvent] = []
        # What is the caller's after all, until whoever reads the ears takes it.
        self.released: deque[stt.SpeechEvent] = deque()
        self.judged = asyncio.Event()

    def began(self) -> None:
        """A speech began over the agent: the model has no word on it yet."""
        self.word = "none yet"

    def is_the_callers(self) -> None:
        """The speech is the caller's: what the ears wrote of it is passed on, in their order."""
        self.word = "theirs"
        self._let_go(self.kept)

    # The ears' own start and end of a speech are no words: they pass, so no start is left without its end.
    def was_agreement(self) -> None:
        """The speech ended as it began, agreement: the words the ears wrote of it are nobody's turn."""
        self.word = "agreement"
        self._let_go([event for event in self.kept if not carries_words(event)])

    # Read between the ears and the session (the agent's stt_node). The model's word comes from the
    # voice detector's task, sometimes after the ears' last event of the speech: what was kept is
    # passed on as the word comes, not when the ears next write.
    async def only_the_callers(self, written: AsyncGenerator[stt.SpeechEvent]) -> AsyncIterator[stt.SpeechEvent]:
        """The ears' events, each once its speech has the model's word: but the words of a speech that was agreement."""
        coming: asyncio.Task[stt.SpeechEvent | None] | None = None
        async with contextlib.aclosing(written):
            try:
                while True:
                    if coming is None:
                        coming = asyncio.ensure_future(anext(written, None))
                    word = asyncio.ensure_future(self.judged.wait())
                    try:
                        await asyncio.wait({coming, word}, return_when=asyncio.FIRST_COMPLETED)
                    finally:
                        word.cancel()
                    self.judged.clear()
                    ended = False
                    if coming.done():
                        event, coming = coming.result(), None
                        ended = event is None
                        if event is not None:
                            self._take(event)
                    while self.released:
                        yield self.released.popleft()
                    if ended:
                        return
            finally:
                # The read still waiting is the ears' own: it ends before they are closed.
                if coming is not None:
                    coming.cancel()
                    with contextlib.suppress(asyncio.CancelledError):
                        await coming

    # Nothing is said over an agent that is not speaking: whatever was kept is the caller's by then.
    def _take(self, event: stt.SpeechEvent) -> None:
        if not self.agent_speaks():
            self.is_the_callers()
        if event.type is stt.SpeechEventType.RECOGNITION_USAGE:
            self.released.append(event)
        elif self.word == "none yet":
            self.kept.append(event)
        elif self.word == "theirs" or not carries_words(event):
            self.released.append(event)

    def _let_go(self, events: list[stt.SpeechEvent]) -> None:
        self.released.extend(events)
        self.kept.clear()
        if self.released:
            self.judged.set()


def carries_words(event: stt.SpeechEvent) -> bool:
    """Whether an event of the ears says anything the caller would have said."""
    return bool(event.alternatives and event.alternatives[0].text.strip())


class HeardOverTheAgent(vad.VAD):
    """The voice detector as the session hears it: over the agent, only the speech the model calls a floor-take."""

    def __init__(self, detector: vad.VAD, model: FloorModel, agent_speaks: Callable[[], bool]) -> None:
        """Over the detector the session would have had, for one call."""
        super().__init__(capabilities=detector.capabilities)
        self.detector = detector
        self.floor_model = model
        self.agent_speaks = agent_speaks
        # The model's word on each speech, for whoever reads what the ears write of it.
        self.said = SaidOverTheAgent(agent_speaks)

    @property
    @override
    def model(self) -> str:
        """The detector's own model: this adds no detector, only a word on what it found."""
        return self.detector.model

    @property
    @override
    def provider(self) -> str:
        """The detector's own provider."""
        return self.detector.provider

    @override
    def stream(self) -> "HeardStream":
        """A stream of the detector's, and a stream of the model's beside it."""
        return HeardStream(self, self.detector.stream(), self.floor_model.open_stream())


class HeardStream(vad.VADStream):
    """One stream of the detector's events, the caller's speech over the agent held back until it is a floor-take."""

    def __init__(self, heard: HeardOverTheAgent, found: vad.VADStream, overlap: Overlap) -> None:
        """Nothing held."""
        self.heard = heard
        self.found = found
        self.overlap = overlap
        # The start of the speech that began over the agent, until it is told or it ends untold.
        self.held: vad.VADEvent | None = None
        super().__init__(heard)

    @override
    async def _main_task(self) -> None:
        feeding = asyncio.create_task(self._feed())
        try:
            async for event in self.found:
                for told in self.tell(event):
                    self._event_ch.send_nowait(told)
        finally:
            feeding.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await feeding
            self.overlap.close()
            await self.found.aclose()

    # Both hear every frame: the detector to find speech, the model to say what the speech is.
    async def _feed(self) -> None:
        async for item in self._input_ch:
            if isinstance(item, rtc.AudioFrame):
                self.found.push_frame(item)
                self.overlap.hear(item, agent_speaks=self.heard.agent_speaks())
            else:
                self.found.flush()
                self.held = None
                self.heard.said.is_the_callers()
        self.found.end_input()

    def tell(self, event: vad.VADEvent) -> list[vad.VADEvent]:
        """What the session is told of one event of the detector's: it, nothing, or the start it was not told before."""
        said = self.heard.said
        if event.type is vad.VADEventType.START_OF_SPEECH:
            if not self.heard.agent_speaks():
                said.is_the_callers()
                return [event]
            self.held = event
            self.overlap.forget()
            said.began()
            return []
        if self.held is None:
            # Agreement was over the agent's words: once it is quiet, nothing is said over it.
            if not self.heard.agent_speaks():
                said.is_the_callers()
            return [event]
        if event.type is vad.VADEventType.END_OF_SPEECH:
            # It ended as it began, agreement: the session never knew of it.
            self.held = None
            said.was_agreement()
            return []
        if self._is_the_callers_now(event):
            start, self.held = self.held, None
            said.is_the_callers()
            return [dataclasses.replace(start, speech_duration=event.speech_duration, timestamp=event.timestamp), event]
        return [quiet(event)]

    # The agent stopping by itself hands the floor over: what the caller is saying is theirs from then.
    def _is_the_callers_now(self, event: vad.VADEvent) -> bool:
        return self.overlap.taken or event.speech_duration >= NO_MURMUR_LASTS_S or not self.heard.agent_speaks()


def quiet(event: vad.VADEvent) -> vad.VADEvent:
    """An inference of the detector's told as one that found no speech: the session neither pauses nor counts."""
    return dataclasses.replace(event, speaking=False, speech_duration=0.0, raw_accumulated_speech=0.0)


# A process that cannot load it says so once and takes its calls as before: by the ears' words.
def load_floor_model(weights: Path | None) -> FloorModel | None:
    """The model the settings name, loaded on one thread; None when they name none, or when it does not load."""
    if weights is None:
        return None
    try:
        # The ONNX runtime has no types of its own: what is used of it is said here, once.
        onnx = importlib.import_module("onnxruntime")
        options: _Threads = onnx.SessionOptions()
        options.intra_op_num_threads = 1
        options.inter_op_num_threads = 1
        session: _Session = onnx.InferenceSession(str(weights), sess_options=options, providers=[ON_A_CPU])
        carried = {
            one.name: tuple(int(size) for size in one.shape) for one in session.get_inputs() if one.name not in GIVEN
        }
        answers = [one.name for one in session.get_outputs()]
    except Exception:
        logger.warning("the floor model at %s did not load: calls go on without it", weights, exc_info=True)
        return None
    return FloorModel(session, carried, answers)
