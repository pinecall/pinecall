"""What a call taught: its turns read at hang-up, asked of the model once, admitted, embedded and written."""

import json
import logging
import re
import time
from collections import Counter
from collections.abc import Collection, Sequence
from dataclasses import dataclass, replace
from datetime import datetime
from typing import Literal

from livekit.agents import llm
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from runtime.actor import Scope
from runtime.agents.declaration import Declaration, MemoryPolicy
from runtime.enums import Channel
from runtime.kit.crypto import Vault
from runtime.kit.text import a_list, a_mapping
from runtime.knowledge.service import memory
from runtime.knowledge.service.embedder import FindEmbedder
from runtime.knowledge.service.language import UNDECIDED, detect_language
from runtime.knowledge.service.memory import NAMES_A_FACT, OP_NAMES, WRITES, Op, OpName, Taught, fold_text
from runtime.providers import service as providers
from runtime.providers.stage import Running
from runtime.wire.base import Entry
from runtime.wire.events import AgentTurnEnded, UserTurnEnded
from runtime.wire.metrics import LLMModelUsage
from runtime.wire.parts import MemoryFact, MemoryOp

logger = logging.getLogger(__name__)

# A word shorter than this matches prepositions, and would refuse nearly every sentence.
SHORTEST_TOOL_WORD = 4
# Why admission refused an op, said beside it in a case's `refused` line.
FORGOTTEN = "the policy forgets {category!r}"
NAMES_A_TOOL = "{word!r} is a word of the tool {tool}, and a fact naming a tool is never kept"
NO_SUCH_FACT = "{of!r} is no fact the contact holds, or one this call already changed"

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
class Admission:
    """One op and what admission made of it: the op as it is kept, or why it was refused."""

    op: Op
    kept: Op | None
    refusal: str = ""


@dataclass(frozen=True, slots=True)
class MemoryWrite:
    """What one call wrote into its contact's memory, and the tokens the model took to find it."""

    op: MemoryOp
    usage: LLMModelUsage | None


# What a hang-up reads before any vendor is asked: the embedder, the model the agent thinks with on
# the org's keys as they are now, and the facts the contact holds.
@dataclass(frozen=True, slots=True)
class _Asking:
    model: Running
    known: list[KnownFact]


def hear_call(
    call: str,
    channel: Channel,
    contact: str | None,
    declaration: Declaration,
    entries: Sequence[Entry],
    *,
    at: datetime,
) -> Heard | None:
    """What the extraction model reads of a finished call; None when nothing is to be kept."""
    if contact is None or declaration.memory is None:
        return None
    spoken = [turn for entry in entries if (turn := _turn_of(entry)) is not None]
    return Heard(
        contact=contact,
        call=call,
        channel=channel,
        policy=declaration.memory,
        tools=tuple(tool.name for tool in declaration.tools),
        spoken=spoken,
        at=at,
        language=language_of(spoken, declaration.language),
    )


# Three steps, and no connection held while a vendor answers: what the contact holds is read and the
# write admitted, the model is asked and its facts embedded, the ops are written. A memory at its cap
# is refused before the model is asked (`QuotaExceeded`), so a hang-up at the cap costs nothing; the
# stock is held again in the transaction that writes. None on a box with no embedder: nothing is
# remembered there, and nothing says a call was.
async def remember(
    sessions: async_sessionmaker[AsyncSession],
    vault: Vault,
    find_embedder: FindEmbedder,
    scope: Scope,
    declaration: Declaration,
    heard: Heard,
) -> MemoryWrite | None:
    """What one call taught, asked of the agent's model once, admitted, embedded and written as one."""
    started = time.perf_counter()
    async with sessions.begin() as session:
        embedder = await find_embedder(session)
        if embedder is None:
            return None
        await memory.admit_fact(session, scope)
        asking = await _read_asking(session, vault, scope, declaration, heard) if heard.policy.remember else None
    written: list[MemoryFact] = []
    usage = None
    if asking is not None:
        answered = await ask_model(asking.model, heard, asking.known)
        usage = answered.usage
        ops = admit_ops(answered.ops, heard.policy, heard.tools, {fact.id for fact in asking.known})
        embedded = await memory.embed_ops(embedder, ops)
        if embedded:
            async with sessions.begin() as session:
                await memory.admit_fact(session, scope)
                taught = Taught(heard.contact, heard.call, heard.at)
                facts = await memory.apply_ops(session, scope, taught, embedded, model=embedder.model)
                written = [
                    MemoryFact(id=str(fact.id), text=fact.text, category=fact.category, source=fact.source_call)
                    for fact in facts
                ]
    took_ms = (time.perf_counter() - started) * 1000
    op = MemoryOp(op="remember", contact=heard.contact, facts=written, took_ms=took_ms)
    return MemoryWrite(op=op, usage=usage)


# The vendor's own errors pass through: whoever ends the call says a hang-up that could not be read.
async def ask_model(model: Running, heard: Heard, known: Sequence[KnownFact]) -> ExtractionAnswer:
    """The ops the model asks for over the call, before any admission, and what it took."""
    async with providers.thinking_outside_a_call(model) as thinking:
        answered = await thinking.chat(chat_ctx=_ask(heard, known)).collect()
        usage = providers.completion_usage(thinking, answered.usage)
    return ExtractionAnswer(ops=parse_ops(answered.text), usage=usage)


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
    return [each.kept for each in decide_admission(ops, policy, tools, known) if each.kept is not None]


# Each op with what admission made of it. The forget list reads the category the model gave, before the
# filing: a fact under a forgotten category is refused, never filed as `other`.
def decide_admission(
    ops: Sequence[Op], policy: MemoryPolicy, tools: Sequence[str], known: Collection[str]
) -> list[Admission]:
    """What admission makes of each op, in order: kept and filed, or refused with the reason."""
    forgotten = {word.casefold() for word in policy.forget}
    named: set[str] = set()
    decided: list[Admission] = []
    for op in ops:
        if op.category is not None and op.category.casefold() in forgotten:
            decided.append(Admission(op, None, FORGOTTEN.format(category=op.category)))
            continue
        tool = _find_tool_in(op.text, tools) if op.text else None
        if tool is not None:
            logger.warning("a fact naming one of the agent's own tools was not written")
            decided.append(Admission(op, None, NAMES_A_TOOL.format(word=tool[0], tool=tool[1])))
            continue
        if op.op in NAMES_A_FACT:
            if op.of is None or op.of not in known or op.of in named:
                decided.append(Admission(op, None, NO_SUCH_FACT.format(of=op.of)))
                continue
            named.add(op.of)
        filed = replace(op, category=file_under(op.category, policy.remember)) if op.op in WRITES else op
        decided.append(Admission(op, filed))
    return decided


def file_under(category: str | None, remember: Sequence[str]) -> str:
    """The policy's entry as written that the category names, case and spacing aside; `other` when none."""
    wanted = fold_text(category or "")
    return next((entry for entry in remember if fold_text(entry) == wanted), OTHER)


# The caller's language, as they spoke it: a written call of an agent set to Spanish whose caller
# writes English is an English call. The agent's setting only stands in where nothing else tells.
def language_of(spoken: Sequence[Spoken], agents: str | None) -> str | None:
    """The language the caller spoke on the call: the recognizer's, else their own lines', else the agent's."""
    heard = Counter(turn.language for turn in spoken if turn.role == "user" and turn.language)
    if heard:
        return heard.most_common(1)[0][0]
    written = detect_language([turn.text for turn in spoken if turn.role == "user"])
    return agents if written == UNDECIDED else written.value


# ── private ──


async def _read_asking(
    session: AsyncSession, vault: Vault, scope: Scope, declaration: Declaration, heard: Heard
) -> _Asking:
    known = await memory.list_current(session, scope, heard.contact)
    catalog = await providers.get_catalog(session)
    keys = await providers.keys_of(session, vault, scope)
    return _Asking(
        model=providers.thinking_of(declaration, catalog, keys),
        known=[KnownFact(str(fact.id), fact.category, fact.text) for fact in known],
    )


def _ask(heard: Heard, known: Sequence[KnownFact]) -> llm.ChatContext:
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


# Only an update and an invalidate name a fact. Until 2026-11 an `of` was kept on any op and looked up
# as it was written: a model that answered `"of": ""` on an add raised there and every fact of the
# call was lost with it, and one that answered a real id replaced that fact with no check that it was
# the contact's.
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
    names = of if name in NAMES_A_FACT and isinstance(of, str) else None
    return Op(op=name, text=text, category=category or None, of=names)


# A fact naming one of the agent's tools could grant it a permission ("book without asking"): every
# word of every tool's name is refused (`listOrders` refuses "order"), matched by prefix so plurals and
# stems count. Wide on purpose: a plain word that is a tool's name is refused with it.
def _find_tool_in(text: str, tools: Sequence[str]) -> tuple[str, str] | None:
    """The fact's word and the tool whose name holds it, or None."""
    words = [word for word in _words(text) if len(word) >= SHORTEST_TOOL_WORD]
    for tool in tools:
        for item in (part for part in _words(tool) if len(part) >= SHORTEST_TOOL_WORD):
            word = next((word for word in words if word.startswith(item) or item.startswith(word)), None)
            if word is not None:
                return word, tool
    return None


def _words(text: str) -> list[str]:
    return [word.casefold() for word in A_WORD.findall(A_HUMP.sub(" ", text))]


def _turn_of(entry: Entry) -> Spoken | None:
    if entry.type == "turn.user":
        heard = UserTurnEnded.parse(entry.data, "turn.user")
        return Spoken(role="user", text=heard.text, language=heard.language)
    if entry.type == "turn.agent":
        return Spoken(role="agent", text=AgentTurnEnded.parse(entry.data, "turn.agent").text)
    return None
