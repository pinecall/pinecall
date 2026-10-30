"""How the widget presents an agent, and what the agent plays while a tool runs."""

import asyncio
import hashlib
import re
from dataclasses import dataclass

from sqlalchemy.ext.asyncio import AsyncSession

from pinecall_runtime.agents.models import HoldAudio
from pinecall_runtime.agents.repository import HoldAudioRepository, WidgetRepository
from pinecall_runtime.agents.schemas import LATEST_AFTER_S, SOONEST_AFTER_S
from pinecall_runtime.agents.service import hold_audio
from pinecall_runtime.enums import Env, HoldPlayed
from pinecall_runtime.exceptions import ValidationError
from pinecall_runtime.kit.time import now
from pinecall_runtime.wire.parts import HoldConfig, WidgetLook, WidgetTheme

LONGEST = {"title": 80, "tagline": 160, "greeting": 500, "accent": 40}
AFTER_OUT_OF_RANGE = (
    "after_s {after:g}: the melody starts after {soonest:g} to {latest:g} seconds of quiet, or null for the runtime's"
)
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
    """An uploaded melody, already converted: its bytes, how long it lasts, the file's name, the upload's hash."""

    audio: bytes
    seconds: float
    name: str
    source_sha256: str


def look_of(declared: WidgetLook) -> Look:
    """The look as a class declares it, held to the widget's own rules."""
    return Look(
        title=declared.title,
        tagline=declared.tagline,
        greeting=declared.greeting,
        accent=declared.accent,
        autostart=declared.autostart,
        theme=declared.theme,
    )


def check_look(declared: WidgetLook | None) -> WidgetLook | None:
    """A declared look refused by sentence when a widget would refuse it; None stays None."""
    if declared is not None:
        look_of(declared)
    return declared


def check_hold(declared: HoldConfig | None) -> HoldConfig | None:
    """A declared melody refused when its wait is out of the band a PUT holds it to; None stays None."""
    if declared is not None and declared.after_s is not None:
        check_wait(declared.after_s)
    return declared


def check_wait(after_s: float) -> None:
    """Refuse a wait outside the band the melody starts in."""
    if not SOONEST_AFTER_S <= after_s <= LATEST_AFTER_S:
        raise ValidationError(AFTER_OUT_OF_RANGE.format(after=after_s, soonest=SOONEST_AFTER_S, latest=LATEST_AFTER_S))


async def get_look(session: AsyncSession, org: str, env: Env, agent: str, declared: WidgetLook | None = None) -> Look:
    """How the agent's widget looks in the env: its class's when declared, else the row's, else the defaults."""
    if declared is not None:
        return look_of(declared)
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
    """What the agent plays while a tool runs in the env; None is the runtime's melody after its own wait."""
    return await HoldAudioRepository(session).get(org, env, agent)


async def get_hold_clip(session: AsyncSession, org: str, env: Env, agent: str) -> bytes | None:
    """The agent's own clip, when it plays one."""
    row = await HoldAudioRepository(session).get(org, env, agent)
    return None if row is None or row.audio is None else bytes(row.audio)


async def hold_clip_heard(session: AsyncSession, org: str, env: Env, agent: str) -> bytes | None:
    """What a person hears of the agent's melody before a caller does: its own clip, the runtime's, or None when off."""
    row = await HoldAudioRepository(session).get(org, env, agent)
    if row is not None and row.audio is not None:
        return bytes(row.audio)
    if row is None or row.played is HoldPlayed.default:
        return await asyncio.to_thread(hold_audio.runtime_melody().read_bytes)
    return None


async def keep_hold_clip(session: AsyncSession, org: str, env: Env, agent: str, clip: Clip) -> HoldAudio:
    """Play this clip while the agent's tools run in the env."""
    return await HoldAudioRepository(session).put(
        org,
        env,
        agent,
        played=HoldPlayed.custom,
        audio=clip.audio,
        sha256=hashlib.sha256(clip.audio).hexdigest(),
        source_sha256=clip.source_sha256,
        seconds=clip.seconds,
        name=clip.name,
    )


# Choosing what plays keeps the wait the org set: the two are set apart.
async def silence_hold(session: AsyncSession, org: str, env: Env, agent: str) -> HoldAudio:
    """Play nothing while the agent's tools run; any clip is forgotten."""
    return await HoldAudioRepository(session).put(
        org, env, agent, played=HoldPlayed.off, audio=None, sha256=None, source_sha256=None, seconds=None, name=None
    )


async def forget_hold(session: AsyncSession, org: str, env: Env, agent: str) -> HoldAudio:
    """Play the runtime's own melody again; any clip is forgotten."""
    return await HoldAudioRepository(session).put(
        org, env, agent, played=HoldPlayed.default, audio=None, sha256=None, source_sha256=None, seconds=None, name=None
    )


async def wait_before_hold(session: AsyncSession, org: str, env: Env, agent: str, after_s: float | None) -> HoldAudio:
    """How long the agent is quiet before its melody starts; None is the runtime's own wait."""
    if after_s is not None:
        check_wait(after_s)
    repository = HoldAudioRepository(session)
    row = await repository.get(org, env, agent)
    if row is None:
        return await repository.put(org, env, agent, played=HoldPlayed.default, after_s=after_s)
    return await repository.update(row, set_at=now(), after_s=after_s)


def _theme(word: str | None) -> WidgetTheme | None:
    match word:
        case "auto" | "light" | "dark":
            return word
        case _:
            return None
