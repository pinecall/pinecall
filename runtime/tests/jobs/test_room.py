"""The melody a worker builds for a call: the runtime's from livekit's clip, or none, after the wait it read."""

from pathlib import Path
from typing import override

from pinecall_runtime.agents.service import HoldAudio
from pinecall_runtime.enums import Env, HoldPlayed
from pinecall_runtime.jobs.service.client import GatewayClient
from pinecall_runtime.jobs.service.room import hold_music_for
from pinecall_runtime.kit.auth import Scope

SCOPE = Scope("org_test", Env.sandbox, "")


class NoGateway(GatewayClient):
    """A gateway never reached: the runtime's melody and silence fetch nothing."""

    def __init__(self) -> None:
        """Nothing to connect to."""

    @override
    async def hold_clip(self, slug: str, scope: Scope) -> bytes:
        """Never asked."""
        raise AssertionError(f"the clip of {slug} was fetched")


async def test_the_runtimes_melody_is_livekits_clip_on_this_disk_after_the_wait_read() -> None:
    held = HoldAudio(played=HoldPlayed.default, after_s=0.8)
    melody = await hold_music_for(NoGateway(), "front-desk", SCOPE, held, typed=False)
    assert melody is not None
    assert melody.clip.name == "hold_music.ogg" and Path(melody.clip).is_file()
    assert melody.after_s == 0.8


async def test_silence_and_a_written_call_play_no_melody() -> None:
    off = await hold_music_for(NoGateway(), "front-desk", SCOPE, HoldAudio(played=HoldPlayed.off), typed=False)
    written = await hold_music_for(NoGateway(), "front-desk", SCOPE, HoldAudio(played=HoldPlayed.default), typed=True)
    assert off is None and written is None
