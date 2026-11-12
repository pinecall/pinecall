"""The hold melody: what a caller hears while a tool runs (the class's word, the org's, the runtime's), and its clip."""

import asyncio
from dataclasses import dataclass, replace
from pathlib import Path
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from runtime.actor import Scope
from runtime.agents.declaration import Agent
from runtime.agents.models import HoldAudio
from runtime.agents.repository import HoldAudioRepository
from runtime.agents.service.setting_names import refuse_what_the_class_sets
from runtime.enums import HoldPlayed
from runtime.exceptions import Conflict, NotFound, ValidationError
from runtime.kit.opus import RunsLonger, encode_upload
from runtime.kit.text import sha256_of
from runtime.wire.declaration import HoldConfig
from runtime.wire.worker import HOLD_AFTER_S

# The org's own wait is held between these two; unset, the runtime's (`HOLD_AFTER_S`).
SOONEST_AFTER_S = 0.0
LATEST_AFTER_S = 30.0
# The melody loops, so a long file only costs storage, and a very short one stutters.
LONGEST_S = 300
SHORTEST_S = 1
# The whole file in one request; a five-minute mp3 is under 10 MB.
LONGEST_UPLOAD = 20 * 1024 * 1024
A_MELODY = "melody"
# What a row holds of a clip, forgotten together when the org chooses the runtime's melody or silence.
_NO_CLIP: dict[str, Any] = {"audio": None, "sha256": None, "source_sha256": None, "seconds": None, "name": None}

TOO_LONG = f"a hold melody loops, so {LONGEST_S // 60} minutes at most: this one runs longer"
TOO_SHORT = f"a hold melody of less than {SHORTEST_S} second would stutter as it loops"
AFTER_OUT_OF_RANGE = (
    "after_s {after:g}: the melody starts after {soonest:g} to {latest:g} seconds of quiet, or null for the runtime's"
)
NOT_THE_CLASSS_FILE = (
    "{slug} takes no melody here: this endpoint takes the file its class declares as `hold`, by the hash it "
    "declared, from the process that holds the agent; a file of the org's goes through PUT …/pipeline/hold-audio"
)
NO_CLIP = "agent {slug} plays no clip of its own"
OFF = "agent {slug} plays nothing while a tool runs: its melody is off"


# Until 2026-11 this precedence was a classmethod of the response's schema, and the store was the widget's.
@dataclass(frozen=True, slots=True)
class Hold:
    """What a caller hears while a tool runs, and after how long: the runtime's melody, silence, or the org's clip."""

    played: HoldPlayed = HoldPlayed.default
    sha256: str | None = None
    # The hash of the clip as it was uploaded, before conversion: what a class that ships it says.
    source_sha256: str | None = None
    seconds: float | None = None
    name: str | None = None
    # The wait that plays: the class's, else the org's, else the runtime's.
    after_s: float = HOLD_AFTER_S
    # True when the agent's class declares its melody: nothing is written but the class's own file.
    fixed: bool = False


def hold_of(row: HoldAudio | None, of_the_class: HoldConfig | None = None) -> Hold:
    """What the agent plays, from its row and its class; the runtime's melody after its wait when neither says."""
    read = Hold()
    if row is not None:
        read = Hold(
            played=row.played,
            sha256=row.sha256,
            source_sha256=row.source_sha256,
            seconds=row.seconds,
            name=row.name,
            after_s=HOLD_AFTER_S if row.after_s is None else row.after_s,
        )
    if of_the_class is None:
        return read
    # The class's wait and its silence win; its clip is the row's once its process uploaded it.
    unsilenced = HoldPlayed.default if read.played is HoldPlayed.off else read.played
    return replace(
        read,
        played=HoldPlayed.off if of_the_class.off else unsilenced,
        after_s=read.after_s if of_the_class.after_s is None else of_the_class.after_s,
        fixed=True,
    )


def check_wait(after_s: float) -> None:
    """Refuse a wait outside the band the melody starts in."""
    if not SOONEST_AFTER_S <= after_s <= LATEST_AFTER_S:
        raise ValidationError(AFTER_OUT_OF_RANGE.format(after=after_s, soonest=SOONEST_AFTER_S, latest=LATEST_AFTER_S))


# ── reading ──


# The melody is the agent's in an env, whoever holds it.
async def get_hold(session: AsyncSession, scope: Scope, agent: Agent) -> Hold:
    """What the agent plays while a tool runs in the env, and after how long."""
    row = await HoldAudioRepository(session).find(scope.org, scope.env, agent.slug)
    return hold_of(row, _its_class_holds(agent))


async def get_clip(session: AsyncSession, scope: Scope, slug: str) -> bytes:
    """The agent's own clip, Ogg Opus; NotFound when it plays none of its own."""
    audio = await HoldAudioRepository(session).find_clip(scope.org, scope.env, slug)
    if audio is None:
        raise NotFound(NO_CLIP.format(slug=slug))
    return audio


# The runtime's own melody is the file livekit ships, read by whoever owns the worker's side of it
# and handed in: this domain names no library of a vendor's.
async def get_heard_clip(session: AsyncSession, scope: Scope, slug: str, *, runtime_melody: Path) -> bytes:
    """What a person hears of the agent's melody before a caller does: its clip, else the runtime's; none when off."""
    repository = HoldAudioRepository(session)
    audio = await repository.find_clip(scope.org, scope.env, slug)
    if audio is not None:
        return audio
    row = await repository.find(scope.org, scope.env, slug)
    if row is None or row.played is HoldPlayed.default:
        return await asyncio.to_thread(runtime_melody.read_bytes)
    raise NotFound(OFF.format(slug=slug))


# ── writing ──


# Converted here, once, so no worker decodes a tenant's upload in the middle of a call. An agent whose
# class declares its melody takes no file of the org's: the class ships its own, through `ship_clip`.
async def put_clip(session: AsyncSession, scope: Scope, agent: Agent, data: bytes, name: str | None) -> Hold:
    """A file of the org's as the agent's melody, from the next call on; refused while its class declares the melody."""
    refuse_what_the_class_sets(agent, ["hold"])
    return hold_of(await _keep_clip(session, scope, agent.slug, data, name))


# The class's own melody comes in on the app's key: only the file the class declared, by its hash, and
# nothing for an agent whose class declares none.
async def ship_clip(session: AsyncSession, scope: Scope, agent: Agent, data: bytes, name: str | None) -> Hold:
    """The file the agent's class declares as its melody, uploaded by the process that holds it."""
    of_the_class = _its_class_holds(agent)
    if of_the_class is None or of_the_class.clip != sha256_of(data):
        raise Conflict(NOT_THE_CLASSS_FILE.format(slug=agent.slug))
    return hold_of(await _keep_clip(session, scope, agent.slug, data, name), of_the_class)


# Choosing what plays keeps the wait the org set: the two are set apart.
async def put_played(session: AsyncSession, scope: Scope, agent: Agent, played: HoldPlayed) -> Hold:
    """The runtime's melody back, or silence; an uploaded clip is forgotten either way, the wait kept."""
    refuse_what_the_class_sets(agent, ["hold"])
    chosen: dict[str, Any] = {"played": played, **_NO_CLIP}
    return hold_of(await HoldAudioRepository(session).put(scope.org, scope.env, agent.slug, chosen))


async def put_wait(session: AsyncSession, scope: Scope, agent: Agent, after_s: float | None) -> Hold:
    """How long the agent is quiet before its melody starts, from the next call on; None is the runtime's own wait."""
    refuse_what_the_class_sets(agent, ["hold"])
    if after_s is not None:
        check_wait(after_s)
    return hold_of(await HoldAudioRepository(session).put_wait(scope.org, scope.env, agent.slug, after_s))


# No foreign key reaches a melody from its org (`hold_audio.org` is text): the org's erasure calls this.
async def forget_melodies(session: AsyncSession, org: str) -> int:
    """Forget every melody of an org that is being erased; how many it had."""
    return await HoldAudioRepository(session).delete_of_org(org)


# ── private ──


def _its_class_holds(agent: Agent) -> HoldConfig | None:
    return None if agent.declaration is None else agent.declaration.hold


async def _keep_clip(session: AsyncSession, scope: Scope, slug: str, data: bytes, name: str | None) -> HoldAudio:
    try:
        melody = await asyncio.to_thread(encode_upload, data, longest_s=LONGEST_S)
    except RunsLonger as longer:
        raise ValidationError(TOO_LONG) from longer
    if melody.seconds < SHORTEST_S:
        raise ValidationError(TOO_SHORT)
    chosen = {
        "played": HoldPlayed.custom,
        "audio": melody.audio,
        "sha256": sha256_of(melody.audio),
        "source_sha256": sha256_of(data),
        "seconds": round(melody.seconds, 2),
        "name": (name or "").strip() or A_MELODY,
    }
    return await HoldAudioRepository(session).put(scope.org, scope.env, slug, chosen)
