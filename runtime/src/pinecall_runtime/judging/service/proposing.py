"""A group of cases diagnosed by a model: the cause, and the change it proposes and where."""

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Never

from livekit.agents import llm
from pydantic import ValidationError as PydanticValidationError

from pinecall_runtime.exceptions import UpstreamError
from pinecall_runtime.judging.schemas import ProposalRow
from pinecall_runtime.judging.service.asking import forced
from pinecall_runtime.kit.text import JsonObject
from pinecall_runtime.wire.metrics import LLMModelUsage

# A proposal is read by a person before anything changes: it says where, what, and how sure,
# and it never answers for the judge — a judge that was wrong is the person's to say.
DOCTOR = (
    "You diagnose why an AI phone or chat agent failed the same check on several calls. "
    "Read the check, what each call did wrong and the lines that show it, the agent's "
    "prompt, its settings and its tools. Name the one cause they share in one sentence. "
    "Then propose the smallest change that fixes it: a setting (name the setting and its "
    "new value), code (name the tool or the prompt block and what it must do instead), "
    "knowledge (what the agent must be told), or none when the calls show no fault of the "
    "agent's. Say how sure you are, 0 to 1. Then call the tool."
)

NO_DIAGNOSIS = "the model handed in no diagnosis it could read: {why}"
MOST_CHARS = 6000

TOOL: JsonObject = {
    "name": "propose_fix",
    "description": "Hand in the diagnosis.",
    "parameters": {
        "type": "object",
        "properties": {
            "cause": {"type": "string", "description": "the cause the calls share, one sentence"},
            "kind": {"type": "string", "enum": ["setting", "code", "knowledge", "none"]},
            "where": {
                "type": "string",
                "description": "the setting's name, the tool or prompt block, or the knowledge",
            },
            "change": {"description": "the setting's new value, or what the code or knowledge must say"},
            "confidence": {"type": "number", "description": "0 to 1"},
        },
        "required": ["cause", "kind", "where", "change", "confidence"],
    },
}


@dataclass(frozen=True, slots=True)
class Failure:
    """One call of the group: the reason its judge gave, and the lines it pointed at."""

    call: str
    reason: str
    lines: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class Dossier:
    """What the doctor reads: the check that failed, the calls, the agent as it ran."""

    judge: str
    question: str
    failures: Sequence[Failure]
    prompt: str = ""
    settings: Mapping[str, object] | None = None
    tools: tuple[str, ...] = ()


async def diagnose(model: llm.LLM[Never], dossier: Dossier) -> tuple[ProposalRow, LLMModelUsage | None]:
    """The group's cause and the change proposed, read whole or refused."""
    fields, usage = await forced(model, DOCTOR, _question_of(dossier), TOOL)
    try:
        return ProposalRow.model_validate(dict(fields)), usage
    except PydanticValidationError as unread:
        raise UpstreamError(NO_DIAGNOSIS.format(why=unread.errors()[0]["msg"])) from unread


def _question_of(dossier: Dossier) -> str:
    blocks = [f"The check ({dossier.judge}): {dossier.question}"]
    for failure in dossier.failures:
        lines = "\n".join(f"  {line}" for line in failure.lines)
        blocks.append(f"Call {failure.call} failed it: {failure.reason}\n{lines}")
    if dossier.prompt:
        blocks.append(f"The agent's prompt:\n{dossier.prompt[:MOST_CHARS]}")
    if dossier.settings:
        settings = "\n".join(f"- {name}: {value}" for name, value in dossier.settings.items())
        blocks.append(f"The agent's settings:\n{settings}")
    if dossier.tools:
        blocks.append("The agent's tools:\n" + "\n".join(dossier.tools))
    return "\n\n".join(blocks)
