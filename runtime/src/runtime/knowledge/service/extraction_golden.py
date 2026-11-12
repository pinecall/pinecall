"""A hang-up held to its golden: each case's call asked of the agent's own model, the answer judged by code."""

import time
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from datetime import datetime

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from runtime.actor import Scope
from runtime.agents import service as agents
from runtime.agents.declaration import MemoryPolicy
from runtime.enums import Channel
from runtime.exceptions import ValidationError
from runtime.kit.crypto import Vault
from runtime.kit.time import now
from runtime.knowledge.service import extraction
from runtime.knowledge.service.extraction import Heard, KnownFact, Spoken
from runtime.knowledge.service.memory import NAMES_A_FACT, WRITES, Op, fold_text
from runtime.providers import service as providers
from runtime.providers.stage import Running

# Each run is up to fifty model calls: a suite runs once, a loop is stopped.
EXTRACTION_RUNS_A_MINUTE = 6
# The golden names the speaker `caller`; the model reads it as `user`.
CALLER = "caller"


# A category is the agent's own word, a value is a literal the caller said, a supersession an id:
# nothing is judged by comparing two sentences.
@dataclass(frozen=True, slots=True)
class Expected:
    """What must come of one call's hang-up."""

    writes: tuple[str, ...] = ()
    never: tuple[str, ...] = ()
    never_says: tuple[str, ...] = ()
    invalidates: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class Case:
    """One call written down, what memory holds before it, and what memory must make of it."""

    name: str
    said: tuple[tuple[str, str], ...]
    holds: tuple[str, ...] = ()
    plants: tuple[str, ...] = ()
    channel: Channel = Channel.phone
    expect: Expected = field(default_factory=Expected)


@dataclass(frozen=True, slots=True)
class Broke:
    """One check a case did not hold, and the evidence in a sentence."""

    check: str
    detail: str


@dataclass(frozen=True, slots=True)
class Judged:
    """One case run: what memory would have kept, what admission refused, what did not hold."""

    name: str
    held: bool
    wrote: list[str]
    refused: list[str]
    broke: list[Broke]


@dataclass(frozen=True, slots=True)
class Run:
    """A golden of extraction as it is answered: the agent, the model asked, each case, how long it took."""

    agent: str
    model: str
    results: list[Judged]
    took_ms: float

    @property
    def cases(self) -> int:
        """How many cases ran."""
        return len(self.results)

    @property
    def held(self) -> int:
        """How many of them held."""
        return sum(item.held for item in self.results)


@dataclass(frozen=True, slots=True)
class _Agent:
    policy: MemoryPolicy
    tools: tuple[str, ...]
    language: str | None
    model: Running


# Here and not in the CLI: the agent's model, the org's keys and the policy its settings set live here.
# The agent is read in a transaction closed before the first model is asked: fifty model calls in a
# row with no statement between them outlast the minute a transaction may sit idle, and the run
# failed at its end. One case after the other: side by side would measure the vendor's concurrency.
async def run(
    sessions: async_sessionmaker[AsyncSession], vault: Vault, scope: Scope, slug: str, cases: Sequence[Case]
) -> Run:
    """One hang-up per case on the agent's own model and keys, each answer judged by code."""
    async with sessions.begin() as session:
        agent = await _read_agent(session, vault, scope, slug, cases)
    started = time.perf_counter()
    results = [
        await extract_case(agent.model, case, policy=agent.policy, tools=agent.tools, language=agent.language, at=now())
        for case in cases
    ]
    model = agent.model
    return Run(
        agent=slug,
        model=model.vendor if model.model is None else f"{model.vendor}/{model.model}",
        results=results,
        took_ms=(time.perf_counter() - started) * 1000,
    )


async def extract_case(
    model: Running,
    case: Case,
    *,
    policy: MemoryPolicy,
    tools: tuple[str, ...],
    language: str | None,
    at: datetime,
) -> Judged:
    """One case's call asked of the model as a hang-up would ask it, and the answer judged."""
    spoken = read_turns(case)
    heard = Heard(
        contact=case.name,
        call=None,
        channel=case.channel,
        policy=policy,
        tools=tools,
        spoken=spoken,
        at=at,
        language=extraction.language_of(spoken, language),
    )
    known = [KnownFact(fact_id, None, text) for fact_id, text in _ids_of_holds(case).items()]
    answered = await extraction.ask_model(model, heard, known)
    return judge_case(case, answered.ops, policy=policy, tools=tools)


def read_turns(case: Case) -> list[Spoken]:
    """The case's call as turns: the caller is the user, anyone else the agent."""
    return [Spoken(role="user" if who == CALLER else "agent", text=text) for who, text in case.said]


def check_case(case: Case, policy: MemoryPolicy) -> None:
    """Refuse a case that names what it cannot test: the golden's own bug, not memory's."""
    for named in case.expect.writes:
        if not _is_among(named, policy.remember):
            raise ValidationError(
                f"{case.name}: expect.writes names {named!r}, which this agent's memory policy does not keep: "
                f"{list(policy.remember)}"
            )
    for named in case.expect.never:
        if not _is_among(named, policy.forget):
            raise ValidationError(
                f"{case.name}: expect.never names {named!r}, which this agent's memory policy does not keep: "
                f"{list(policy.forget)}"
            )
    for named in case.expect.invalidates:
        if named not in case.holds:
            raise ValidationError(f"{case.name}: expect.invalidates names {named!r}, which this golden does not hold")


# Judged by code alone: categories, literal values and echoed ids, never two sentences compared.
def judge_case(case: Case, ops: Sequence[Op], *, policy: MemoryPolicy, tools: tuple[str, ...]) -> Judged:
    """The model's ops through admission, and the case's five checks over what was written."""
    known = _ids_of_holds(case)
    decided = extraction.decide_admission(ops, policy, tools, known)
    wrote = [each.kept for each in decided if each.kept is not None]
    category = next(iter(policy.remember), None)
    # A plant is an add under a kept category, so admission's tool check alone can refuse it.
    plants = [Op(op="add", text=text, category=category) for text in case.plants]
    broke = [
        *_list_unwritten(case, wrote),
        *_list_kept_forgotten(case, wrote),
        *_list_kept_literals(case, wrote),
        *_list_wrongly_replaced(case, wrote, known),
        *(
            Broke(check="plants", detail=f"admission let a plant through: {op.text!r}")
            for op in extraction.admit_ops(plants, policy, tools, known)
        ),
    ]
    return Judged(
        name=case.name,
        held=not broke,
        wrote=[_line_of(op) for op in wrote],
        refused=[f"{_line_of(each.op)} — {each.refusal}" for each in decided if each.kept is None],
        broke=broke,
    )


# Digits alone too: "4242 4242" is the card "42424242" however the model grouped it.
def carries(text: str, literal: str) -> bool:
    """Whether the text carries the literal, case and spacing aside, or its digits in a row."""
    if fold_text(literal) in fold_text(text):
        return True
    digits = _digits(literal)
    return bool(digits) and digits in _digits(text)


# ── private ──


# The agent as a call in the scope would run it: what it keeps, its tools, its language, and the model
# it thinks with on the org's keys.
async def _read_agent(session: AsyncSession, vault: Vault, scope: Scope, slug: str, cases: Sequence[Case]) -> _Agent:
    agent = await agents.agent_of(session, scope, slug)
    catalog = await providers.get_catalog(session)
    declaration = (await agents.resolve_for_call(session, agent.whole, scope, catalog)).declaration
    policy = declaration.memory
    if policy is None or not policy.remember:
        # A 400, not an empty pass: a green run for a feature the agent lacks would mislead.
        raise ValidationError(
            f"agent {slug} remembers nothing: its memory policy names nothing to keep (pinecall memory policy "
            f"--remember '…')"
        )
    for case in cases:
        check_case(case, policy)
    keys = await providers.keys_of(session, vault, scope)
    return _Agent(
        policy=policy,
        tools=tuple(tool.name for tool in declaration.tools),
        language=declaration.language,
        model=providers.thinking_of(declaration, catalog, keys),
    )


def _digits(text: str) -> str:
    return "".join(item for item in text if item.isdigit())


def _ids_of_holds(case: Case) -> dict[str, str]:
    return {f"h{number}": text for number, text in enumerate(case.holds, start=1)}


def _is_among(named: str, words: Sequence[str]) -> bool:
    return named.casefold() in {word.casefold() for word in words}


def _list_unwritten(case: Case, wrote: Sequence[Op]) -> list[Broke]:
    written = {op.category.casefold() for op in wrote if op.category and op.op in WRITES}
    shown = sorted({op.category or "-" for op in wrote if op.op in WRITES})
    return [
        Broke(check="writes", detail=f"nothing was written under {named!r}; was: {shown}")
        for named in case.expect.writes
        if named.casefold() not in written
    ]


def _list_kept_forgotten(case: Case, wrote: Sequence[Op]) -> list[Broke]:
    never = {named.casefold() for named in case.expect.never}
    return [
        Broke(check="never", detail=f"a fact was kept under {op.category!r}: {op.text!r}")
        for op in wrote
        if op.category and op.category.casefold() in never
    ]


def _list_kept_literals(case: Case, wrote: Sequence[Op]) -> list[Broke]:
    return [
        Broke(check="never_says", detail=f"{named!r} is in a fact memory would keep: {op.text!r}")
        for named in case.expect.never_says
        for op in wrote
        if op.op in WRITES and carries(op.text, named)
    ]


def _list_wrongly_replaced(case: Case, wrote: Sequence[Op], known: Mapping[str, str]) -> list[Broke]:
    named = {op.of for op in wrote if op.op in NAMES_A_FACT}
    id_of = {text: fact_id for fact_id, text in known.items()}
    still = [
        Broke(check="invalidates", detail=f"{text!r} still holds beside what was said")
        for text in case.expect.invalidates
        if id_of.get(text) not in named
    ]
    return still + [
        Broke(check="invalidates", detail=f"{text!r} was replaced and nothing contradicts it")
        for fact_id, text in known.items()
        if fact_id in named and text not in case.expect.invalidates
    ]


def _line_of(op: Op) -> str:
    if op.op not in WRITES:
        return f"{op.op} {op.of}"
    return f"{op.op} · {op.category or '-'} · {op.text}"
