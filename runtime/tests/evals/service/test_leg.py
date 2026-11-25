"""Tests for a persona on a real line: the audio it says, the room behind it, when it cuts in."""

import asyncio
import math
import random
from array import array
from collections.abc import AsyncIterator

import pytest
from livekit import rtc

from runtime.calls.log.store import Store
from runtime.evals.service.leg import (
    A_ROOM_FADES_FRAMES,
    A_VOICE_RMS,
    FRAME_MS,
    MURMURS,
    SAMPLE_RATE,
    SILENCE,
    CallerLeg,
    Pace,
    Spoken,
    SpokenLevel,
    at_tempo,
    describe,
    pick_murmur,
    resample,
    tempo_of,
    with_pauses,
)
from runtime.exceptions import ValidationError
from runtime.judging import service as judging
from runtime.kit.link import LinkShape
from runtime.kit.pcm import QUIET, frames_of, in_frames, mix_under, rms_of
from tests.calls.factories import logs_on
from tests.conftest import needs_the_database
from tests.fakes.acme import AcmeTTS

A_SECOND_IN_FRAMES = 100
# Integer samples put the level near the target, never exactly on it.
WITHIN_THE_ROUNDING_DB = 0.5


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


def difference(mix: bytes, caller: bytes) -> bytes:
    mixed, voice = array("h"), array("h")
    mixed.frombytes(mix)
    voice.frombytes(caller)
    return array("h", (a - b for a, b in zip(mixed, voice, strict=True))).tobytes()


# ── the caller's level, and the line in a report's words ──


def test_a_caller_is_taken_to_speak_at_a_vendors_level_before_its_first_word() -> None:
    assert SpokenLevel().rms == A_VOICE_RMS


def test_the_callers_level_is_that_of_its_speech_and_its_gaps_do_not_lower_it() -> None:
    level = SpokenLevel()
    loud = frames_of(tone_of(SAMPLE_RATE * 5, 12000), SAMPLE_RATE, FRAME_MS)
    for frame in loud:
        level.hear(frame)
        level.hear(SILENCE)
    assert abs(20 * math.log10(level.rms / rms_of(loud[0]))) < WITHIN_THE_ROUNDING_DB


def test_the_line_is_described_in_the_words_a_report_prints() -> None:
    clean = LinkShape()
    assert describe(judging.Behavior(), clean) == "a clean line"
    assert describe(judging.Behavior(interferer_db=15.0), clean) == "television 15 dB under the caller"
    assert describe(judging.Behavior(interferer_db=22.0, ambience="cafe"), LinkShape(loss=0.02)) == (
        "cafe 22 dB under the caller, 2% packet loss"
    )


def test_a_lines_network_and_its_phone_are_part_of_how_it_is_described() -> None:
    mobile = LinkShape(loss=0.05, delay_ms=150, jitter_ms=40, rate_kbps=64)
    assert describe(judging.Behavior(), mobile) == "5% packet loss, 150 ms delay ± 40 ms, 64 kbps"
    assert describe(judging.Behavior(), LinkShape(delay_ms=300)) == "300 ms delay"
    assert describe(judging.Behavior(), LinkShape(), by_phone=True) == "a phone line"
    assert describe(judging.Behavior(), LinkShape(loss=0.1), by_phone=True) == "a phone line, 10% packet loss"


# ── how the caller acts, beside what it says ──


def test_a_caller_murmurs_in_its_own_language_and_in_english_without_one() -> None:
    dice = random.Random()
    assert pick_murmur("es-ES", dice) in MURMURS["es"]
    assert pick_murmur(None, dice) in MURMURS["en"]
    assert pick_murmur("xx", dice) in MURMURS["en"]


async def test_at_the_vendors_own_tempo_the_audio_is_untouched() -> None:
    voice = tone_of(4_800, 8000)
    assert await joined(at_tempo(pieces_of(voice[:2_000], voice[2_000:]), 1.0)) == voice


async def test_a_faster_caller_says_the_same_line_in_less_time() -> None:
    voice = tone_of(SAMPLE_RATE, 8000)
    quick = await joined(at_tempo(pieces_of(voice), 2.0))
    assert abs(len(quick) / len(voice) - 0.5) < 0.03


# 2026-11-25: a slow caller was its line stretched whole, with no pause in it.
async def test_a_slow_caller_says_its_words_nearly_as_read_and_holds_the_breaks_between_them() -> None:
    word, a_break = tone_of(SAMPLE_RATE // 2, 8000), SILENCE * 20
    frames = [piece async for piece in in_frames(pieces_of(word + a_break + word), SAMPLE_RATE, FRAME_MS)]

    async def said() -> AsyncIterator[bytes]:
        for frame in frames:
            yield frame

    slow = [frame async for frame in with_pauses(said(), 0.5, random.Random(7))]
    held = len(slow) - len(frames)
    assert 54 <= held <= 126
    assert [frame for frame in slow if frame != SILENCE] == [frame for frame in frames if frame != SILENCE]
    assert [frame async for frame in with_pauses(said(), 1.0, random.Random(7))] == frames
    assert tempo_of(0.7) == pytest.approx(0.9) and tempo_of(1.3) == 1.3


# ── the caller's voice ──


async def test_audio_already_at_the_rooms_rate_comes_back_untouched() -> None:
    audio = tone_of(SAMPLE_RATE, 8000)
    assert await joined(resample(frames_at(SAMPLE_RATE, audio))) == audio


async def test_audio_at_the_vendors_rate_comes_back_as_a_second_at_the_rooms() -> None:
    second = await joined(resample(frames_at(24_000, tone_of(24_000, 8000))))
    assert abs(len(second) // 2 - SAMPLE_RATE) <= SAMPLE_RATE * FRAME_MS // 1000


async def test_a_line_in_pieces_is_resampled_as_one_line_not_as_pieces_each_with_a_tail() -> None:
    tone = tone_of(24_000, 8000)
    whole = await joined(resample(frames_at(24_000, tone)))
    in_pieces = await joined(resample(frames_at(24_000, tone[:7_000], tone[7_000:])))
    assert len(in_pieces) == len(whole)


# ── the line, carried the whole call ──


def leg_on(store: Store, call: str, acts: judging.Behavior, interferer: bytes = b"") -> CallerLeg:
    """The caller's leg of the call, acting so, with this playing behind it: on a voice of the box's vendor."""
    return CallerLeg(Spoken(call, acts), AcmeTTS(speech_key="k"), logs_on(store).logs, store, interferer)


@needs_the_database
async def test_a_clean_line_with_nobody_speaking_carries_silence(store: Store, call: str) -> None:
    assert leg_on(store, call, judging.Behavior()).next_frame() == SILENCE


# The fault this replaced: the noise was mixed into each spoken line, so a caller that said nothing
# was on a line of digital silence, and the agent never answered over the room it was tested against.
@needs_the_database
async def test_the_room_is_heard_while_the_caller_says_nothing(store: Store, call: str) -> None:
    television = tone_of(SAMPLE_RATE, 6000, period=31)
    leg = leg_on(store, call, judging.Behavior(interferer_db=15.0), television)
    quiet = b"".join(leg.next_frame() for _ in range(A_SECOND_IN_FRAMES))
    under = 20 * math.log10(A_VOICE_RMS / rms_of(quiet))
    assert abs(under - 15.0) < WITHIN_THE_ROUNDING_DB


# 2026-11-25: a television that never stops was transcribed as the caller's turns, at any level tried. A
# room heard behind some of the caller's lines alone is silent until one of them and gone after it.
@needs_the_database
async def test_a_room_heard_behind_some_lines_alone_comes_up_with_a_line_and_is_gone_after_it(
    store: Store, call: str
) -> None:
    television = tone_of(SAMPLE_RATE, 6000, period=31)
    leg = leg_on(store, call, judging.Behavior(interferer_db=15.0, ambience_turns=0.5), television)
    assert all(leg.next_frame() == SILENCE for _ in range(A_SECOND_IN_FRAMES))
    leg.heard = True
    rising = [rms_of(leg.next_frame()) for _ in range(A_ROOM_FADES_FRAMES)]
    assert 0 < rising[0] < rising[-1]
    leg.heard = False
    falling = [rms_of(leg.next_frame()) for _ in range(A_ROOM_FADES_FRAMES)]
    assert falling[0] > falling[-1] == 0
    assert leg.next_frame() == SILENCE
    with pytest.raises(ValidationError, match="ambience_turns is a share"):
        judging.Behavior(ambience_turns=1.5)


@needs_the_database
async def test_the_room_goes_on_from_frame_to_frame_rather_than_restarting_at_each(store: Store, call: str) -> None:
    television = tone_of(3_000, 2000, period=300)
    leg = leg_on(store, call, judging.Behavior(interferer_db=0.0), television)
    heard = b"".join(leg.next_frame() for _ in range(20))
    gain = A_VOICE_RMS / rms_of(television)
    assert heard == mix_under(QUIET * (len(heard) // 2), television, 0, gain)


@needs_the_database
async def test_the_room_keeps_its_level_when_the_caller_speaks_and_when_it_stops(store: Store, call: str) -> None:
    television = tone_of(SAMPLE_RATE, 6000, period=31)
    voice = frames_of(tone_of(SAMPLE_RATE, int(A_VOICE_RMS * math.sqrt(2)), period=97), SAMPLE_RATE, FRAME_MS)
    leg = leg_on(store, call, judging.Behavior(interferer_db=15.0), television)
    before = rms_of(b"".join(leg.next_frame() for _ in range(A_SECOND_IN_FRAMES)))
    leg.waiting.extend(voice)
    under_the_voice = [difference(leg.next_frame(), frame) for frame in voice]
    after = rms_of(b"".join(leg.next_frame() for _ in range(A_SECOND_IN_FRAMES)))
    assert abs(20 * math.log10(rms_of(b"".join(under_the_voice)) / before)) < WITHIN_THE_ROUNDING_DB
    assert abs(20 * math.log10(after / before)) < WITHIN_THE_ROUNDING_DB


# What a line loses is lost on its network, packet by packet (`kit.link`): the track is never silenced
# to stand for it, as it was until 2026-11-17.
@needs_the_database
async def test_a_line_that_loses_packets_still_carries_every_frame_of_its_track(store: Store, call: str) -> None:
    television = tone_of(SAMPLE_RATE, 6000, period=31)
    leg = leg_on(store, call, judging.Behavior(interferer_db=15.0, packet_loss=0.5), television)
    frames = [leg.next_frame() for _ in range(A_SECOND_IN_FRAMES)]
    assert {len(frame) for frame in frames} == {len(SILENCE)}
    assert SILENCE not in frames


# The line is carried at the clock's rate into a real source: a line is said once its last frame left.
@needs_the_database
async def test_a_line_is_said_once_its_last_frame_has_left_and_is_kept_with_when(store: Store, call: str) -> None:
    television = tone_of(SAMPLE_RATE, 6000, period=31)
    leg = leg_on(store, call, judging.Behavior(interferer_db=15.0), television)
    leg.open()
    try:
        await asyncio.wait_for(leg.say("Esa me viene bien."), 5.0)
        carried = leg.carried
        await asyncio.sleep(0.05)
    finally:
        await leg.close()
    assert not leg.waiting
    assert leg.carried > carried > 0, "the room is carried before the line, under it and after it"
    (kept,) = leg.spoke
    assert (kept.kind, kept.text, kept.cut_in) == ("line", "Esa me viene bien.", False)
    assert kept.began_at <= kept.ended_at


# G B2 (2026-10-23): a caller that cut in asked for its line only then, and paused before it as before any
# line, so the answer it meant to talk over was over by the time it spoke.
@needs_the_database
@pytest.mark.timeout(30)
async def test_a_caller_that_cuts_in_asks_for_its_line_as_the_agent_begins_and_says_it_with_no_pause(
    store: Store, call: str, agent: str
) -> None:
    # A caller that talks over every answer, and thinks ten seconds before any line it does not cut in with.
    leg = leg_on(store, call, judging.Behavior(interrupts=1.0, pause_s=10.0))
    await store.write("entry", call, agent, "agent.state", {"state": "speaking"})
    leg.open()
    try:
        asked: list[bool] = []
        assert await asyncio.wait_for(leg.wait_for_answer(1, lambda: asked.append(True)), 10.0) is True
        assert asked == [True]
        await asyncio.wait_for(leg.say("wait, the Tuesday one"), 5.0)
    finally:
        await leg.close()
    # What it said is kept with when, and that it meant to talk over the agent: the hearing is measured against it.
    (kept,) = leg.spoke
    assert (kept.kind, kept.text, kept.cut_in) == ("line", "wait, the Tuesday one", True)
    assert kept.began_at <= kept.ended_at


# ── how the line kept to the clock ──


# 2026-11-25: nineteen callers on one loop, and each one's room heard twenty to a hundred milliseconds
# of nothing inside its words, dozens of times a minute. The leg knows when it happens: it hands the
# room ten milliseconds a hundred times a second, a tenth of a second ahead, and a frame handed after
# the one before it ran out found the room with nothing to play.
def test_a_line_that_keeps_to_the_clock_hands_no_frame_late() -> None:
    pace = Pace()
    # The first frames are handed at once (the room takes a tenth of a second ahead), then one each ten milliseconds.
    for frame in range(300):
        pace.hand(100.0 + max(0, frame - 10) * 0.010)
    assert pace.dump() == {
        "frames": 300,
        "late_frames": 0,
        "late_ms": 0.0,
        "worst_ms": 0.0,
        "speech_frames": 0,
        "breaks_in_speech": 0,
    }


def test_a_loop_that_stalls_past_what_the_room_holds_is_counted_once_for_each_time_the_room_ran_out() -> None:
    pace = Pace()
    for frame in range(100):
        pace.hand(100.0 + frame * 0.010)
    # The loop is away 150 ms: the room had the frame's ten milliseconds, and heard nothing for the rest.
    pace.hand(100.99 + 0.150)
    # It goes on from there, on time again: the stall is one gap, not every frame after it.
    for frame in range(1, 100):
        pace.hand(100.99 + 0.150 + frame * 0.010)
    kept = pace.dump()
    assert (kept["frames"], kept["late_frames"]) == (200, 1)
    assert kept["late_ms"] == kept["worst_ms"] == 140.0


def test_a_break_inside_the_callers_lines_is_counted_apart_from_lateness_in_its_silence() -> None:
    """A listener hears the voice break when the room runs out in the middle of a line, for 20 ms or more."""
    pace = Pace()
    for frame in range(100):
        pace.hand(100.0 + frame * 0.010, speaking=True)
    # Away 50 ms while it speaks: a break the listener hears. Away 50 ms again while it says nothing: no break.
    pace.hand(100.99 + 0.050, speaking=True)
    for frame in range(1, 50):
        pace.hand(100.99 + 0.050 + frame * 0.010, speaking=True)
    pace.hand(101.53 + 0.050 + 0.050, speaking=False)
    kept = pace.dump()
    assert (kept["speech_frames"], kept["breaks_in_speech"], kept["late_frames"]) == (150, 1, 2)


def test_a_frame_a_moment_late_is_nothing_the_room_hears() -> None:
    pace = Pace()
    for frame in range(100):
        pace.hand(100.0 + frame * 0.010 + (0.003 if frame == 50 else 0.0))
    assert pace.dump()["late_frames"] == 0
