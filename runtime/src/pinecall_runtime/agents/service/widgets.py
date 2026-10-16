"""How the widget presents an agent, and what the agent plays while a tool runs."""

import hashlib
import re
from dataclasses import dataclass

from sqlalchemy.ext.asyncio import AsyncSession

from pinecall_runtime.agents.models import HoldAudio
from pinecall_runtime.agents.repository import HoldAudioRepository, WidgetRepository
from pinecall_runtime.enums import Env, HoldPlayed
from pinecall_runtime.exceptions import ValidationError
from pinecall_runtime.wire.parts import WidgetTheme

LONGEST = {"title": 80, "tagline": 160, "greeting": 500, "accent": 40}
# The widget sets the accent as a CSS variable: nothing that could end the declaration passes.
A_COLOUR = re.compile(r"^(#[0-9a-fA-F]{3,8}|[a-zA-Z]+|(rgb|rgba|hsl|hsla|oklch)\([0-9.,%\s/a-z-]+\))$")


@dataclass(frozen=True, slots=True)
class Look:
    """How the widget presents the agent; None is the widget's own default."""

    title: str | None = None
    tagline: str | None = None
    greeting: str | None = None
    accent: str | None = None
    autostart: bool = False
    theme: WidgetTheme | None = None

    def __post_init__(self) -> None:
        for name, longest in LONGEST.items():
            value = getattr(self, name)
            if value is not None and len(value) > longest:
                raise ValidationError(f"a widget's {name} is {longest} characters at most")
        if self.accent is not None and not A_COLOUR.match(self.accent):
            raise ValidationError(f"an accent is a CSS colour, not {self.accent!r}")


@dataclass(frozen=True, slots=True)
class Clip:
    """An uploaded melody, already converted: its bytes, how long it lasts, the file's name."""

    audio: bytes
    seconds: float
    name: str


async def get_look(session: AsyncSession, org: str, env: Env, agent: str) -> Look:
    """How the agent's widget looks in the env; the widget's defaults when nobody said."""
    row = await WidgetRepository(session).get(org, env, agent)
    if row is None:
        return Look()
    return Look(row.title, row.tagline, row.greeting, row.accent, row.autostart, _theme(row.theme))


async def put_look(session: AsyncSession, org: str, env: Env, agent: str, look: Look) -> None:
    """Replace how the agent's widget looks in the env."""
    await WidgetRepository(session).put(
        org,
        env,
        agent,
        title=look.title,
        tagline=look.tagline,
        greeting=look.greeting,
        accent=look.accent,
        autostart=look.autostart,
        theme=look.theme,
    )


async def get_hold_audio(session: AsyncSession, org: str, env: Env, agent: str) -> HoldAudio | None:
    """What the agent plays while a tool runs in the env; None is the box's melody."""
    return await HoldAudioRepository(session).get(org, env, agent)


async def get_hold_clip(session: AsyncSession, org: str, env: Env, agent: str) -> bytes | None:
    """The agent's own clip, when it plays one."""
    row = await HoldAudioRepository(session).get(org, env, agent)
    return None if row is None or row.audio is None else bytes(row.audio)


async def keep_hold_clip(session: AsyncSession, org: str, env: Env, agent: str, clip: Clip) -> HoldAudio:
    """Play this clip while the agent's tools run in the env."""
    return await HoldAudioRepository(session).put(
        org,
        env,
        agent,
        played=HoldPlayed.custom,
        audio=clip.audio,
        sha256=hashlib.sha256(clip.audio).hexdigest(),
        seconds=clip.seconds,
        name=clip.name,
    )


async def silence_hold(session: AsyncSession, org: str, env: Env, agent: str) -> None:
    """Play nothing while the agent's tools run; any clip is forgotten."""
    await HoldAudioRepository(session).put(
        org, env, agent, played=HoldPlayed.off, audio=None, sha256=None, seconds=None, name=None
    )


async def forget_hold(session: AsyncSession, org: str, env: Env, agent: str) -> None:
    """Play the box's own melody again; any clip is forgotten."""
    repository = HoldAudioRepository(session)
    row = await repository.get(org, env, agent)
    if row is not None:
        await repository.delete(row)


def _theme(word: str | None) -> WidgetTheme | None:
    match word:
        case "auto" | "light" | "dark":
            return word
        case _:
            return None
