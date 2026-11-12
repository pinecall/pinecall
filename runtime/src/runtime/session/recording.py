"""A call's audio recorded by its own session: the caller left, every other voice right."""

import asyncio
import logging
import time
from collections.abc import Callable
from pathlib import Path

import numpy as np
from livekit import rtc
from livekit.agents import AgentSession
from livekit.agents.voice.recorder_io import RecorderIO

from runtime.kit import pcm
from runtime.session.call import Call
from runtime.session.hold import VOLUME
from runtime.wire.parts import ParticipantKind

logger = logging.getLogger(__name__)

# livekit's recorder wraps the session's audio in and out and places both on one timeline: the
# caller on the left, the agent on the right, encoded in a thread of this process. Egress did the
# same work in a process of its own per call (~0.12 vCPU, ~80 MB), and a track egress per voice
# costs more still (~0.1 vCPU and ~170 MB a track, the load lab 2026-10-02): the voices are already
# decoded here, so the recording is made here. A supervisor who takes over and the far end of a
# transfer are the room's, not the session's: each is heard from its own track while it speaks and
# spooled beside the file, and with the hold melody (from its clip, where it sounded) they are laid
# in on the right when the file is closed: the file decoded and encoded once more, a stretch at a
# time. That costs about a fiftieth of the call's length on one core (ten minutes in ~13 s on a
# laptop's), within the worker's sealing budget for the calls a phone line takes; a call with no
# other voice and no hold is never touched again. The session closes the recorder before the seal,
# so the file is whole when the summary names it.

# The agent's voice comes at 24 kHz and a phone at 8: 48 keeps nothing more (~10 % of a worker's
# cores less, the load lab).
RATE = 24000
# Who in the room speaks into the recording besides the session's own two.
OTHERS = frozenset({"supervisor", "sip"})
LOST = "a voice in the room of %s is not in its recording"
NOT_LAID_IN = "the other voices and the melody of %s are not in its recording: the file stays as it was recorded"

# Who a participant of the room is to the call, as the room tells it.
type KindOf = Callable[[rtc.Participant], ParticipantKind]
# The melody's clip and when it sounded, by the clock.
type Melody = tuple[Path | None, list[tuple[float, float]]]


class Recorder:
    """The call's file: livekit's recorder for its two sides, the room's other voices beside."""

    def __init__(self, recorder: RecorderIO, audio: Path, room: rtc.Room | None, kind_of: KindOf) -> None:
        """A recording that started now and heard nobody else yet."""
        self.recorder = recorder
        self.audio = audio
        self.room = room
        self.kind_of = kind_of
        self.others: list[tuple[float, Path]] = []
        self.tasks: set[asyncio.Task[None]] = set()

    def listen(self) -> None:
        """Hear every other voice the room has, and each one that joins from now on."""
        if self.room is None:
            return
        self.room.on("track_subscribed", self._on_track_subscribed)  # pyright: ignore[reportUnknownMemberType]
        for participant in self.room.remote_participants.values():
            for publication in participant.track_publications.values():
                if publication.track is not None:
                    self._on_track_subscribed(publication.track, publication, participant)

    # The file livekit's recorder wrote is whole before anything is laid in, and laying in writes a
    # file beside it and puts it in its place at the end: one that breaks (a clip that does not
    # decode, a full disk) is said and leaves the recording as it was. Until 2026-11 it raised out of
    # the session's close, and the call was left without its last entry and its seal.
    async def close(self, melody: Melody) -> None:
        """Finish the file; lay in the other voices and the melody when there were any."""
        if self.room is not None:
            self.room.off("track_subscribed", self._on_track_subscribed)  # pyright: ignore[reportUnknownMemberType]
        for task in self.tasks:
            task.cancel()
        await asyncio.gather(*self.tasks, return_exceptions=True)
        await self.recorder.aclose()
        began = self.recorder.recording_started_at
        clip, played = melody
        if began is None or (not self.others and not played):
            return
        spans = [(start - began, end - began) for start, end in played]
        try:
            await asyncio.to_thread(lay_in, self.audio, self.others, (clip, spans))
        except Exception:
            logger.warning(NOT_LAID_IN, self.audio.parent.name, exc_info=True)

    def _on_track_subscribed(
        self, track: rtc.Track, _publication: rtc.TrackPublication, participant: rtc.RemoteParticipant
    ) -> None:
        if not isinstance(track, rtc.RemoteAudioTrack) or self.kind_of(participant) not in OTHERS:
            return
        task = asyncio.create_task(self._hear(track))
        self.tasks.add(task)
        task.add_done_callback(self.tasks.discard)

    # The track's frames come continuous (the jitter buffer fills a silence), so one run a voice,
    # spooled as it comes and placed where its first frame arrived. A run that breaks is said and
    # kept as far as it got: the recording is the call's, with or without that voice.
    async def _hear(self, track: rtc.RemoteAudioTrack) -> None:
        began = self.recorder.recording_started_at or time.time()
        spool = self.audio.with_name(f"{track.sid}.pcm")
        stream = rtc.AudioStream(track, sample_rate=RATE, num_channels=1)
        try:
            with spool.open("wb") as sink:
                async for event in stream:
                    if sink.tell() == 0:
                        self.others.append((time.time() - event.frame.duration - began, spool))
                    sink.write(event.frame.data)
        except Exception:
            logger.warning(LOST, self.audio.parent.name, exc_info=True)
        finally:
            await stream.aclose()


async def record(
    live: AgentSession[Call], audio: Path | None, room: rtc.Room | None, kind_of: KindOf
) -> Recorder | None:
    """Record the call into the file from now on; None when it keeps no audio."""
    caller, agent = live.input.audio, live.output.audio
    if audio is None or caller is None or agent is None:
        return None
    recorder = RecorderIO(agent_session=live, sample_rate=RATE)
    live.input.audio = recorder.record_input(caller)
    live.output.audio = recorder.record_output(agent)
    await recorder.start(output_path=audio)
    recording = Recorder(recorder, audio, room, kind_of)
    recording.listen()
    return recording


# Blocking, for a thread: the mixing itself is the kit's (kit/pcm.py), a stretch at a time.
def lay_in(audio: Path, others: list[tuple[float, Path]], melody: Melody) -> None:
    """Add the other voices and the melody to the recording's right channel, each at its time."""
    sounds = [*(_voice(at_s, spool) for at_s, spool in others), *_tune(*melody)]
    pcm.lay_sounds(audio, sounds, rate=RATE)
    for _, spool in others:
        spool.unlink(missing_ok=True)


def _voice(at_s: float, spool: Path) -> pcm.Sound:
    samples = np.memmap(spool, dtype="<i2", mode="r")

    def stretch(at: int, count: int) -> np.ndarray:
        return samples[at : at + count].astype(np.float32) / 32768

    return pcm.Sound(round(at_s * RATE), len(samples), stretch)


# The melody loops from the start of each span, as the player played it.
def _tune(clip: Path | None, spans: list[tuple[float, float]]) -> list[pcm.Sound]:
    pieces = [] if clip is None else list(pcm.decode(clip, "mono", rate=RATE))
    if not pieces or not spans:
        return []
    tune = np.concatenate(pieces, axis=1)[0] * VOLUME

    def stretch(at: int, count: int) -> np.ndarray:
        return np.take(tune, np.arange(at, at + count) % len(tune))

    return [
        pcm.Sound(round(start_s * RATE), max(round((end_s - start_s) * RATE), 0), stretch) for start_s, end_s in spans
    ]
