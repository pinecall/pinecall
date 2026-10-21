"""The bodies of the eval endpoints: a suite and its run, a replay, the simulated caller."""

from typing import Literal

from pydantic import Field

from pinecall_runtime.judging.schemas import Ambience, CallerPersona, JudgeScore
from pinecall_runtime.kit.schemas import Row, Schema
from pinecall_runtime.kit.text import Json, JsonObject
from pinecall_runtime.wire.base import WireModel
from pinecall_runtime.wire.goldens import Golden
from pinecall_runtime.wire.parts import EndReason, ModelConfig, ScoreVerdict

# A listing's page is never longer than this, whatever the reader asks; a screen when unsaid.
LONGEST_LIST = 200
A_SCREENFUL = 20

# `failed` is the run itself; a golden that failed is a score, not a status.
type RunStatus = Literal["running", "done", "failed"]


# ── a suite, its run, and the matrix it is scored into ──


class RunSuiteRequest(Schema):
    """POST /v1/evals/run, the body: the agent, its goldens and cases, the models, a version."""

    agent: str
    # Each golden is a call whose simulated caller the box pays for: two hundred at most, and two
    # hundred calls in all once the cases join and every model plays each (the endpoint counts).
    goldens: list[Golden] = Field(default_factory=list[Golden], max_length=200)
    # Cases of the org's dataset by name; a case held out is played only when named here.
    cases: list[str] = Field(default_factory=list[str], max_length=200)
    # Every case of the agent's that is not held out: the nightly run.
    dataset: bool = False
    # A version of the agent's settings in the app's scope to run instead of the one standing.
    version: int | None = Field(default=None, ge=1)
    # Empty: the model the agent declares. Each one plays every golden again: eight at most.
    models: list[ModelConfig] = Field(default_factory=list[ModelConfig], max_length=8)
    # The app socket to drive, as `WS /v1/chat?app=`; absent, the newest that holds the agent.
    app: str | None = None
    # Each golden said out loud, through the env's fleet, under this noise when named.
    voice: bool = False
    interferer_db: float | None = None
    packet_loss: float = Field(default=0.0, ge=0, le=1)
    ambience: Ambience | None = None


class OpenedCall(WireModel):
    """The call one golden opened under one model."""

    golden: str
    model: str
    call: str


# `asked` is set on a cell that did not hold, and null when the run kept no requests.
class ScoreRow(WireModel):
    """Every judge's verdict on one golden under one model, and the call's own summary."""

    model: str
    golden: str
    scores: list[JudgeScore]
    summary: JsonObject | None
    asked: list[JsonObject] | None = None


class Failure(WireModel):
    """One judge that did not hold, and the cell it broke on."""

    model: str
    golden: str
    metric: str


class ScoreMatrix(WireModel):
    """Models by goldens: the axes in the order the cells came, one row per cell."""

    models: list[str]
    goldens: list[str]
    metrics: list[str]
    # A count, not a price: a judge's tokens are billed with the rest of the model usage.
    judge_calls: int
    runs: list[ScoreRow]
    failures: list[Failure]


# The run's document: written whole at every change, so a run is followed while it goes.
class RunRow(WireModel):
    """An eval run: the calls it opened, the matrix judged so far, and why it stopped early."""

    id: str
    agent: str
    started_at: float
    finished_at: float | None
    status: RunStatus
    calls: list[OpenedCall]
    matrix: ScoreMatrix | None
    error: str | None


class RunList(Row):
    """GET /v1/evals/runs: the runs of the key's org and env, newest first."""

    runs: list[RunRow]


class RunListQuery(Schema):
    """What a list of runs asks for: one agent's or every one, since when, how many."""

    agent: str | None = None
    since: float = Field(0.0, ge=0)
    limit: int = Field(A_SCREENFUL, ge=1, le=LONGEST_LIST)


class JudgeQuery(Schema):
    """Whether a call judged already is judged again, and paid for again."""

    again: bool = False


class GoldenQuery(Schema):
    """What a call read as a golden is named, and the seq it is cut at."""

    name: str | None = Field(default=None, min_length=1)
    from_seq: int = Field(default=0, ge=0)


# ── a finished call checked again ──


class ReplayCallRequest(Schema):
    """POST /v1/evals/replay/{call}, the body: the words banned and the latency budget."""

    banned: list[str] = Field(default_factory=list[str])
    budget: dict[str, float] = Field(default_factory=dict[str, float])


class CheckVerdict(WireModel):
    """One code check's answer: its name, its status and why."""

    check: str
    status: ScoreVerdict
    detail: str


class ReplayCallResponse(Row):
    """POST /v1/evals/replay/{call}, the answer: the six checks and whether none broke."""

    call: str
    agent: str
    passed: bool
    verdicts: list[CheckVerdict]


# ── the simulated caller ──


class Spoken(WireModel):
    """One turn of the call as the caller heard it."""

    who: Literal["agent", "caller"]
    said: str = Field(max_length=4000)


class NextLineRequest(Schema):
    """POST /v1/evals/caller, the body: the persona, the call so far, the turns left."""

    persona: CallerPersona
    # Two turns for each of the forty a call may take, and no more.
    heard: list[Spoken] = Field(default_factory=list[Spoken], max_length=80)
    turns_left: int = Field(default=1, ge=0, le=40)


class NextLineResponse(Row):
    """The caller's next line, and whether it hangs up after it."""

    say: str
    hangup: bool = False


class PlaceVoiceCallRequest(Schema):
    """POST /v1/evals/voice, the body: the room, the agent, the persona, and the line."""

    # Minted by the client, as the box mints one (`call_` and a word), so it tails the log before
    # the call starts; the endpoint takes it only for a call nobody opened yet.
    call: str = Field(pattern=r"^call_[A-Za-z0-9]{1,64}$")
    agent: str
    persona: CallerPersona
    # The caller's lines, each paid for by the box (its model and its voice): forty at most.
    turns: int = Field(default=6, ge=1, le=40)
    # dB of the ambience under the caller's voice; absent is a clean line. The ambience named
    # plays instead of the persona's own.
    interferer_db: float | None = None
    packet_loss: float = Field(default=0.0, ge=0, le=1)
    ambience: Ambience | None = None
    # The state the agent opens the call in: the persona's, as `pinecall simulate` reads it.
    state: JsonObject = Field(default_factory=dict[str, Json])


class PlaceVoiceCallResponse(Row):
    """POST /v1/evals/voice, the answer: how many lines the caller said, and on what line."""

    call: str
    turns: int
    line: str
    # What the caller's lines and voice cost, in US dollars, by the box's rates.
    caller_cost_usd: float = 0.0
    # The caller hung up because its call had spent the providers row's `caller.ceiling_usd`.
    stopped_at_ceiling: bool = False


class PlayedBy(Schema):
    """Who plays the caller for one run, over the persona's own; each unsaid stays the persona's."""

    # `vendor/model`, a vendor whose voices the caller is read in, and one of its voices' ids.
    llm: str | None = None
    tts: str | None = None
    voice: str | None = None


class SimulationRequest(Schema):
    """POST /v1/simulations, the body: the agent, one of its personas, a written or spoken line."""

    agent: str
    persona: str
    # Spoken: a real line, the caller in a voice of its own. Written: the chat the widget has.
    voice: bool = True
    # The caller's lines, each paid for by the box: forty at most, fifteen when not said.
    turns: int = Field(default=15, ge=1, le=40)
    # Spoken alone: dB of the ambience under the caller's voice, which ambience, and the share
    # of packets lost; each unsaid is the persona's own.
    interferer_db: float | None = None
    packet_loss: float = Field(default=0.0, ge=0, le=1)
    ambience: Ambience | None = None
    # The model, the voice's vendor and the voice this run alone is played on.
    played_by: PlayedBy | None = None


class SimulationStarted(Row):
    """POST /v1/simulations, the answer: the call it plays on, watched like any call."""

    call: str
    voice: bool


class SessionScore(WireModel):
    """What the judges said of a simulated call, as its list row carries it."""

    held: int
    judged: int
    passed: bool
    reason: str | None


class PersonaRunRow(Row):
    """One call a persona made: who played it, to whom, when, how it ended, what it cost."""

    call: str
    agent: str
    # Every simulated call names its persona; the facts' column is empty only for a person's call.
    persona: str | None
    started_at: float
    ended_at: float | None
    turns: int
    end_reason: EndReason | None
    outcome: str | None
    cost_usd: float | None
    score: SessionScore | None
    # Who played the caller as it ran (`vendor/model` of its lines and its voice, and the voice),
    # and what that cost; None for a call simulated before the runtime kept it.
    played_by: PlayedBy | None = None
    caller_cost_usd: float = 0.0


class PersonaRunList(Row):
    """A page of simulated calls, newest first: one persona's, or the env's (/v1/simulations)."""

    runs: list[PersonaRunRow]
    total: int
    next: str | None


class PersonaRunQuery(Schema):
    """Where a persona's runs continue, and how many."""

    limit: int = Field(A_SCREENFUL, ge=1, le=LONGEST_LIST)
    before: str | None = None


class SimulationQuery(PersonaRunQuery):
    """Every simulated call, or the agents named's: where the page continues, and how many."""

    agent: list[str] = Field(default_factory=list[str])
    # One simulated call, by its id.
    call: str | None = None
