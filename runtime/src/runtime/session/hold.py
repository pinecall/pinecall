"""The hold melody: the clip played while a tool runs or the line is held, after its grace, and when it sounded."""

import asyncio
import logging
import time
from pathlib import Path

from livekit import rtc
from livekit.agents.voice.background_audio import AudioConfig, BackgroundAudioPlayer, BuiltinAudioClip, PlayHandle

from runtime.wire.worker import HOLD_AFTER_S

logger = logging.getLogger(__name__)

# The hold melody sits under the agent's voice, since a phone leg has no volume of its own. A
# tool that answers inside the grace plays nothing; the grace is the org's, else the runtime's.
VOLUME = 0.6
GRACE_S = HOLD_AFTER_S
FADE_IN_S = 0.4
FADE_OUT_S = 0.3


class HoldMusic:
    """The melody played while a tool runs or the line is held, shared by what overlaps."""

    def __init__(self, clip: Path, room: rtc.Room, after_s: float | None = None) -> None:
        """A melody for the call's room, not yet published, that starts after that many seconds of quiet."""
        self.clip = clip
        self.room = room
        self.after_s = after_s
        self.player: BackgroundAudioPlayer | None = None
        self.handle: PlayHandle | None = None
        self.running = 0
        self.pending: asyncio.Task[None] | None = None
        self.quiet = asyncio.Event()
        self.quiet.set()
        # When it sounded, by the clock, for the call's recording to lay it in: the player's track
        # is the room's, not the session's, and the clip is already on this disk.
        self.played: list[tuple[float, float]] = []
        self.playing_since: float | None = None

    # The player publishes its own track, which the SIP bridge mixes into the phone leg. A
    # player that does not start leaves the call without a melody, and nothing else.
    async def start(self) -> None:
        """Publish the melody's track in the room."""
        player = BackgroundAudioPlayer()
        try:
            await player.start(room=self.room)  # pyright: ignore[reportUnknownMemberType]
        except (RuntimeError, ConnectionError):
            logger.warning("the hold melody did not start: the call goes on without it", exc_info=True)
            return
        self.player = player

    def floor(self, *, speaking: bool) -> None:
        """Whether the agent is speaking, as the session says."""
        if speaking:
            self.quiet.clear()
        else:
            self.quiet.set()

    def begin(self) -> None:
        """One more reason to play; the first starts the melody after the grace."""
        self.running += 1
        if self.running == 1 and self.player is not None:
            self.pending = asyncio.create_task(self._play_after_the_grace())

    def end(self) -> None:
        """One reason less; the last stops the melody."""
        self.running = max(self.running - 1, 0)
        if self.running == 0:
            self._stop()

    # Nothing stops the melody when the caller hangs up on hold: the player goes with the room.
    @property
    def sounded(self) -> list[tuple[float, float]]:
        """When the melody played, by the clock; the one still playing counted up to now."""
        if self.playing_since is None:
            return self.played
        return [*self.played, (self.playing_since, time.time())]

    async def aclose(self) -> None:
        """Stop and close the player."""
        self._stop()
        player, self.player = self.player, None
        if player is not None:
            await player.aclose()

    # The tool starts while its announcement still plays, so the grace counts from when the agent
    # is quiet; checked again after it, since livekit may speak another round's preamble.
    async def _play_after_the_grace(self) -> None:
        await self.quiet.wait()
        await asyncio.sleep(GRACE_S if self.after_s is None else self.after_s)
        if self.running == 0 or not self.quiet.is_set() or self.player is None:
            return
        melody = AudioConfig(str(self.clip), volume=VOLUME, fade_in=FADE_IN_S, fade_out=FADE_OUT_S)
        self.handle = self.player.play(melody, loop=True)
        self.playing_since = time.time()

    def _stop(self) -> None:
        if self.pending is not None and not self.pending.done():
            self.pending.cancel()
        self.pending = None
        if self.handle is not None:
            self.handle.stop()
            self.handle = None
        if self.playing_since is not None:
            self.played.append((self.playing_since, time.time()))
            self.playing_since = None


# The file livekit ships: what an agent with no clip of its own plays, and what a person hears of
# it in the console before a caller does.
def runtime_melody() -> Path:
    """The runtime's own hold melody, on this disk."""
    return Path(BuiltinAudioClip.HOLD_MUSIC.path())
