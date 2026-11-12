"""The hold melody: one for whatever overlaps, played after its grace once the agent is quiet, and when it sounded."""

import asyncio
from pathlib import Path

from runtime.session.hold import HoldMusic
from tests.fakes.livekit import Player
from tests.fakes.livekit import Room as AnOfflineRoom

A_MOMENT_S = 0.01


async def playing(after_s: float | None = A_MOMENT_S) -> tuple[HoldMusic, Player]:
    """A melody in a call's room, started on a player that publishes nothing, after this wait."""
    player = Player()
    melody = HoldMusic(Path("hold.ogg"), AnOfflineRoom("call_1"), player, after_s)
    await melody.start()
    return melody, player


async def test_tools_side_by_side_share_one_melody_until_the_last_ends() -> None:
    melody, _ = await playing()
    melody.begin()
    melody.begin()
    melody.end()
    assert melody.running == 1
    melody.end()
    assert melody.running == 0


async def test_a_tool_that_takes_a_while_plays_the_melody_looped_and_stops_it_after() -> None:
    melody, player = await playing()
    melody.begin()
    await asyncio.sleep(0.05)
    assert player.played == [("hold.ogg", True)]
    melody.end()
    assert player.handles[0].done()


async def test_the_melody_keeps_when_it_sounded_for_the_recording_and_nothing_inside_the_grace() -> None:
    melody, _ = await playing()
    melody.begin()
    melody.end()
    assert melody.played == []
    melody.begin()
    await asyncio.sleep(0.05)
    melody.end()
    ((start, end),) = melody.played
    assert 0 < end - start < 1


async def test_a_melody_still_playing_when_the_call_ends_counts_up_to_now() -> None:
    melody, _ = await playing()
    melody.begin()
    await asyncio.sleep(0.05)
    assert melody.played == []
    ((start, end),) = melody.sounded
    assert 0 < end - start < 1


async def test_the_melody_waits_for_the_agent_to_stop_talking() -> None:
    melody, player = await playing()
    melody.floor(speaking=True)
    melody.begin()
    await asyncio.sleep(0.05)
    assert player.played == []
    melody.floor(speaking=False)
    await asyncio.sleep(0.05)
    assert player.played == [("hold.ogg", True)]
    melody.end()


async def test_a_melody_waits_the_orgs_own_wait_and_plays_nothing_inside_it() -> None:
    patient, player = await playing(after_s=5.0)
    patient.begin()
    await asyncio.sleep(0.05)
    assert player.played == []
    patient.end()


async def test_a_player_that_did_not_start_plays_nothing() -> None:
    melody = HoldMusic(Path("hold.ogg"), AnOfflineRoom("call_1"), Player(), A_MOMENT_S)
    melody.begin()
    await asyncio.sleep(0.05)
    assert melody.played == [] and melody.sounded == []
    melody.end()


async def test_the_grace_outlasts_the_line_the_agent_says_before_the_tool() -> None:
    melody, player = await playing(after_s=0.05)
    melody.begin()
    await asyncio.sleep(0.01)
    melody.floor(speaking=True)
    await asyncio.sleep(0.08)
    assert player.played == []
    melody.end()
    assert (melody.running, melody.pending, melody.handle) == (0, None, None)
