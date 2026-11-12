"""A text a page shows, explained by the agent's model as notes, each on one line of it, in the agent's own words."""

import json
import re
from dataclasses import dataclass

from livekit.agents import llm
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from runtime.actor import Scope
from runtime.agents.service.declaration import agent_of
from runtime.agents.service.settings import resolve_for_call
from runtime.kit.crypto import Vault
from runtime.kit.text import a_list, a_mapping
from runtime.providers import service as providers
from runtime.providers.stage import Running, primary_language

# A page reads an output aloud with a finger on the line it talks about: the model picks the lines
# that matter and says one sentence of each. A note names its line by a fragment copied from it, so the
# page can light it; a fragment that is in no line is dropped, as is anything the model made up.
MOST_NOTES = 6
LONGEST_OUTPUT = 8000
LONGEST_SAY = 240
LANGUAGES = {"es": "Spanish", "en": "English", "pt": "Portuguese", "fr": "French", "de": "German", "it": "Italian"}
FALLBACK_LANGUAGE = "en"

INSTRUCTIONS = (
    "You are a guide reading a command's output aloud to a learner, a finger on the line you talk about. "
    "Answer with a JSON array alone, no prose and no fence: at most {most} objects, each "
    '{{"find": "...", "say": "..."}}. `find` is an exact fragment copied from ONE line of the output, as written, '
    "a few words that tell the line apart. `say` is one short spoken sentence in {language} saying what that line "
    "means to the learner: plain words, no markdown, no lists, numbers as they are said. Pick the lines that "
    "matter, a result, an error, a warning, a value, and skip the noise. Say nothing that is not in the output."
)
THE_OUTPUT = "The command: {command}\n\nIts output:\n{output}"
A_FENCE = re.compile(r"^\s*```(?:json)?\s*(.*?)\s*```\s*$", re.S)


@dataclass(frozen=True, slots=True)
class Note:
    """One line of the text, by a fragment of it, and what is said of it."""

    find: str
    say: str


@dataclass(frozen=True, slots=True)
class Asked:
    """What a page asks to have explained: a text it shows, the command that made it, in what language, how much."""

    output: str
    command: str = ""
    # The language the notes are said in; the agent's when left out.
    language: str | None = None
    most: int = 4


def notes_of(answer: str, output: str, most: int = MOST_NOTES) -> list[Note]:
    """The model's answer read as notes: each `find` in one line of the output, one a line, `most` at most."""
    fenced = A_FENCE.match(answer)
    try:
        decoded: object = json.loads(fenced.group(1) if fenced else answer)
    except ValueError:
        return []
    if not a_list(decoded):
        return []
    lines = [_flatten(line) for line in output.splitlines()]
    kept: list[Note] = []
    taken: set[int] = set()
    for item in decoded:
        if not a_mapping(item):
            continue
        find, say = item.get("find"), item.get("say")
        if not isinstance(find, str) or not isinstance(say, str) or not find.strip() or not say.strip():
            continue
        at = next((index for index, line in enumerate(lines) if _flatten(find) in line), None)
        if at is None or at in taken:
            continue
        taken.add(at)
        kept.append(Note(find=find.strip(), say=" ".join(say.split())[:LONGEST_SAY]))
        if len(kept) == most:
            break
    return kept


# Explained by the model the agent's next call in this env would think with, on the same keys as a
# call. Like a recording, it writes no usage row: a page's own endpoint paces what it asks for. The
# stage is read in a transaction of its own, and the model asked with no connection held.
async def explain_output(
    sessions: async_sessionmaker[AsyncSession], vault: Vault, scope: Scope, slug: str, asked: Asked
) -> list[Note]:
    """A text a page shows, explained by the agent's model as notes, each on one line of it."""
    async with sessions.begin() as session:
        agent = await agent_of(session, scope, slug)
        catalog = await providers.get_catalog(session)
        resolved = (await resolve_for_call(session, agent.whole, scope, catalog)).declaration
        keys = await providers.keys_of(session, vault, scope)
        thinking = providers.build_pipeline(resolved, catalog, keys).llm
    language = asked.language or primary_language(resolved.language) or FALLBACK_LANGUAGE
    return await ask(thinking, output=asked.output, command=asked.command, language=language, most=asked.most)


async def ask(running: Running, *, output: str, command: str, language: str, most: int) -> list[Note]:
    """The notes the agent's model gives on `output`, asked once; none when it answers nothing it can read."""
    asking = llm.ChatContext.empty()
    spoken = LANGUAGES.get(language.split("-")[0].lower(), language)
    asking.add_message(role="system", content=INSTRUCTIONS.format(most=most, language=spoken))
    asking.add_message(
        role="user", content=THE_OUTPUT.format(command=command or "(not given)", output=output[:LONGEST_OUTPUT])
    )
    async with providers.thinking_outside_a_call(running) as thinking:
        answered = await thinking.chat(chat_ctx=asking).collect()
    return notes_of(answered.text, output, most)


def _flatten(text: str) -> str:
    return " ".join(text.split()).lower()
