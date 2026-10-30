"""The bodies of the judges, personas, cases, groups and calibration endpoints."""

from datetime import datetime
from typing import Literal

from pydantic import Field, field_serializer

from pinecall_runtime.enums import CaseSource, CaseStatus, Env, JudgeAnswer, JudgeRunsWhen
from pinecall_runtime.kit.schemas import Row, Schema
from pinecall_runtime.kit.text import Json, JsonObject
from pinecall_runtime.wire.base import WireModel
from pinecall_runtime.wire.goldens import Expect, Golden
from pinecall_runtime.wire.parts import CallerBehavior, JudgeRead
from pinecall_runtime.wire.scores import Judgment

# How an answer scores: a pass is 1, unsure is 0.5, a fail is 0, as livekit's own scoring has it.
PASSED = 1.0


def _as_epoch(at: datetime | None) -> float | None:
    return None if at is None else at.timestamp()


# ── judges: Pinecall's library, the org's own, an agent's own ──


class JudgeRequest(Schema):
    """PUT …/judges/{name}: a judge of one's own, whole, or for one of Pinecall's only `on`."""

    question: str = ""
    answer: JudgeAnswer = JudgeAnswer.verdict
    # The answers a `choice` judge picks from: two at least, and only for `choice`.
    choices: list[str] = Field(default_factory=list[str])
    # always, only a simulated call, or a call `trigger` says it applies to (a no is N/A).
    when: JudgeRunsWhen = JudgeRunsWhen.always
    trigger: str = ""
    reads: list[JudgeRead] = Field(default_factory=list[JudgeRead])
    # One of Pinecall's judges: whether the org's calls (or the agent's) meet it. Nothing else.
    on: bool | None = None


class JudgeRow(Row):
    """One judge as the list shows it: whose it is, whether it runs, and what it asks."""

    name: str
    # "pinecall" for the library's, "org" for the org's own, else the agent's slug.
    owner: str
    on: bool
    question: str
    answer: JudgeAnswer
    choices: list[str]
    when: JudgeRunsWhen
    trigger: str
    reads: list[str]
    # The library's: one line on what it holds a call to, and the version of its question.
    summary: str | None = None
    version: int | None = None
    # The library's: what it saves an org from, and whether Pinecall says to switch it on first.
    why: str | None = None
    recommended: bool = False
    # One of the org's own: who wrote it last, and when.
    author: str | None = None
    set_at: float | None = None


class JudgeList(Row):
    """GET /v1/agents/{slug}/judges: Pinecall's judges first, then the org's, then the agent's."""

    judges: list[JudgeRow]


class JudgeTry(JudgeRequest):
    """POST /v1/agents/{slug}/judges/try: a judge asked of finished calls, never saved."""

    # One of Pinecall's by its name alone, or one of the org's own as written in this body.
    name: str
    # The agent's newest finished calls, or the calls named; never both.
    last: int | None = Field(None, ge=1, le=50)
    calls: list[str] = Field(default_factory=list[str], max_length=50)


class JudgeTriedRow(Row):
    """What the judge answered of one call, or why it did not."""

    call: str
    judgment: Judgment | None
    not_judged: str | None = None


class JudgeTried(Row):
    """The judge's answer on every call it was tried on, the evals spent and what they cost."""

    rows: list[JudgeTriedRow]
    evals: int
    cost_usd: float


# ── the simulated caller, and an agent's personas ──


class CallerPersona(Schema):
    """A persona as the caller endpoints take it: who to play, and on what."""

    name: str = ""
    # Bounded: each is a model's prompt, on keys the box may lend.
    goal: str = Field(max_length=4000)
    style: str = Field(max_length=4000)
    facts: JsonObject = Field(default_factory=dict[str, Json])
    llm: str | None = None
    tts: str | None = None
    voice: str | None = None
    # For its judge alone (expected-outcome): the model playing the caller is never told them.
    expects: list[str] = Field(default_factory=list[str], max_length=20)
    behavior: CallerBehavior = Field(default_factory=CallerBehavior)


class PersonaRequest(Schema):
    """PUT /v1/agents/{slug}/personas/{name}: the caller written whole, or for Pinecall's `on`."""

    about: str = ""
    goal: str = ""
    style: str = ""
    facts: dict[str, str] = Field(default_factory=dict[str, str])
    state: JsonObject = Field(default_factory=dict[str, Json])
    llm: str | None = None
    tts: str | None = None
    voice: str | None = None
    # One verifiable demand a line ("The agent should…"); the expected-outcome judge reads them.
    expects: list[str] = Field(default_factory=list[str], max_length=20)
    tags: list[str] = Field(default_factory=list[str], max_length=10)
    behavior: CallerBehavior = Field(default_factory=CallerBehavior)
    # The name this caller had, when the write renames it.
    was: str | None = None
    # One of Pinecall's personas: whether the agent's runs play it. Nothing else is written.
    on: bool | None = None


class PersonaRow(Row):
    """One caller of the agent as the list shows it, and whose it is."""

    agent: str
    name: str
    # "pinecall" for the library's, else the agent's slug.
    owner: str
    on: bool
    about: str
    goal: str
    style: str
    facts: dict[str, str]
    state: JsonObject
    llm: str | None
    tts: str | None
    voice: str | None
    expects: list[str]
    tags: list[str]
    behavior: CallerBehavior
    # The library's: one line on what it is for, and the version of its page.
    summary: str | None = None
    version: int | None = None
    # The agent's own: who wrote it last, and when.
    author: str | None = None
    set_at: float | None = None


class PersonaList(Row):
    """GET /v1/agents/{slug}/personas: the agent's callers by name; /v1/personas, every agent's."""

    personas: list[PersonaRow]


class GeneratePersonas(Schema):
    """POST /v1/agents/{slug}/personas/generate: how many callers, about what, like whom."""

    n: int = Field(default=3, ge=1, le=10)
    about: str = Field(default="", max_length=2000)
    # A finished call whose caller these are like.
    from_call: str | None = None
    # One of Pinecall's personas, written again for this agent.
    template: str | None = None


class ProposedPersona(Row):
    """A caller written for the agent and saved nowhere: PUT it to keep it."""

    name: str
    about: str
    goal: str
    style: str
    facts: dict[str, str]
    expects: list[str]
    tags: list[str]
    behavior: CallerBehavior


class GeneratedPersonas(Row):
    """The callers written, the evals they cost (one each, none on the org's key), and dollars."""

    personas: list[ProposedPersona]
    evals: int
    cost_usd: float


# ── the org's dataset: real calls kept as goldens ──


class PromoteCaseRequest(Schema):
    """POST /v1/evals/cases, the body: the finished call, its name, what it expects, held out."""

    call: str
    name: str = Field(min_length=1)
    expect: Expect = Field(default_factory=Expect)
    # Left out of a nightly run, read only when a run names it.
    held_out: bool = False


class WriteCaseRequest(Schema):
    """PUT /v1/agents/{slug}/cases/{name}, the body: the golden a person wrote, held out or not."""

    golden: Golden
    # Left out of a nightly run, read only when a run names it.
    held_out: bool = False


class BrokeOn(WireModel):
    """A judge that broke on the call a case was kept from, and why."""

    judge: str
    reason: str


class CaseRow(Row):
    """One case of the org's dataset: the golden a real call made, whose, from where, by whom."""

    id: str
    agent: str
    name: str
    golden: Golden
    # The call the case was kept from; None for a case a person wrote, which no call made.
    source_call: str | None
    source_env: Env
    held_out: bool
    author: str
    created_at: datetime
    status: CaseStatus = CaseStatus.approved
    # The judges that broke at hang-up; empty for a case a person kept from a call that held.
    broke: list[BrokeOn] = Field(default_factory=list[BrokeOn])
    # The settings version the call ran on, None where its scope had set nothing.
    source_version: int | None = None
    # Written into the repository as a golden: the nightly plays the file, not the case.
    kept_in_repo: bool = False
    decided_by: str | None = None
    # The group of cases its judge broke on, for this agent; None for one a person kept.
    group: str | None = Field(default=None, validation_alias="group_id", serialization_alias="group")
    # A real call, a simulation a persona played (named here), or a person who wrote it by hand.
    source: CaseSource = CaseSource.call
    persona: str | None = None

    @field_serializer("created_at")
    def _created(self, created_at: datetime) -> float:
        return created_at.timestamp()


class CaseList(Row):
    """GET /v1/evals/cases: the org's cases, by agent and name; how many wait, of how many."""

    cases: list[CaseRow]
    pending: int = 0
    # Past it a broken call is judged as ever and not kept: the inbox is for reading.
    pending_at_most: int = 0


class CaseDecision(Schema):
    """PATCH /v1/evals/cases/{id}, the body: what a person decided; each field set is written."""

    status: CaseStatus | None = None
    held_out: bool | None = None
    kept_in_repo: bool | None = None
    # With `dismissed`: the judge that should have held, written as a calibration label.
    judge_was_wrong: str | None = Field(default=None, min_length=1)
    note: str | None = None


# ── cases grouped by what broke them ──


class ProposalRow(Schema):
    """A diagnosis of a group: the cause the calls share, and the change it proposes."""

    cause: str
    # setting: applied at POST …/apply; code: handed to the developer's assistant; knowledge:
    # what the agent must be told; none: the calls show no fault of the agent's.
    kind: Literal["setting", "code", "knowledge", "none"]
    # The setting's name, the tool or prompt block, or the knowledge.
    where: str
    # The setting's new value as the settings take it; else the words of the fix.
    change: Json = None
    confidence: float = Field(ge=0.0, le=1.0)


class GroupRow(Row):
    """Cases one judge broke on for one agent: the cause, how many, and what to change."""

    id: str
    agent: str
    judge: str
    cause: str
    status: CaseStatus
    since: datetime
    cases: int
    simulations: int
    proposal: ProposalRow | None = None
    proposed_at: datetime | None = None

    @field_serializer("since", "proposed_at")
    def _epochs(self, at: datetime | None) -> float | None:
        return _as_epoch(at)


class GroupList(Row):
    """GET /v1/evals/groups: the org's groups, one agent's or every one, the pending first."""

    groups: list[GroupRow]


class GroupWhole(Row):
    """GET /v1/evals/groups/{id}: the group and every case in it."""

    group: GroupRow
    cases: list[CaseRow]


class GroupDecision(Schema):
    """PATCH /v1/evals/groups/{id}: approve or dismiss the group, and every case waiting in it."""

    status: Literal[CaseStatus.approved, CaseStatus.dismissed]
    # With `dismissed`: the group's judge should have held, a calibration label on every call.
    judge_was_wrong: bool = False
    note: str | None = None


# ── the judge judged ──


class LabelRequest(Schema):
    """POST /v1/evals/calibration, the body: what one judge should have answered on a call."""

    call: str
    judge: str = Field(min_length=1)
    # A word is no answer: "yes" was read as true and kept.
    held: bool = Field(strict=True)
    note: str | None = None


class JudgeAgreement(Row):
    """One judge against the labels people gave: how many, compared, agreed, and trusted."""

    judge: str
    labelled: int
    compared: int
    agreed: int
    rate: float | None
    # None until enough labels were compared to say; False is a judge under its line.
    trusted: bool | None


class Calibration(Row):
    """GET /v1/evals/calibration: each judge's agreement, and the line it is held to."""

    judges: list[JudgeAgreement]
    labels_to_judge: int
    agrees_at_least: float


# ── what a golden scores as ──


class JudgeScore(WireModel):
    """One judge's verdict on one golden under one model."""

    metric: str
    # livekit's scoring: a pass is 1, unsure is 0.5, a fail is 0.
    score: float
    passed: bool
    reason: str
    criteria: str
    judge_calls: int
