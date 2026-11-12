"""The bodies of the insights endpoints: a window of days at a glance, the series, tools, slow turns, drift."""

from datetime import date

from pydantic import Field

from runtime.enums import Env, Stage
from runtime.kit.schemas import Epoch, Row, Schema

# ── a window at a glance ──


class InsightsConversations(Row):
    """How many calls started in the window, and in the window of the same length before it."""

    now: int
    before: int


class InsightsChannels(Row):
    """The window's calls by the channel they came in on."""

    phone: int
    web: int
    whatsapp: int


class InsightsSpend(Row):
    """What one agent's window cost by stage, in US dollars, and per minute of its ended calls."""

    llm_usd: float
    stt_usd: float
    tts_usd: float
    phone_usd: float
    platform_usd: float
    minutes: float
    per_minute_usd: float | None


class InsightsAgent(Row):
    """One agent's window: its calls, the share of judgments it held, what it cost by stage."""

    slug: str
    calls: int
    score: float | None
    spend: InsightsSpend


class InsightsStage(Row):
    """One stage of the window's turns on one vendor and model: how slow, how sure the ears were."""

    stage: Stage
    vendor: str | None
    model: str | None
    turns: int
    median_s: float | None
    p95_s: float | None
    confidence: float | None


class InsightsBudget(Row):
    """What the org may spend in a month and what it has spent so far, both envs together."""

    limit_usd: int | None
    spent_usd_month: float


class InsightsEnding(Row):
    """One way the window's calls ended, and how many did."""

    reason: str
    count: int


class InsightsDay(Row):
    """One UTC day of the window: its calls by channel, what they cost, how their judges answered."""

    day: date
    phone: int
    web: int
    whatsapp: int
    spend_usd: float
    judged: int
    passed: int


class Insights(Row):
    """GET /v1/insights: whole UTC days of the key's env and scope, counted off the call index."""

    day: date
    days: int
    timezone: str
    conversations: InsightsConversations
    resolved_rate: float | None
    median_e2e_s: float | None
    spend_usd: float
    channels: InsightsChannels
    judged: int
    passed: int
    escalated: int
    mean_length_s: float | None
    endings: list[InsightsEnding]
    series: list[InsightsDay]
    sessions_total: int
    live: int
    agents: list[InsightsAgent]
    stages: list[InsightsStage]
    budget: InsightsBudget


# ── the series ──


class SeriesStage(Row):
    """One stage over one day's turns: how many, and how slow at the median and the tail."""

    stage: Stage
    turns: int
    median_s: float | None
    p95_s: float | None


class SeriesJudge(Row):
    """One judge over one day: the verdicts that held, and those settled."""

    name: str
    held: int
    judged: int


# Two of a day's numbers are read under the names alerts' monitors read them by (`service/windows.py`:
# `SeriesDay`); the wire's names are the fields'.
class SeriesDay(Row):
    """One UTC day of the window, every number the Observability screen draws."""

    day: date
    calls: int
    finished: int
    escalated: int
    spend_usd: float = Field(validation_alias="spent")
    mean_length_s: float | None
    e2e_median_s: float | None = Field(validation_alias="e2e_median")
    e2e_p95_s: float | None
    endings: list[InsightsEnding]
    stages: list[SeriesStage]
    judges: list[SeriesJudge]
    tools_ran: int
    tools_failed: int


class SeriesVendor(Row):
    """One stage on one vendor and model over the whole window: its turns, median and p95."""

    stage: Stage
    vendor: str
    model: str | None
    turns: int
    median_s: float | None
    p95_s: float | None


class Series(Row):
    """GET /v1/insights/series: the window day by day, every number a chart draws."""

    day: date
    days: int
    agent: str | None
    timezone: str
    series: list[SeriesDay]
    vendors: list[SeriesVendor]


# ── tools ──


class ToolError(Row):
    """The newest failure of a tool over the window: the call, when it was written, its error."""

    call: str
    at: float
    text: str


class ToolStat(Row):
    """One tool over the window: its results, those that failed, its median seconds, its last failure."""

    name: str
    ran: int
    failed: int
    median_s: float | None
    last_error: ToolError | None


class ToolsReport(Row):
    """GET /v1/insights/tools: every tool of the window, the most failed first."""

    day: date
    days: int
    agent: str | None
    tools: list[ToolStat]


# ── the slowest turns ──


class SlowTurn(Row):
    """One turn the caller waited long for, and where the wait went."""

    call: str
    agent: str
    seq: int
    name: str | None
    at: float
    e2e_s: float
    hears_s: float | None
    thinks_s: float | None
    tools_s: float | None
    speaks_s: float | None


class SlowTurns(Row):
    """GET /v1/insights/slow: the window's slowest turns, the slowest first."""

    day: date
    days: int
    agent: str | None
    turns: list[SlowTurn]


# ── drift ──


class DriftSide(Row):
    """One side of a drift as asked: a day, a version; and the versions its calls ran."""

    day: date | None
    version: int | None
    versions: list[int]


class JudgeTally(Row):
    """One judge on one side: its verdicts that held, those settled, and the share that held."""

    held: int
    judged: int
    pass_rate: float | None


class DriftJudge(Row):
    """One judge on both sides, how far its pass rate moved, and whether its question changed."""

    name: str
    before: JudgeTally | None
    after: JudgeTally | None
    moved: float | None
    criteria_changed: bool


class StageTally(Row):
    """One stage on one side: its turns, median and p95 in seconds, the ears' confidence."""

    turns: int
    median_s: float | None
    p95_s: float | None
    confidence: float | None


class DriftStage(Row):
    """One stage on one vendor and model on both sides, and how far its median and p95 moved."""

    stage: Stage
    vendor: str | None
    model: str | None
    before: StageTally | None
    after: StageTally | None
    median_moved_s: float | None
    p95_moved_s: float | None


class DriftVersion(Row):
    """A version of the agent's settings a side ran or that was set between: who, when, why."""

    version: int
    holder: str
    author: str
    note: str | None
    set_at: Epoch
    ran_before: bool
    ran_after: bool


# `world` is the wire's word for the env, which the console reads.
class Drift(Row):
    """GET /v1/insights/drift: what moved between two days or versions of an agent, and why."""

    agent: str
    world: Env = Field(validation_alias="env")
    before: DriftSide
    after: DriftSide
    judges: list[DriftJudge]
    stages: list[DriftStage]
    versions: list[DriftVersion]


# ── what is asked ──


class InsightsQuery(Schema):
    """What insights count: the window's last day (today), its days, one agent or every one."""

    day: date | None = None
    days: int = 1
    agent: str | None = None


# FastAPI reads a query model flat only when it is an endpoint's one query parameter.
class SlowQuery(InsightsQuery):
    """What the slowest turns count: the insights' window, and how many turns to list."""

    limit: int = Field(10, ge=1, le=50)


class DriftQuery(Schema):
    """What a drift compares: an agent, two days (today and the day before) or two versions."""

    agent: str
    before: str | None = None
    after: str | None = None
