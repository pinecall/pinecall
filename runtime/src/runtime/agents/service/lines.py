"""An agent's lines recorded once in its own voice: the MP3, and when each written word is said."""

import asyncio
import dataclasses
import json
import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from runtime.actor import Scope
from runtime.agents.models import AgentLine
from runtime.agents.repository import AgentLineRepository
from runtime.agents.service.declaration import agent_of
from runtime.agents.service.settings import resolve_for_call
from runtime.exceptions import NotFound
from runtime.kit.crypto import Vault
from runtime.kit.mp3 import mp3_of
from runtime.kit.text import sha256_of
from runtime.kit.time import now
from runtime.kit.words import holds, pattern_of
from runtime.providers import service as providers
from runtime.providers.stage import Running

# Mono MP3 at 48 kbps plays in every browser, Safari's too: about 6 KB a second.
BIT_RATE = 48_000
# In the hash: an encoding changed is every line recorded again.
FORMAT = "mp3-48k-1"
# What one request may record, so an app's mistake costs the vendor little: a recording writes
# no usage row, as a voice sample writes none.
MOST_LINES = 64
LONGEST_LINE = 600
AT_ONCE = 4

A_LINES_PATH = "/v1/lines/{id}.mp3"


@dataclass(frozen=True, slots=True)
class Group:
    """Written words the lexicon touches as one, and how the voice is told to say them."""

    written: tuple[str, ...]
    spoken: str


@dataclass(frozen=True, slots=True)
class Word:
    """A written word of a line, and when it is said, in ms from the start of the audio."""

    text: str
    start_ms: int
    end_ms: int


@dataclass(frozen=True, slots=True)
class Line:
    """A line recorded in the agent's voice: where its MP3 is read, how long it runs, when each word is said."""

    id: str
    text: str
    url: str
    duration_ms: int
    voice: str
    # False where the voice times no words and each word was placed by its length.
    timed: bool
    words: tuple[Word, ...]


def voice_of(running: Running) -> str:
    """The voice a line is recorded in, as a person reads it: `cartesia sonic-3 f786b574…`."""
    return " ".join(part for part in (running.vendor, running.model, running.voice) if part)


def line_id(running: Running, says: Mapping[str, str], text: str) -> str:
    """The hash a line is kept under: the voice, the lexicon's forms the text holds, the encoding, the text."""
    touched = {written: spoken for written, spoken in says.items() if holds(text, written)}
    kept = {
        "vendor": running.vendor,
        "model": running.model,
        "builds": running.builds,
        "options": dict(running.options),
        "voice": running.voice,
        "language": running.language,
        "says": touched,
        "format": FORMAT,
        "text": text,
    }
    return sha256_of(json.dumps(kept, sort_keys=True, default=str))


# Found as a call's voice finds them (kit.words): the longest form first, in any case, as a whole word.
# A form that spans words makes them one group, whose words share its time.
def groups_of(text: str, says: Mapping[str, str]) -> list[Group]:
    """The line's written words, grouped where a lexicon form touches them, each group as it is said."""
    tokens = list(re.finditer(r"\S+", text))
    spoken = {written.lower(): form for written, form in says.items() if written}
    pattern = pattern_of(says)
    if pattern is None:
        return [Group(written=(token.group(),), spoken=token.group()) for token in tokens]
    matches = list(pattern.finditer(text))
    groups: list[Group] = []
    at = 0
    while at < len(tokens):
        start, end, last = tokens[at].start(), tokens[at].end(), at
        reaching = True
        while reaching:
            reaching = False
            for match in matches:
                if match.start() < end and match.end() > end:
                    end, reaching = match.end(), True
            while last + 1 < len(tokens) and tokens[last + 1].start() < end:
                last += 1
                end = max(end, tokens[last].end())
        said = pattern.sub(lambda found: spoken[found.group(0).lower()], text[start:end])
        groups.append(Group(written=tuple(token.group() for token in tokens[at : last + 1]), spoken=said))
        at = last + 1
    return groups


def words_of(
    groups: Sequence[Group], timed: Sequence[providers.TimedWord], duration_ms: int
) -> tuple[list[Word], bool]:
    """Each written word with its start and end in ms: the voice's times where they line up, else spread by length."""
    counts = [len(group.spoken.split()) for group in groups]
    if timed and sum(counts) == len(timed):
        words: list[Word] = []
        at = 0
        for group, count in zip(groups, counts, strict=True):
            said = timed[at : at + count]
            at += count
            start = round(said[0].start_s * 1000) if said else (words[-1].end_ms if words else 0)
            end = round(said[-1].end_s * 1000) if said else start
            words += [Word(word, start, end) for word in group.written]
        return words, True
    written = [word for group in groups for word in group.written]
    total = sum(len(word) + 1 for word in written) or 1
    spread: list[Word] = []
    passed = 0
    for word in written:
        start = round(duration_ms * passed / total)
        passed += len(word) + 1
        spread.append(Word(word, start, round(duration_ms * passed / total)))
    return spread, False


# Recorded with the voice the agent's next call in this env would speak with: its settings over its
# class, the providers row, and the org's keys or the box's lent ones.
#
# Three steps, and no connection held while the vendor speaks. Until 2026-11 up to sixty-four lines
# were synthesized inside the request's transaction, four at a time: past the minute Postgres gives an
# idle transaction the insert failed, and the recordings already paid for were lost. What was recorded
# is kept even when a later line fails, and the failure is then said.
async def record_lines(
    sessions: async_sessionmaker[AsyncSession], vault: Vault, scope: Scope, slug: str, texts: Sequence[str], base: str
) -> list[Line]:
    """Each text as a line in the agent's voice, in order: the ones recorded before as they were, the rest now."""
    async with sessions.begin() as session:
        agent = await agent_of(session, scope, slug)
        catalog = await providers.get_catalog(session)
        resolved = (await resolve_for_call(session, agent.whole, scope, catalog)).declaration
        keys = await providers.keys_of(session, vault, scope)
        running = providers.build_pipeline(resolved, catalog, keys).tts
        ids = [line_id(running, resolved.says, text) for text in texts]
        recorded = await AgentLineRepository(session).list_recorded(scope.org, scope.env, slug, ids)
        kept = {row.id: _line_of(row, base) for row in recorded}
    missing = {id_: text for id_, text in zip(ids, texts, strict=True) if id_ not in kept}
    gate = asyncio.Semaphore(AT_ONCE)

    async def record(id_: str, text: str) -> dict[str, Any]:
        async with gate:
            return await _record(id_, text, running, resolved.says, scope, slug)

    made = await asyncio.gather(*(record(id_, text) for id_, text in missing.items()), return_exceptions=True)
    fresh = [one for one in made if not isinstance(one, BaseException)]
    async with sessions.begin() as session:
        await AgentLineRepository(session).add_missing(fresh)
    for failed in made:
        if isinstance(failed, BaseException):
            raise failed
    kept.update({one["id"]: _line_of_columns(one, base) for one in fresh})
    return [kept[id_] for id_ in ids]


async def get_audio(session: AsyncSession, id_: str) -> bytes:
    """A recorded line's MP3 by its id; NotFound for one never recorded."""
    audio = await AgentLineRepository(session).find_audio(id_)
    if audio is None:
        raise NotFound(f"no line {id_} is recorded here")
    return audio


# ── private ──


async def _record(
    id_: str, text: str, running: Running, says: Mapping[str, str], scope: Scope, slug: str
) -> dict[str, Any]:
    groups = groups_of(text, says)
    spoken = await providers.speak(running, " ".join(group.spoken for group in groups))
    frames = len(spoken.pcm) // (2 * max(spoken.channels, 1))
    duration_ms = round(frames * 1000 / spoken.rate) if spoken.rate else 0
    audio = await asyncio.to_thread(mp3_of, spoken.pcm, rate=spoken.rate, channels=spoken.channels, bit_rate=BIT_RATE)
    words, timed = words_of(groups, spoken.words, duration_ms)
    return {
        "org": scope.org,
        "env": scope.env,
        "agent": slug,
        "id": id_,
        "text": text,
        "voice": voice_of(running),
        "audio": audio,
        "duration_ms": duration_ms,
        "words": [dataclasses.asdict(word) for word in words],
        "timed": timed,
        "recorded_at": now(),
    }


def _line_of(row: AgentLine, base: str) -> Line:
    return Line(
        id=row.id,
        text=row.text,
        url=f"{base}{A_LINES_PATH.format(id=row.id)}",
        duration_ms=row.duration_ms,
        voice=row.voice,
        timed=row.timed,
        words=tuple(Word(word["text"], word["start_ms"], word["end_ms"]) for word in row.words),
    )


def _line_of_columns(columns: Mapping[str, Any], base: str) -> Line:
    return Line(
        id=columns["id"],
        text=columns["text"],
        url=f"{base}{A_LINES_PATH.format(id=columns['id'])}",
        duration_ms=columns["duration_ms"],
        voice=columns["voice"],
        timed=columns["timed"],
        words=tuple(Word(**word) for word in columns["words"]),
    )
