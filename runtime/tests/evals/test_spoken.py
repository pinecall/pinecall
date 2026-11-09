"""Tests for a persona on a real line: the audio it says, when it may speak, when it hangs up."""

import asyncio
import math
import time
from array import array
from collections.abc import AsyncIterator, Sequence
from dataclasses import dataclass, field
from types import SimpleNamespace
from typing import Never, cast, override

import pytest
from livekit import rtc
from livekit.agents import tts

import pinecall_runtime.evals.service.spoken as spoken
from pinecall_runtime.calls import service as calls
from pinecall_runtime.evals.service.spoken import (
    A_VOICE_RMS,
    FRAME_MS,
    LOST,
    MURMURS,
    SAMPLE_RATE,
    SILENCE,
    CallerLeg,
    Line,
    SpokenLevel,
    SpokenLine,
    at_tempo,
    behind,
    described,
    frames_of,
    in_frames,
    line_of,
    murmur_of,
    pick_caller_voice,
    resampled,
    rms_of,
)
from pinecall_runtime.judging.schemas import CallerBehavior

A_SECOND_IN_FRAMES = 100


# Integer samples put the level near the target, never exactly on it.
WITHIN_THE_ROUNDING_DB = 0.5


VOICES = {"acme/es": "marcos", "acme/en": "henry", "acme/fr": "amelie", "other/es": "lucia"}


LINES = ("Esa me viene bien.", "Sí, confírmemela.")


def tone_of(samples: int, amplitude: int, period: int = 100) -> bytes:
    written = array("h")
    for index in range(samples):
        written.append(int(amplitude * math.sin(2 * math.pi * index / period)))
    return written.tobytes()


async def pieces_of(*pcm: bytes) -> AsyncIterator[bytes]:
    for piece in pcm:
        yield piece


async def frames_at(rate: int, *pcm: bytes) -> AsyncIterator[rtc.AudioFrame]:
    for piece in pcm:
        yield rtc.AudioFrame(piece, rate, 1, len(piece) // 2)


async def joined(frames: AsyncIterator[bytes]) -> bytes:
    return b"".join([frame async for frame in frames])


async def collected(frames: AsyncIterator[bytes]) -> Sequence[bytes]:
    return [frame async for frame in frames]


def difference(mix: bytes, caller: bytes) -> bytes:
    mixed, voice = array("h"), array("h")
    mixed.frombytes(mix)
    voice.frombytes(caller)
    return array("h", (a - b for a, b in zip(mixed, voice, strict=True))).tobytes()


# ── the line ──


def test_a_frame_is_ten_milliseconds_of_the_rate_it_was_cut_at() -> None:
    frames = frames_of(tone_of(SAMPLE_RATE, 8000), SAMPLE_RATE)
    assert FRAME_MS == 10
    assert len(frames) == A_SECOND_IN_FRAMES
    assert all(len(frame) == SAMPLE_RATE // A_SECOND_IN_FRAMES * 2 for frame in frames)


def test_the_last_frame_is_padded_with_silence_rather_than_sent_short() -> None:
    frames = frames_of(tone_of(SAMPLE_RATE // 100 + 10, 8000), SAMPLE_RATE)
    assert len(frames) == 2
    assert len(frames[1]) == len(frames[0])
    assert frames[1].endswith(LOST * 10)


def test_the_interferer_goes_behind_the_frame_at_the_gain_it_is_given() -> None:
    voice = tone_of(480, 8000, period=97)
    television = tone_of(SAMPLE_RATE, 8000, period=31)
    added = difference(behind(voice, television, 0, 0.25), voice)
    assert abs(rms_of(added) / rms_of(television[: len(voice)]) - 0.25) < 0.01


def test_the_interferer_loops_and_goes_on_from_the_sample_it_is_asked_from() -> None:
    television = tone_of(500, 2000, period=50)
    whole = behind(SILENCE + SILENCE, television, 0, 1.0)
    assert behind(SILENCE, television, 480, 1.0) == whole[len(SILENCE) :]
    assert rms_of(whole[-200:]) > 0


def test_a_sum_past_sixteen_bits_is_clipped_never_wrapped() -> None:
    loud = array("h", [32000] * 480).tobytes()
    assert set(array("h", behind(loud, loud, 0, 1.0))) == {32767}


def test_a_caller_is_taken_to_speak_at_a_vendors_level_before_its_first_word() -> None:
    assert SpokenLevel().rms == A_VOICE_RMS


def test_the_callers_level_is_that_of_its_speech_and_its_gaps_do_not_lower_it() -> None:
    level = SpokenLevel()
    loud = frames_of(tone_of(SAMPLE_RATE * 5, 12000), SAMPLE_RATE)
    for frame in loud:
        level.hear(frame)
        level.hear(SILENCE)
    assert abs(20 * math.log10(level.rms / rms_of(loud[0]))) < WITHIN_THE_ROUNDING_DB


def test_the_line_is_described_in_the_words_a_report_prints() -> None:
    assert described(Line()) == "a clean line"
    assert described(Line(interferer_db=15.0)) == "television 15 dB under the caller"
    assert described(Line(interferer_db=22.0, packet_loss=0.02, ambience="cafe")) == (
        "cafe 22 dB under the caller, 2% packet loss"
    )


# ── how the caller acts, beside what it says ──


def test_a_caller_murmurs_in_its_own_language_and_in_english_without_one() -> None:
    assert murmur_of(Line(language="es-ES")) in MURMURS["es"]
    assert murmur_of(Line(language=None)) in MURMURS["en"]
    assert murmur_of(Line(language="xx")) in MURMURS["en"]


async def test_at_the_vendors_own_tempo_the_audio_is_untouched() -> None:
    voice = tone_of(4_800, 8000)
    assert await joined(at_tempo(pieces_of(voice[:2_000], voice[2_000:]), Line())) == voice


async def test_a_faster_caller_says_the_same_line_in_less_time() -> None:
    voice = tone_of(SAMPLE_RATE, 8000)
    quick = await joined(at_tempo(pieces_of(voice), Line(speed=2.0)))
    assert abs(len(quick) / len(voice) - 0.5) < 0.03


# ── the caller's voice ──


async def test_audio_already_at_the_rooms_rate_comes_back_untouched() -> None:
    audio = tone_of(SAMPLE_RATE, 8000)
    assert await joined(resampled(frames_at(SAMPLE_RATE, audio))) == audio


async def test_audio_at_the_vendors_rate_comes_back_as_a_second_at_the_rooms() -> None:
    second = await joined(resampled(frames_at(24_000, tone_of(24_000, 8000))))
    assert abs(len(second) // 2 - SAMPLE_RATE) <= SAMPLE_RATE * FRAME_MS // 1000


async def test_a_line_in_pieces_is_resampled_as_one_line_not_as_pieces_each_with_a_tail() -> None:
    tone = tone_of(24_000, 8000)
    whole = await joined(resampled(frames_at(24_000, tone)))
    in_pieces = await joined(resampled(frames_at(24_000, tone[:7_000], tone[7_000:])))
    assert len(in_pieces) == len(whole)


# ── the line, piece by piece ──


async def test_the_pieces_go_out_in_whole_frames_and_only_the_lines_end_is_padded() -> None:
    first, second = tone_of(1_234, 8000), tone_of(777, 8000)
    frames = await collected(in_frames(pieces_of(first, second)))
    assert {len(frame) for frame in frames} == {len(SILENCE)}
    heard = b"".join(frames)
    assert heard[: len(first + second)] == first + second
    assert heard[len(first + second) :] == LOST * ((len(heard) - len(first + second)) // 2)


# ── the line, carried the whole call ──


@dataclass
class HeardSource:
    """A room's source that keeps what it is handed, at no clock: a frame a turn of the loop."""

    frames: list[bytes] = field(default_factory=list[bytes])

    async def capture_frame(self, frame: rtc.AudioFrame) -> None:
        self.frames.append(bytes(frame.data))
        await asyncio.sleep(0)


@dataclass
class SaidVoice:
    """A voice that says every line as the same audio, in two pieces."""

    audio: bytes

    def synthesize(self, _: str) -> "SaidVoice":
        return self

    async def __aenter__(self) -> AsyncIterator[SimpleNamespace]:
        return self._pieces()

    async def __aexit__(self, *_: object) -> None:
        return None

    async def _pieces(self) -> AsyncIterator[SimpleNamespace]:
        half = len(self.audio) // 4 * 2
        for piece in (self.audio[:half], self.audio[half:]):
            yield SimpleNamespace(frame=rtc.AudioFrame(piece, SAMPLE_RATE, 1, len(piece) // 2))


def leg_on(line: Line, interferer: bytes = b"", voice: bytes = b"") -> tuple[CallerLeg, HeardSource]:
    logs = cast(calls.Logs, SimpleNamespace(store=SimpleNamespace(clock=time.time)))
    leg = CallerLeg(
        SpokenLine("ws://box", "t", "call_1", 3, line), cast(tts.TTS[Never], SaidVoice(voice)), logs, interferer
    )
    source = HeardSource()
    leg.source = cast(rtc.AudioSource, source)
    return leg, source


def test_a_clean_line_with_nobody_speaking_carries_silence() -> None:
    leg, _ = leg_on(Line())
    assert leg.next_frame() == SILENCE


# The fault this replaced: the noise was mixed into each spoken line, so a caller that said nothing
# was on a line of digital silence, and the agent never answered over the room it was tested against.
def test_the_room_is_heard_while_the_caller_says_nothing() -> None:
    television = tone_of(SAMPLE_RATE, 6000, period=31)
    leg, _ = leg_on(Line(interferer_db=15.0), television)
    quiet = b"".join(leg.next_frame() for _ in range(A_SECOND_IN_FRAMES))
    under = 20 * math.log10(A_VOICE_RMS / rms_of(quiet))
    assert abs(under - 15.0) < WITHIN_THE_ROUNDING_DB


def test_the_room_goes_on_from_frame_to_frame_rather_than_restarting_at_each() -> None:
    television = tone_of(3_000, 2000, period=300)
    leg, _ = leg_on(Line(interferer_db=0.0), television)
    heard = b"".join(leg.next_frame() for _ in range(20))
    gain = A_VOICE_RMS / rms_of(television)
    assert heard == behind(LOST * (len(heard) // 2), television, 0, gain)


def test_the_room_keeps_its_level_when_the_caller_speaks_and_when_it_stops() -> None:
    television = tone_of(SAMPLE_RATE, 6000, period=31)
    voice = frames_of(tone_of(SAMPLE_RATE, int(A_VOICE_RMS * math.sqrt(2)), period=97), SAMPLE_RATE)
    leg, _ = leg_on(Line(interferer_db=15.0), television)
    before = rms_of(b"".join(leg.next_frame() for _ in range(A_SECOND_IN_FRAMES)))
    leg.waiting.extend(voice)
    under_the_voice = [difference(leg.next_frame(), frame) for frame in voice]
    after = rms_of(b"".join(leg.next_frame() for _ in range(A_SECOND_IN_FRAMES)))
    assert abs(20 * math.log10(rms_of(b"".join(under_the_voice)) / before)) < WITHIN_THE_ROUNDING_DB
    assert abs(20 * math.log10(after / before)) < WITHIN_THE_ROUNDING_DB


def test_a_lost_packet_is_the_silence_a_jitter_buffer_plays_whoever_was_speaking() -> None:
    television = tone_of(SAMPLE_RATE, 6000, period=31)
    leg, _ = leg_on(Line(interferer_db=15.0, packet_loss=0.5), television)
    frames = [leg.next_frame() for _ in range(A_SECOND_IN_FRAMES)]
    assert {len(frame) for frame in frames} == {len(SILENCE)}
    # Half of a hundred, by chance: outside 20 to 80 once in a billion runs.
    assert 20 < len([frame for frame in frames if frame == SILENCE]) < 80


async def test_a_line_is_said_once_its_last_frame_has_left_and_the_room_is_heard_before_and_after() -> None:
    television = tone_of(SAMPLE_RATE, 6000, period=31)
    voice = tone_of(4_800, 8000, period=97)
    leg, source = leg_on(Line(interferer_db=15.0), television, voice)
    leg.open()
    try:
        await asyncio.sleep(0)
        await asyncio.sleep(0)
        before = len(source.frames)
        await asyncio.wait_for(leg.say("Esa me viene bien."), 2.0)
        said = len(source.frames)
        await asyncio.sleep(0)
        await asyncio.sleep(0)
    finally:
        await leg.close()
    assert before > 0
    assert said - before >= len(voice) // len(SILENCE)
    assert len(source.frames) > said
    assert not leg.waiting
    assert all(rms_of(frame) > 0 for frame in source.frames)


async def test_a_line_that_broke_wakes_the_caller_speaking_on_it_with_what_broke() -> None:
    class Broken(HeardSource):
        @override
        async def capture_frame(self, frame: rtc.AudioFrame) -> None:
            raise ConnectionError("the room is gone")

    leg, _ = leg_on(Line(), voice=tone_of(4_800, 8000))
    leg.source = cast(rtc.AudioSource, Broken())
    leg.open()
    await asyncio.sleep(0)
    with pytest.raises(ConnectionError):
        await asyncio.wait_for(leg.say("Hola."), 2.0)
    await leg.close()


def test_the_caller_speaks_in_the_first_voice_of_its_language_when_the_agent_has_another() -> None:
    assert pick_caller_voice(VOICES, "acme", "someone-else", "es-ES") == "marcos"


def test_an_agent_that_speaks_in_that_voice_has_its_caller_in_another() -> None:
    assert pick_caller_voice(VOICES, "acme", "marcos", "es") == "henry"


def test_a_language_with_no_voice_of_its_own_is_called_in_englishs() -> None:
    assert pick_caller_voice(VOICES, "acme", None, "de") == "henry"


def test_no_caller_voice_is_the_one_the_agent_is_given() -> None:
    for agents_voice in VOICES.values():
        assert pick_caller_voice(VOICES, "acme", agents_voice, "es") != agents_voice


def test_a_persona_with_a_voice_of_its_own_speaks_in_it_unless_it_is_the_agents() -> None:
    assert pick_caller_voice(VOICES, "acme", "marcos", "es", "lucia") == "lucia"
    assert pick_caller_voice(VOICES, "acme", "marcos", "es", "marcos") != "marcos"


def test_a_vendor_the_operator_gave_no_voice_speaks_with_its_own() -> None:
    assert pick_caller_voice(VOICES, "nobody", None, "es") is None


def test_the_room_the_caller_joins_is_the_one_it_was_given() -> None:
    line = spoken.SpokenLine("ws://box", "t", "call_1", 3, Line())
    assert (line.url, line.call, line.turns) == ("ws://box", "call_1", 3)


def test_the_line_is_the_requests_noise_or_else_the_personas_and_carries_how_it_acts() -> None:
    behavior = CallerBehavior(
        interrupts=0.4,
        pause_s=1.5,
        interferer_db=12.0,
        packet_loss=0.05,
        backchannels=0.3,
        speed=0.8,
        ambience="office",
    )
    own = line_of(behavior, None, 0.0)
    assert (own.interferer_db, own.packet_loss, own.interrupts, own.pause_s) == (
        12.0,
        0.05,
        0.4,
        1.5,
    )
    # A preview wants a caller that answers at once: the request's pause stands over the persona's.
    assert line_of(behavior, None, 0.0, pause_s=0.0).pause_s == 0.0
    assert (own.backchannels, own.speed, own.ambience) == (0.3, 0.8, "office")
    named = line_of(behavior, 20.0, 0.1, "street")
    assert (named.interferer_db, named.packet_loss, named.interrupts) == (20.0, 0.1, 0.4)
    assert named.ambience == "street"


# G B2 (2026-10-23): a caller that cut in asked for its line only then, and paused before it as before any
# line, so the answer it meant to talk over was over by the time it spoke.
async def test_a_caller_that_cuts_in_asks_for_its_line_as_the_agent_begins_and_says_it_with_no_pause(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def began(*_: object, **__: object) -> None:
        return None

    monkeypatch.setattr(spoken, "speaking", began)
    monkeypatch.setattr(spoken, "CUT_IN_AFTER_S", (0.0, 0.0))
    logs = cast(calls.Logs, SimpleNamespace(store=SimpleNamespace(clock=time.time)))
    line = Line(interrupts=1.0, pause_s=30.0)
    leg = spoken.CallerLeg(spoken.SpokenLine("ws://box", "t", "call_1", 3, line), cast(tts.TTS[Never], None), logs, b"")
    said: list[str] = []

    async def speak(text: str) -> None:
        said.append(text)

    monkeypatch.setattr(leg, "_speak", speak)
    asked: list[bool] = []
    assert await leg.line_answered(1, lambda: asked.append(True)) is True
    assert asked == [True]
    await asyncio.wait_for(leg.say("wait, the Tuesday one"), 1.0)
    assert said == ["wait, the Tuesday one"]
