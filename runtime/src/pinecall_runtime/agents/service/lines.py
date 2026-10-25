"""An agent's lines recorded once in its own voice: the MP3, and when each written word is said."""

import asyncio
import hashlib
import json
import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from pinecall_runtime.agents.models import AgentLine
from pinecall_runtime.agents.repository import AgentLineRepository
from pinecall_runtime.enums import Env
from pinecall_runtime.exceptions import NotFound
from pinecall_runtime.kit.mp3 import mp3_of
from pinecall_runtime.providers import service as providers

# Mono MP3 at 48 kbps plays in every browser, Safari's too: about 6 KB a second.
BIT_RATE = 48_000
# In the hash: an encoding changed is every line recorded again.
FORMAT = "mp3-48k-1"
# What one request may record, so an app's mistake costs the vendor little: a recording writes
# no usage row, as a voice sample writes none.
MOST_LINES = 64
LONGEST_LINE = 600
AT_ONCE = 4

NO_LINE = "no line {id} is recorded here"


@dataclass(frozen=True, slots=True)
class Group:
    """Written words the lexicon touches as one, and how the voice is told to say them."""

    written: tuple[str, ...]
    spoken: str


def voice_of(running: providers.Running) -> str:
    """The voice a line is recorded in, as a person reads it: `cartesia sonic-3 f786b574…`."""
    return " ".join(part for part in (running.vendor, running.model, running.voice) if part)


def line_id(running: providers.Running, says: Mapping[str, str], text: str) -> str:
    """The hash a line is kept under: the voice, the lexicon's forms the text holds, the encoding, the text."""
    touched = {written: spoken for written, spoken in says.items() if written.lower() in text.lower()}
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
    return hashlib.sha256(json.dumps(kept, sort_keys=True, default=str).encode()).hexdigest()


# Matched as livekit's own replace matches in a call: the longest form first, in any case, inside a
# word too. A form that spans words makes them one group, whose words share its time.
def groups_of(text: str, says: Mapping[str, str]) -> list[Group]:
    """The line's written words, grouped where a lexicon form touches them, each group as it is said."""
    tokens = list(re.finditer(r"\S+", text))
    spoken = {written.lower(): form for written, form in says.items() if written}
    if not spoken:
        return [Group(written=(token.group(),), spoken=token.group()) for token in tokens]
    pattern = re.compile("|".join(re.escape(key) for key in sorted(spoken, key=len, reverse=True)), re.IGNORECASE)
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


def words_of(groups: Sequence[Group], timed: Sequence[providers.TimedWord], duration_ms: int) -> tuple[list[Any], bool]:
    """Each written word with its start and end in ms: the voice's times where they line up, else spread by length."""
    counts = [len(group.spoken.split()) for group in groups]
    if timed and sum(counts) == len(timed):
        words: list[Any] = []
        at = 0
        for group, count in zip(groups, counts, strict=True):
            said = timed[at : at + count]
            at += count
            start = round(said[0].start_s * 1000) if said else (words[-1]["end_ms"] if words else 0)
            end = round(said[-1].end_s * 1000) if said else start
            words += [{"text": word, "start_ms": start, "end_ms": end} for word in group.written]
        return words, True
    written = [word for group in groups for word in group.written]
    total = sum(len(word) + 1 for word in written) or 1
    spread: list[Any] = []
    passed = 0
    for word in written:
        start = round(duration_ms * passed / total)
        passed += len(word) + 1
        spread.append({"text": word, "start_ms": start, "end_ms": round(duration_ms * passed / total)})
    return spread, False


async def record_lines(
    session: AsyncSession,
    *,
    org: str,
    env: Env,
    agent: str,
    texts: Sequence[str],
    running: providers.Running,
    says: Mapping[str, str],
) -> list[AgentLine]:
    """Each text as a line in the agent's voice, in order: the ones recorded before as they were, the rest now."""
    ids = [line_id(running, says, text) for text in texts]
    repository = AgentLineRepository(session)
    kept = await repository.get_many(org, env, agent, ids)
    missing = {id_: text for id_, text in zip(ids, texts, strict=True) if id_ not in kept}
    gate = asyncio.Semaphore(AT_ONCE)

    async def recorded(id_: str, text: str) -> AgentLine:
        async with gate:
            return await _recorded(id_, text, running, says, org=org, env=env, agent=agent)

    fresh = await asyncio.gather(*(recorded(id_, text) for id_, text in missing.items()))
    if fresh:
        await repository.add_all(fresh)
    kept.update({row.id: row for row in fresh})
    return [kept[id_] for id_ in ids]


async def get_line(session: AsyncSession, id_: str) -> AgentLine:
    """A recorded line by its id; NotFound for one never recorded."""
    row = await AgentLineRepository(session).get_audio(id_)
    if row is None:
        raise NotFound(NO_LINE.format(id=id_))
    return row


async def _recorded(
    id_: str, text: str, running: providers.Running, says: Mapping[str, str], *, org: str, env: Env, agent: str
) -> AgentLine:
    groups = groups_of(text, says)
    spoken = await providers.speak(running, " ".join(group.spoken for group in groups))
    frames = len(spoken.pcm) // (2 * max(spoken.channels, 1))
    duration_ms = round(frames * 1000 / spoken.rate) if spoken.rate else 0
    audio = await asyncio.to_thread(mp3_of, spoken.pcm, rate=spoken.rate, channels=spoken.channels, bit_rate=BIT_RATE)
    words, timed = words_of(groups, spoken.words, duration_ms)
    return AgentLine(
        org=org,
        env=env,
        agent=agent,
        id=id_,
        text=text,
        voice=voice_of(running),
        audio=audio,
        duration_ms=duration_ms,
        words=words,
        timed=timed,
    )
