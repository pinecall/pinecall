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
    A_VOICE_RMS,
    FRAME_MS,
    MURMURS,
    SAMPLE_RATE,
    SILENCE,
    CallerLeg,
    Spoken,
    SpokenLevel,
    at_tempo,
    describe,
    pick_murmur,
    resample,
)
from runtime.judging import service as judging
from runtime.kit.pcm import QUIET, frames_of, mix_under, rms_of
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
    assert describe(judging.Behavior()) == "a clean line"
    assert describe(judging.Behavior(interferer_db=15.0)) == "television 15 dB under the caller"
    assert describe(judging.Behavior(interferer_db=22.0, packet_loss=0.02, ambience="cafe")) == (
        "cafe 22 dB under the caller, 2% packet loss"
    )


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


@needs_the_database
async def test_a_lost_packet_is_the_silence_a_jitter_buffer_plays_whoever_was_speaking(store: Store, call: str) -> None:
    television = tone_of(SAMPLE_RATE, 6000, period=31)
    leg = leg_on(store, call, judging.Behavior(interferer_db=15.0, packet_loss=0.5), television)
    frames = [leg.next_frame() for _ in range(A_SECOND_IN_FRAMES)]
    assert {len(frame) for frame in frames} == {len(SILENCE)}
    # Half of a hundred, by chance: outside 20 to 80 once in a billion runs.
    assert 20 < len([frame for frame in frames if frame == SILENCE]) < 80


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
