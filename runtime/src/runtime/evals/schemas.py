"""The bodies of the eval endpoints: a suite and its run, a replay, a simulation, a comparison, the calibration."""

from collections.abc import Sequence
from typing import Any, Literal, Self

from pydantic import Field

from runtime.judging import service as judging
from runtime.kit.schemas import Row, Schema
from runtime.kit.text import Json, JsonObject
from runtime.wire.declaration import CallerBehavior, ModelConfig
from runtime.wire.goldens import Golden
from runtime.wire.parts import Ambience, EndOfTurn, EndReason, ScoreVerdict
from runtime.wire.runs import Run

# A listing's page is never longer than this, whatever the reader asks; a screen when unsaid.
LONGEST_LIST = 200
A_SCREENFUL = 20

# ── a suite and its run ──


class RunSuiteRequest(Schema):
    """POST /v1/evals/run, the body: the agent, its goldens and cases, the models, a version."""

    agent: str
    # Each golden is a call whose simulated caller the box pays for: two hundred at most, and two
    # hundred calls in all once the cases join and every model plays each (the service counts).
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
    interferer_db: float | None = Field(default=None, ge=0, le=60)
    packet_loss: float = Field(default=0.0, ge=0, le=1)
    ambience: Ambience | None = None


class RunList(Row):
    """GET /v1/evals/runs: the runs of the key's org and env, newest first."""

    runs: list[Run]


class RunListQuery(Schema):
    """What a list of runs asks for: one agent's or every one, since when, how many."""

    agent: str | None = None
    since: float = Field(0.0, ge=0)
    limit: int = Field(A_SCREENFUL, ge=1, le=LONGEST_LIST)


# ── a finished call checked or judged again ──


class ReplayCallRequest(Schema):
    """POST /v1/evals/replay/{call}, the body: the words banned and the latency budget."""

    banned: list[str] = Field(default_factory=list[str])
    budget: dict[str, float] = Field(default_factory=dict[str, float])


class CheckVerdict(Row):
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


class Spoken(Schema):
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


class AgentValues(Schema):
    """The voice and models a run puts the agent on, over its settings, as a test room asks them."""

    # Each stage as `vendor/model`, a voice of the voice vendor's, a language, a temperature, who ends the turn.
    stt: str | None = None
    llm: str | None = None
    tts: str | None = None
    voice: str | None = None
    language: str | None = None
    temperature: float | None = None
    end_of_turn: EndOfTurn | None = None


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
    interferer_db: float | None = Field(default=None, ge=0, le=60)
    packet_loss: float = Field(default=0.0, ge=0, le=1)
    ambience: Ambience | None = None
    # Seconds of silence before each of the caller's lines, over the persona's own; 0 answers at once.
    pause_s: float | None = Field(default=None, ge=0, le=judging.LONGEST_PAUSE_S)
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


# ── a simulation ──


class PlayedBy(Schema):
    """Who plays the caller for one run, over the persona's own; each unsaid stays the persona's."""

    # `vendor/model`, a vendor whose voices the caller is read in, and one of its voices' ids.
    llm: str | None = None
    tts: str | None = None
    voice: str | None = None


class Scenario(Schema):
    """What the caller phones about this run: a goal in the first person, and the facts that goal needs."""

    goal: str = Field(min_length=1, max_length=4000)
    facts: dict[str, str] = Field(default_factory=dict[str, str])


class SimulationWants(Schema):
    """What a simulation is placed with: the agent, one of its personas, a written or spoken line, who plays it."""

    agent: str
    persona: str
    # Spoken: a real line, the caller in a voice of its own. Written: the chat the widget has.
    voice: bool = True
    # The caller's lines, each paid for by the box: forty at most, fifteen when not said.
    turns: int = Field(default=15, ge=1, le=40)
    # Spoken alone: dB of the ambience under the caller's voice, which ambience, and the share
    # of packets lost; each unsaid is the persona's own.
    interferer_db: float | None = Field(default=None, ge=0, le=60)
    packet_loss: float = Field(default=0.0, ge=0, le=1)
    ambience: Ambience | None = None
    # Spoken alone: seconds of silence before each of the caller's lines, over the persona's own; 0 for
    # a caller that answers at once, as a preview wants.
    pause_s: float | None = Field(default=None, ge=0, le=judging.LONGEST_PAUSE_S)
    # The model, the voice's vendor and the voice this run alone is played on.
    played_by: PlayedBy | None = None
    # What the caller phones about this run, over the persona's goal: what `/brief` wrote and a person
    # read, or edited, before the call. Given, a caller of the library is not briefed again.
    scenario: Scenario | None = None


class SimulationRequest(SimulationWants):
    """POST /v1/simulations, the body: one simulation, and the agent's own voice and models for it, if any."""

    # The voice and models the agent runs on for this call alone, over its settings: the sandbox's, a
    # key that edits the pipeline, as a test room's are.
    against: AgentValues | None = None


class SimulationStarted(Row):
    """POST /v1/simulations, the answer: the call it plays on, watched like any call."""

    call: str
    voice: bool


class SessionScore(Row):
    """What the judges said of a simulated call, as its list row carries it."""

    held: int
    judged: int
    passed: bool
    reason: str | None


class PlayedByRow(Row):
    """Who played the caller as it ran: `vendor/model` of its lines and of its voice, and the voice."""

    llm: str | None = None
    tts: str | None = None
    voice: str | None = None


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
    # None for a call simulated before the runtime kept who played it.
    played_by: PlayedByRow | None = None
    caller_cost_usd: float = 0.0
    # What the agent ran on over its settings, and the comparison the call was placed in.
    against: dict[str, Any] | None = None
    comparison: str | None = None
    # How a spoken call was heard, against what its caller really said; None for a written one.
    hearing: dict[str, Any] | None = None


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
    # The calls of one comparison, by its id.
    comparison: str | None = None


class SimulationLimits(Row):
    """GET /v1/simulations/limits: how the key's org may shape its simulations in the env."""

    # The simulated calls it may have on the line at once, and how many are on it now.
    at_once: int
    on_the_line: int
    # The calls one comparison may place: callers times setups times repeats.
    comparison_calls: int


# ── a comparison ──


class ComparisonRequest(SimulationWants):
    """POST /v1/simulations/compare, the body: a persona or more, the agent under each of these, placed together."""

    against: list[AgentValues] = Field(min_length=1, max_length=10)
    # More callers beside `persona`, each against every configuration as it is: one call per pair.
    more_personas: list[str] = Field(default_factory=list[str], max_length=9)
    # How many times each caller rings the agent under each configuration: one call tells whether a
    # model can do a task, several how often it does.
    repeats: int = Field(default=1, ge=1, le=10)


class ComparedCall(Row):
    """One call a comparison placed: the caller, what the agent runs on, and the call."""

    persona: str
    against: dict[str, Any]
    call: str


class ComparedRefusal(Row):
    """One call a comparison could not place, and the refusal in the gateway's words."""

    persona: str
    against: dict[str, Any]
    why: str


class ComparisonStarted(Row):
    """POST /v1/simulations/compare, the answer: the comparison's id, each call placed, what was refused."""

    comparison: str
    voice: bool
    calls: list[ComparedCall]
    refused: list[ComparedRefusal]
    # The calls that wait for a place on the line: placed by the gateway as the ones before them end.
    waiting: int = 0

    # The wire says `voice` where the package says `spoken`.
    @classmethod
    def of_begun(cls, begun: Any) -> Self:
        """The body a comparison just started answers as."""
        said = {"comparison": begun.comparison, "voice": begun.spoken, "calls": begun.calls}
        return cls.model_validate({**said, "refused": begun.refused, "waiting": begun.waiting}, from_attributes=True)


class Latency(Row):
    """A turn's measures over one call, each its median in seconds; one no turn reported is null."""

    e2e_latency: float | None
    llm_node_ttft: float | None
    tts_node_ttfb: float | None
    transcription_delay: float | None
    end_of_turn_delay: float | None


class RowVerdict(Row):
    """One judge's answer on one call of a comparison: its name, what it said, and why."""

    name: str
    verdict: ScoreVerdict
    reason: str


class ComparisonRow(Row):
    """One call of a comparison: the caller, what the agent ran on, how it went, what it cost, how fast it was."""

    call: str
    persona: str
    against: dict[str, Any]
    started_at: float
    ended_at: float | None
    turns: int
    end_reason: EndReason | None
    score: SessionScore | None
    cost_usd: float | None
    latency: Latency
    # Why the call ended before it began, from the log's `error`; None for a call that ran.
    why: str | None
    # Whether the caller got what it expected of the agent; None until the call is scored.
    goal: ScoreVerdict | None = None
    # Each judge's answer, in the order the panel asked them; empty until the call is scored.
    judges: list[RowVerdict] = Field(default_factory=list[RowVerdict])
    # The agent's replies, the slowest of them end to end in seconds, and how many the caller cut off.
    replies: int = 0
    slowest_reply: float | None = None
    cut_off: int = 0
    # How the call was heard, against what its caller really said; None for a written call.
    hearing: dict[str, Any] | None = None


class Comparison(Row):
    """GET /v1/simulations/compare/{id}: the calls of one comparison, each caller's best first."""

    comparison: str
    agent: str
    # The first caller; `personas` is every one, in the order they were placed.
    persona: str
    personas: list[str]
    voice: bool
    rows: list[ComparisonRow]
    # What was asked for: the agent's values of each column in the order named, and how many times
    # each caller rings under each. Empty and one for a comparison made before they were kept.
    against: list[dict[str, Any]] = Field(default_factory=list[dict[str, Any]])
    repeats: int = 1
    # Every call it was to place, the ones still waiting for a place on the line, and what was refused.
    planned: int = 0
    waiting: int = 0
    refused: list[ComparedRefusal] = Field(default_factory=list[ComparedRefusal])
    # The gateway placing the ones that wait stopped before it placed them all: they never will be.
    abandoned: bool = False

    @classmethod
    def of_read(cls, plan: Any, rows: Sequence[Any], *, planned: int, abandoned: bool) -> Self:
        """The body a comparison read answers as: what was asked for, how its placing stands, its calls."""
        said = {
            "comparison": plan.comparison,
            "agent": plan.agent,
            "persona": plan.personas[0],
            "personas": plan.personas,
            "voice": plan.spoken,
            "rows": rows,
            "against": plan.against,
            "repeats": plan.repeats,
            "planned": planned,
            "waiting": plan.waiting,
            "refused": plan.refused,
            "abandoned": abandoned,
        }
        return cls.model_validate(said, from_attributes=True)


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
