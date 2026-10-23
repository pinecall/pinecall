"""What a call taught: asked of the model at hang-up, admitted, written; the goldens judging it."""

import json
import logging
import re
import time
from collections import Counter
from collections.abc import Collection, Mapping, Sequence
from dataclasses import dataclass, replace
from datetime import datetime
from typing import Literal

from livekit.agents import llm
from sqlalchemy.ext.asyncio import AsyncSession

from pinecall_runtime.agents.declaration import MemoryPolicy
from pinecall_runtime.enums import Channel
from pinecall_runtime.exceptions import ValidationError
from pinecall_runtime.kit.auth import Scope
from pinecall_runtime.kit.text import a_list, a_mapping
from pinecall_runtime.knowledge.models import ContactMemory
from pinecall_runtime.knowledge.schemas import ExtractionBroke, ExtractionGolden, ExtractionJudged
from pinecall_runtime.knowledge.service import memory
from pinecall_runtime.knowledge.service.embedder import Embedder
from pinecall_runtime.knowledge.service.language import UNDECIDED, detected
from pinecall_runtime.knowledge.service.memory import NAMES_A_FACT, OP_NAMES, WRITES, Op, OpName, Taught, fold_text
from pinecall_runtime.providers import service as providers
from pinecall_runtime.providers.service import plugins
from pinecall_runtime.wire.metrics import LLMModelUsage
from pinecall_runtime.wire.parts import MemoryFact, MemoryOp

logger = logging.getLogger(__name__)

# A word shorter than this matches prepositions, and would refuse nearly every sentence.
SHORTEST_TOOL_WORD = 4
# The golden names the speaker `caller`; the model reads it as `user`.
CALLER = "caller"

# What a category the model did not copy from the policy is filed under.
OTHER = "other"

# JSON so the answer is parsed strictly: prose yields no ops.
INSTRUCTIONS = """\
You keep a contact center's memory of one contact, so that the next call starts where this one \
ended. Read the call below and write down what it taught about the contact that stays true and \
will be useful on a later call. Never write what the agent said, never what is already known, \
and nothing outside these categories, which are the tenant's own words: {remember}.
{forget}
Answer with a JSON array and nothing else; an empty array is a good answer. Each element is one of:
  {{"op": "add", "text": "...", "category": "<one of the categories, copied exactly as written>"}}
  {{"op": "update", "of": "<the id of a known fact>", "text": "...", "category": "<as above>"}}
  {{"op": "invalidate", "of": "<the id of a known fact>"}}
Every text is one short sentence about the contact, in the third person and never in their own voice \
("Allergic to penicillin.", "Prefers mornings."), {language}."""
# A later call reads each fact back as it was written, and the agent answers in its language.
CALL_LANGUAGE = (
    "written in {tag}, the language this call was held in, whatever language the categories or the agent's lines are in"
)
CALLER_LANGUAGE = (
    "written in the language the contact speaks in the lines marked `user`, whatever language "
    "the categories or the agent's lines are in"
)
NEVER_KEEP = "Never write anything about: {forget}. Whatever the call says of it stays out."
KNOWN = "Already known (id · category · text):\n{facts}"
NOTHING_KNOWN = "Nothing is known about this contact yet."
THE_CALL = "The call, on {channel}:\n{turns}"

A_FENCE = re.compile(r"^\s*```[A-Za-z]*\s*(.*?)\s*```\s*$", re.DOTALL)
A_WORD = re.compile(r"[^\W\d_]+")
A_HUMP = re.compile(r"(?<=[a-z0-9])(?=[A-Z])")


# Not the log entry: tool payloads never reach the extraction model.
@dataclass(frozen=True, slots=True)
class Spoken:
    """One turn of a call as the extraction model reads it; a caller's carries the language heard."""

    role: Literal["user", "agent"]
    text: str
    language: str | None = None


@dataclass(frozen=True, slots=True)
class Heard:
    """One call to learn from: whose it was, what the agent keeps, its tools, its turns, its end."""

    contact: str
    call: str | None
    channel: Channel
    policy: MemoryPolicy
    tools: tuple[str, ...]
    spoken: list[Spoken]
    at: datetime
    # The language facts are written in; None when the recognizer, the caller's lines and the agent all say none.
    language: str | None = None


@dataclass(frozen=True, slots=True)
class KnownFact:
    """A fact as the model is shown it: by id, category and text."""

    id: str
    category: str | None
    text: str


@dataclass(frozen=True, slots=True)
class ExtractionAnswer:
    """The ops the model asked for over a call, and the tokens asking it took."""

    ops: list[Op]
    usage: LLMModelUsage | None


@dataclass(frozen=True, slots=True)
class MemoryWrite:
    """What one call wrote into its contact's memory, and the tokens the model took to find it."""

    op: MemoryOp
    usage: LLMModelUsage | None


async def remember(
    session: AsyncSession, embedder: Embedder, model: plugins.Running, scope: Scope, heard: Heard
) -> MemoryWrite:
    """What one call taught, asked of the model once, admitted, embedded and written as one."""
    started = time.perf_counter()
    written: list[ContactMemory] = []
    usage = None
    if heard.policy.remember:
        known = await memory.current(session, scope, heard.contact)
        answered = await ask_model(model, heard, [KnownFact(str(fact.id), fact.category, fact.text) for fact in known])
        usage = answered.usage
        ops = admit_ops(answered.ops, heard.policy, heard.tools, {str(fact.id) for fact in known})
        written = await memory.apply_ops(session, embedder, scope, Taught(heard.contact, heard.call, heard.at), ops)
    op = MemoryOp(
        op="remember",
        contact=heard.contact,
        facts=[
            MemoryFact(id=str(fact.id), text=fact.text, category=fact.category, source=fact.source_call)
            for fact in written
        ],
        took_ms=(time.perf_counter() - started) * 1000,
    )
    return MemoryWrite(op=op, usage=usage)


async def ask_model(model: plugins.Running, heard: Heard, known: Sequence[KnownFact]) -> ExtractionAnswer:
    """The ops the model asks for over the call, before any admission, and what it took."""
    thinking = providers.llm_of(model)
    try:
        answered = await thinking.chat(chat_ctx=_asking(heard, known)).collect()
    finally:
        await thinking.aclose()
    return ExtractionAnswer(ops=parse_ops(answered.text), usage=providers.completion_usage(thinking, answered.usage))


def parse_ops(answer: str) -> list[Op]:
    """The model's answer read as ops; a fence is forgiven, anything else malformed is no ops."""
    fenced = A_FENCE.match(answer)
    try:
        decoded: object = json.loads(fenced.group(1) if fenced else answer)
    except ValueError:
        logger.warning("the extraction model answered something that is not JSON; nothing written")
        return []
    if not a_list(decoded):
        logger.warning("the extraction model answered JSON that is not an array; nothing written")
        return []
    return [op for op in map(_op_of, decoded) if op is not None]


# Admission at write time: filtering what is read back is not enough once a fact is stored. A fact
# the policy lets through is filed under one of its own categories: the model asked for one and may
# not have copied it, so what it wrote is read against the list, and `other` is what no entry matches.
def admit_ops(ops: Sequence[Op], policy: MemoryPolicy, tools: Sequence[str], known: Collection[str]) -> list[Op]:
    """The ops the policy lets through, filed under its categories, given the ids of the contact's current facts."""
    return [kept for _, kept in _admission(ops, policy, tools, known) if kept is not None]


def filed_under(category: str | None, remember: Sequence[str]) -> str:
    """The policy's entry as written that the category names, case and spacing aside; `other` when none."""
    wanted = fold_text(category or "")
    return next((entry for entry in remember if fold_text(entry) == wanted), OTHER)


# The caller's language, as they spoke it: a written call of an agent set to Spanish whose caller
# writes English is an English call. The agent's setting only stands in where nothing else tells.
def language_of(spoken: Sequence[Spoken], declared: str | None) -> str | None:
    """The language the caller spoke on the call: the recognizer's, else their own lines', else the agent's."""
    heard = Counter(turn.language for turn in spoken if turn.role == "user" and turn.language)
    if heard:
        return heard.most_common(1)[0][0]
    written = detected([turn.text for turn in spoken if turn.role == "user"])
    return declared if written == UNDECIDED else written


async def extract_case(
    model: plugins.Running,
    case: ExtractionGolden,
    *,
    policy: MemoryPolicy,
    tools: tuple[str, ...],
    language: str | None,
    at: datetime,
) -> ExtractionJudged:
    """One case's call asked of the model as a hang-up would ask it, and the answer judged."""
    spoken = said_in(case)
    heard = Heard(
        contact=case.name,
        call=None,
        channel=case.channel,
        policy=policy,
        tools=tools,
        spoken=spoken,
        at=at,
        language=language_of(spoken, language),
    )
    known = [KnownFact(fact_id, None, text) for fact_id, text in _held_ids(case).items()]
    answered = await ask_model(model, heard, known)
    return judge_extraction(case, answered.ops, policy=policy, tools=tools)


def said_in(case: ExtractionGolden) -> list[Spoken]:
    """The case's call as turns: the caller is the user, anyone else the agent."""
    return [Spoken(role="user" if who == CALLER else "agent", text=text) for who, text in case.said]


def check_case(case: ExtractionGolden, policy: MemoryPolicy) -> None:
    """Refuse a case that names what it cannot test: the golden's own bug, not memory's."""
    for named in case.expect.writes:
        if not _among(named, policy.remember):
            raise ValidationError(
                f"{case.name}: expect.writes names {named!r}, which this agent's memory policy does not keep: "
                f"{list(policy.remember)}"
            )
    for named in case.expect.never:
        if not _among(named, policy.forget):
            raise ValidationError(
                f"{case.name}: expect.never names {named!r}, which this agent's memory policy does not keep: "
                f"{list(policy.forget)}"
            )
    for named in case.expect.invalidates:
        if named not in case.holds:
            raise ValidationError(f"{case.name}: expect.invalidates names {named!r}, which this golden does not hold")


# Judged by code alone: categories, literal values and echoed ids, never two sentences compared.
def judge_extraction(
    case: ExtractionGolden, ops: Sequence[Op], *, policy: MemoryPolicy, tools: tuple[str, ...]
) -> ExtractionJudged:
    """The model's ops through admission, and the case's five checks over what was written."""
    known = _held_ids(case)
    decided = _admission(ops, policy, tools, known)
    wrote = [kept for _, kept in decided if kept is not None]
    refused = [op for op, kept in decided if kept is None]
    category = next(iter(policy.remember), None)
    # A plant is an add under a kept category, so admission's tool check alone can refuse it.
    plants = [Op(op="add", text=text, category=category) for text in case.plants]
    broke = [
        *_unwritten(case, wrote),
        *_forgotten_kept(case, wrote),
        *_literals_kept(case, wrote),
        *_superseded(case, wrote, known),
        *(
            ExtractionBroke(check="plants", detail=f"admission let a plant through: {op.text!r}")
            for op in admit_ops(plants, policy, tools, known)
        ),
    ]
    return ExtractionJudged(
        name=case.name,
        held=not broke,
        wrote=[_as_a_line(op) for op in wrote],
        refused=[_as_a_line(op) for op in refused],
        broke=broke,
    )


# Digits alone too: "4242 4242" is the card "42424242" however the model grouped it.
def carries(text: str, literal: str) -> bool:
    """Whether the text carries the literal, case and spacing aside, or its digits in a row."""
    if fold_text(literal) in fold_text(text):
        return True
    digits = _digits(literal)
    return bool(digits) and digits in _digits(text)


def _asking(heard: Heard, known: Sequence[KnownFact]) -> llm.ChatContext:
    policy = heard.policy
    forget = NEVER_KEEP.format(forget=", ".join(policy.forget)) if policy.forget else ""
    asking = llm.ChatContext.empty()
    language = CALL_LANGUAGE.format(tag=heard.language) if heard.language else CALLER_LANGUAGE
    asking.add_message(
        role="system",
        content=INSTRUCTIONS.format(remember=", ".join(policy.remember), forget=forget, language=language),
    )
    shown = (
        KNOWN.format(facts="\n".join(f"- {item.id} · {item.category or '-'} · {item.text}" for item in known))
        if known
        else NOTHING_KNOWN
    )
    turns = "\n".join(f"{turn.role}: {turn.text}" for turn in heard.spoken)
    asking.add_message(role="user", content=f"{shown}\n\n{THE_CALL.format(channel=heard.channel, turns=turns)}")
    return asking


def _op_of(item: object) -> Op | None:
    if not a_mapping(item):
        return None
    kind = item.get("op")
    name: OpName | None = next((known for known in OP_NAMES if kind == known), None)
    text = " ".join(str(item.get("text") or "").split())
    of = item.get("of")
    if name is None or (name in WRITES and not text):
        return None
    if name in NAMES_A_FACT and not isinstance(of, str):
        return None
    category = str(item.get("category") or "").strip()
    return Op(op=name, text=text, category=category or None, of=of if isinstance(of, str) else None)


# Each op with what admission made of it: None when refused. The forget list reads the category the
# model gave, before the filing: a fact under a forgotten category is refused, never filed as `other`.
def _admission(
    ops: Sequence[Op], policy: MemoryPolicy, tools: Sequence[str], known: Collection[str]
) -> list[tuple[Op, Op | None]]:
    forgotten = {word.casefold() for word in policy.forget}
    named: set[str] = set()
    decided: list[tuple[Op, Op | None]] = []
    for op in ops:
        if op.category is not None and op.category.casefold() in forgotten:
            decided.append((op, None))
            continue
        if op.text and _names_a_tool(op.text, tools):
            logger.warning("a fact naming one of the agent's own tools was not written")
            decided.append((op, None))
            continue
        if op.op in NAMES_A_FACT:
            if op.of is None or op.of not in known or op.of in named:
                decided.append((op, None))
                continue
            named.add(op.of)
        decided.append((op, replace(op, category=filed_under(op.category, policy.remember)) if op.op in WRITES else op))
    return decided


# A fact naming one of the agent's tools could grant it a permission ("book without asking"):
# the tools are the whole vocabulary refused, matched by prefix so plurals and stems count.
def _names_a_tool(text: str, tools: Sequence[str]) -> bool:
    words = [word for word in _words(text) if len(word) >= SHORTEST_TOOL_WORD]
    wanted = [word for tool in tools for word in _words(tool) if len(word) >= SHORTEST_TOOL_WORD]
    return any(word.startswith(item) or item.startswith(word) for word in words for item in wanted)


def _words(text: str) -> list[str]:
    return [word.casefold() for word in A_WORD.findall(A_HUMP.sub(" ", text))]


def _digits(text: str) -> str:
    return "".join(item for item in text if item.isdigit())


def _held_ids(case: ExtractionGolden) -> dict[str, str]:
    return {f"h{number}": text for number, text in enumerate(case.holds, start=1)}


def _among(named: str, declared: Sequence[str]) -> bool:
    return named.casefold() in {word.casefold() for word in declared}


def _unwritten(case: ExtractionGolden, wrote: Sequence[Op]) -> list[ExtractionBroke]:
    written = {op.category.casefold() for op in wrote if op.category and op.op in WRITES}
    shown = sorted({op.category or "-" for op in wrote if op.op in WRITES})
    return [
        ExtractionBroke(check="writes", detail=f"nothing was written under {named!r}; was: {shown}")
        for named in case.expect.writes
        if named.casefold() not in written
    ]


def _forgotten_kept(case: ExtractionGolden, wrote: Sequence[Op]) -> list[ExtractionBroke]:
    never = {named.casefold() for named in case.expect.never}
    return [
        ExtractionBroke(check="never", detail=f"a fact was kept under {op.category!r}: {op.text!r}")
        for op in wrote
        if op.category and op.category.casefold() in never
    ]


def _literals_kept(case: ExtractionGolden, wrote: Sequence[Op]) -> list[ExtractionBroke]:
    return [
        ExtractionBroke(check="never_says", detail=f"{named!r} is in a fact memory would keep: {op.text!r}")
        for named in case.expect.never_says
        for op in wrote
        if op.op in WRITES and carries(op.text, named)
    ]


def _superseded(case: ExtractionGolden, wrote: Sequence[Op], known: Mapping[str, str]) -> list[ExtractionBroke]:
    named = {op.of for op in wrote if op.op in NAMES_A_FACT}
    id_of = {text: held_id for held_id, text in known.items()}
    still = [
        ExtractionBroke(check="invalidates", detail=f"{text!r} still holds beside what was said")
        for text in case.expect.invalidates
        if id_of.get(text) not in named
    ]
    return still + [
        ExtractionBroke(check="invalidates", detail=f"{text!r} was replaced and nothing contradicts it")
        for held_id, text in known.items()
        if held_id in named and text not in case.expect.invalidates
    ]


def _as_a_line(op: Op) -> str:
    if op.op not in WRITES:
        return f"{op.op} {op.of}"
    return f"{op.op} · {op.category or '-'} · {op.text}"
