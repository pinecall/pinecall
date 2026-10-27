"""A text a page shows, explained by the agent's model as notes, each on one line of it, in the agent's own words."""

import json
import re
from dataclasses import dataclass

from livekit.agents import llm

from pinecall_runtime.kit.text import a_list, a_mapping
from pinecall_runtime.providers import service as providers

# A page reads an output aloud with a finger on the line it talks about: the model picks the lines
# that matter and says one sentence of each. A note names its line by a fragment copied from it, so the
# page can light it; a fragment that is in no line is dropped, as is anything the model made up.
MOST_NOTES = 6
LONGEST_OUTPUT = 8000
LONGEST_SAY = 240
LANGUAGES = {"es": "Spanish", "en": "English", "pt": "Portuguese", "fr": "French", "de": "German", "it": "Italian"}

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


def _flat(text: str) -> str:
    return " ".join(text.split()).lower()


def notes_of(answer: str, output: str, most: int = MOST_NOTES) -> list[Note]:
    """The model's answer read as notes: each `find` in one line of the output, one a line, `most` at most."""
    fenced = A_FENCE.match(answer)
    try:
        decoded: object = json.loads(fenced.group(1) if fenced else answer)
    except ValueError:
        return []
    if not a_list(decoded):
        return []
    lines = [_flat(line) for line in output.splitlines()]
    kept: list[Note] = []
    taken: set[int] = set()
    for item in decoded:
        if not a_mapping(item):
            continue
        find, say = item.get("find"), item.get("say")
        if not isinstance(find, str) or not isinstance(say, str) or not find.strip() or not say.strip():
            continue
        at = next((index for index, line in enumerate(lines) if _flat(find) in line), None)
        if at is None or at in taken:
            continue
        taken.add(at)
        kept.append(Note(find=find.strip(), say=" ".join(say.split())[:LONGEST_SAY]))
        if len(kept) == most:
            break
    return kept


async def explain(running: providers.Running, *, output: str, command: str, language: str, most: int) -> list[Note]:
    """The notes the agent's model gives on `output`, asked once; none when it answers nothing it can read."""
    thinking = providers.llm_of(running)
    asking = llm.ChatContext.empty()
    spoken = LANGUAGES.get(language.split("-")[0].lower(), language)
    asking.add_message(role="system", content=INSTRUCTIONS.format(most=most, language=spoken))
    asking.add_message(
        role="user", content=THE_OUTPUT.format(command=command or "(not given)", output=output[:LONGEST_OUTPUT])
    )
    try:
        answered = await thinking.chat(chat_ctx=asking).collect()
    finally:
        await thinking.aclose()
    return notes_of(answered.text, output, most)
