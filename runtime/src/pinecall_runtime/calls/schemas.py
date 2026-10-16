"""The bodies of the call endpoints: readers, tokens, codes, seats, the worker's writes, threads."""

from datetime import date
from typing import Literal

from pydantic import Field

from pinecall_runtime.calls.context import CallContext
from pinecall_runtime.enums import Channel, Direction, Env, Stage
from pinecall_runtime.kit.schemas import Schema
from pinecall_runtime.kit.text import Json, JsonObject
from pinecall_runtime.wire.base import BatchedEntry, Entry, WireModel
from pinecall_runtime.wire.metrics import ModelUsage
from pinecall_runtime.wire.parts import (
    CallStatus,
    Contact,
    Cost,
    EndReason,
    PlatformTool,
    Projection,
    SessionFlag,
    ThreadKind,
)
from pinecall_runtime.wire.state import AttentionState

# A listing's page is never longer than this, whatever the reader asks.
LONGEST_LIST = 200
# A screen of a listing, when the reader names no size.
A_SCREENFUL = 20
# A log's page, when the reader names no size.
DEFAULT_LIMIT = 500
# An inbox's page of contacts.
THREADS_A_PAGE = 30


# Projected entries keep only part of the envelope, so they travel as plain JSON.
class LogPage(WireModel):
    """One page of a log: the entries above the cursor, and where the next page starts."""

    entries: list[JsonObject]
    live: bool
    next: int | None


class SessionScore(WireModel):
    """What the judges said of a call, as a list row carries it."""

    held: int
    judged: int
    passed: bool
    reason: str | None


class CallRow(WireModel):
    """One call as a list shows it."""

    call: str
    agent: str
    live: bool
    last_seq: int
    status: CallStatus
    channel: Channel | None
    direction: Direction | None
    from_: str | None = Field(alias="from")
    to: str | None
    caller: Contact | None
    started_at: float | None
    ended_at: float | None
    end_reason: EndReason | None
    outcome: str | None
    cost: Cost | None
    score: SessionScore | None = None
    flags: list[SessionFlag] | None = None
    attention: AttentionState | None = None


class CallList(WireModel):
    """A page of calls, newest first."""

    calls: list[CallRow]
    total: int | None = None
    next: str | None = None


class MintTokenRequest(WireModel):
    """livekit's token request body, and ours beside it."""

    agent: str | None = None
    scope: str = "talk"
    # An opaque contact id; never a number or a name.
    contact: str | None = None
    # Reaches the worker inside the signed dispatch: the browser reads it, never changes it.
    metadata: JsonObject = Field(default_factory=dict[str, Json])
    ttl_s: int | None = None
    log: Projection = "public"
    participant_identity: str | None = None
    participant_attributes: dict[str, str] = Field(default_factory=dict[str, str])
    room_config: JsonObject | None = None
    # An earlier answer's resume_token: back into that call while it waits, else one carrying it on.
    resume: str | None = None
    # Declared so they are refused with the reason instead of an unknown key.
    room_name: str | None = None
    participant_name: str | None = None
    participant_metadata: str | None = None


class MintTokenResponse(WireModel):
    """livekit's token response, the call it opens and a token that reads its log."""

    server_url: str
    participant_token: str
    call: str
    log_token: str
    # What the browser keeps to carry this conversation on later: `resume` in a mint.
    resume_token: str


class IssueCodeRequest(WireModel):
    """Four digits a caller keys to tie their call to a page."""

    agent: str
    ttl_s: int = Field(default=600, ge=60, le=1800)
    log: Projection = "public"


class IssueCodeResponse(WireModel):
    """A code issued: the digits, the number to call, and the token its page polls with."""

    code: str
    number: str
    expires_at: float
    code_token: str


class CodeStatus(WireModel):
    """How a code stands; claimed, it names the call and a token that reads it."""

    code: str
    status: Literal["waiting", "claimed", "expired"]
    expires_at: float
    call: str | None
    log_token: str | None


class SeatResponse(WireModel):
    """A seat in a live call: the server, the token, and who it says the person is."""

    server_url: str
    participant_token: str
    call: str
    identity: str
    org: str
    subject: str | None
    name: str | None


class VerbResponse(WireModel):
    """A supervise verb queued; the call's log says what it did."""

    call: str
    verb: str
    seq: int | None


class OpenCallRequest(WireModel):
    """What a worker opens a call with, and says again to a gateway that forgot it."""

    agent: str
    context: CallContext
    # The app socket that must serve it (a spoken golden run); else the one the call reaches.
    app: str | None = None
    # The Twilio account an inbound leg says it came from (X-Twilio-AccountSid); None from any
    # other carrier, or from a worker of an older release.
    carrier_account: str | None = None


class OpenCallResponse(WireModel):
    """What the org's minutes leave the call (null for no limit), and what it says first."""

    seconds_left: int | None
    minutes: int | None
    # An outbound call's AI disclosure, and the notice a recorded call says; null for none.
    disclosure: str | None = None
    recording_notice: str | None = None
    # The turns of the call this one continues, oldest first; empty for a call of its own.
    history: list[Entry] = Field(default_factory=list[Entry])


class AppendEntryRequest(WireModel):
    """One entry a worker writes to its call's log."""

    type: str
    data: JsonObject
    ephemeral: bool | None = None


# `after` makes a retry safe: the log answers a batch it already took with the seqs it gave it.
class AppendEntriesRequest(WireModel):
    """A worker's entries of its call, in order, after how many the log already took from it."""

    after: int = Field(ge=0)
    entries: list[BatchedEntry]


class AppendEntriesResponse(WireModel):
    """A worker's batch as the log numbered it, in the order it was sent."""

    entries: list[Entry]


# On the entries socket, where a refusal is a frame and not a status: the socket stays open.
class AppendEntriesRefused(WireModel):
    """A batch the gateway refused, with the sentence and the status a request would get."""

    refused: str
    status: int


# `input` is whole and unread by the wire: what recall and search take is the runtime's shape.
class LookupRequest(WireModel):
    """Which platform tool to run for a call's turn, what to run it with, and the turn it joins."""

    tool: PlatformTool
    input: JsonObject
    speech_id: str | None = None


class LookupResponse(WireModel):
    """What the tool found, as the model reads it, and how long finding it took."""

    output: JsonObject
    took_ms: float


class RememberResponse(WireModel):
    """How many memory operations a call produced, and how long remembering took."""

    ops: int
    took_ms: float


class RecordingKeyResponse(WireModel):
    """The key a call's recording is sealed under before it is stored: 32 bytes, base64url."""

    key: str


class SealCallRequest(WireModel):
    """The end of a call as its worker hands it to the gateway, which prices, judges and seals."""

    usage: list[ModelUsage]
    outcome: str
    recording: str | None = None
    # The vendors that ran on the box's own key: the operator bills their usage.
    lent: list[str] = Field(default_factory=list[str])


class CallbackRequest(WireModel):
    """Somebody the overflow told to wait for a call back."""

    agent: str
    channel: Channel
    number: str
    call: str | None = None


class CallbackRow(WireModel):
    """One call back somebody asked for, as the org's list shows it."""

    position: int
    agent: str
    ts: float
    channel: Channel
    number: str
    via: Literal["overflow", "widget", "agent"]
    call: str | None
    when: str | None = None
    note: str | None = None
    contact: Contact | None = None


class CallbackList(WireModel):
    """A page of the org's callbacks, oldest first, and where the next starts."""

    requests: list[CallbackRow]
    next: int | None


class ThreadLast(WireModel):
    """The newest thing on a contact's thread."""

    text: str | None
    at: float
    kind: ThreadKind


class ThreadRow(WireModel):
    """One contact of an agent's inbox: every call of theirs, folded into one line."""

    contact: str
    name: str | None
    channel_last: Channel
    last: ThreadLast
    unread: int
    calls: int


class ThreadList(WireModel):
    """GET /v1/agents/{slug}/threads: the agent's contacts, the newest thread first."""

    threads: list[ThreadRow]
    next: str | None


class ThreadMessage(WireModel):
    """One message of a thread, or one spoken call drawn as a pill."""

    kind: ThreadKind
    text: str | None
    at: float
    call: str
    channel: Channel
    duration_s: float | None = None
    answered: bool | None = None


class ThreadResponse(WireModel):
    """GET /v1/agents/{slug}/threads/{contact}: every call of one contact, merged, oldest first."""

    contact: str
    name: str | None
    messages: list[ThreadMessage]


class ThreadMessageRequest(WireModel):
    """POST /v1/agents/{slug}/threads/{contact}/messages, the body."""

    text: str


class ThreadMessageResponse(WireModel):
    """POST /v1/agents/{slug}/threads/{contact}/messages, the answer: the call it was said on."""

    contact: str
    call: str


class PromptBlockRow(WireModel):
    """One block of a call's prompt as its log names it, with the words the org kept of it."""

    seq: int
    name: str
    hash: str
    chars: int
    # Null for a block no gateway kept the words of (a call from before they were kept).
    text: str | None


class CallPromptResponse(WireModel):
    """GET /v1/calls/{call}/prompt: every block the call was told, in the order it was told."""

    call: str
    blocks: list[PromptBlockRow]


class CallbackQuery(Schema):
    """Where the org's list of callbacks continues, and whose."""

    after: int = 0
    agent: str | None = None


class TokenQuery(Schema):
    """A query a page may carry its call's token in: EventSource sets no header, so the token rides
    the URL. The reading dependency reads it (`calls/auth.py`); it is named here so the query, which
    refuses every name it does not know, lets it through."""

    token: str | None = None


class LogQuery(TokenQuery):
    """What a log's reader asks for: the cursor, the types, only what is kept, a page's size."""

    after: int = Field(0, ge=0)
    types: str | None = None
    durable: bool = False
    limit: int = Field(DEFAULT_LIMIT, ge=1, le=DEFAULT_LIMIT)


class ListQuery(Schema):
    """What a list of calls asks for: an agent, words, a channel, a page below a call."""

    limit: int = Field(A_SCREENFUL, ge=1, le=LONGEST_LIST)
    q: str | None = Field(None, max_length=200)
    agent: str | None = None
    channel: str | None = None
    before: str | None = None


class ThreadQuery(Schema):
    """One page of an inbox: after the cursor of the last one, so many contacts."""

    after: str | None = None
    limit: int = Field(THREADS_A_PAGE, ge=1, le=LONGEST_LIST)


class CodeQuery(TokenQuery):
    """Whether a page's ask waits for its code to be keyed."""

    wait: bool = False


# ── what the org used: the usage feed ──


class UsageTotals(WireModel):
    """What was consumed: calls, minutes, turns, tokens, characters, judges asked, the cost."""

    calls: int
    minutes: float
    messages: int
    input_tokens: int
    output_tokens: int
    characters: int
    judge_calls: int
    evals: int
    simulations: int
    cost_usd: float


# Flat, as v1 wrote it: a billing layer that reads the feed today reads it unchanged.
class UsageRow(WireModel):
    """One metered entry: whose it was, which call, what it consumed, and where the feed is."""

    cursor: int
    org: str
    agent: str
    call: str
    type: str
    at: float
    minutes: float
    messages: int
    input_tokens: int
    output_tokens: int
    characters: int
    judge_calls: int
    evals: int
    # A call.summary of a call a simulated caller played: billed as one simulation, not minutes.
    simulated: bool
    cost_usd: float


class UsagePage(WireModel):
    """GET /v1/usage: the org's metered rows after the cursor, their totals, the next cursor."""

    rows: list[UsageRow]
    totals: UsageTotals | None
    next: int | None


class BoxUsagePage(WireModel):
    """GET /v1/ops/usage: every org's metered rows after the cursor, totals per org, the next."""

    rows: list[UsageRow]
    totals: dict[str, UsageTotals]
    next: int | None


class BoxEvent(WireModel):
    """One frame of GET /v1/ops/events: an entry of some org's floor, whose, and in which env."""

    org: str
    env: Env | None = None
    entry: Entry


# ── a window of days: insights, the series, drift ──


class InsightsConversations(WireModel):
    """How many calls started in the window, and in the window of the same length before it."""

    now: int
    before: int


class InsightsChannels(WireModel):
    """The window's calls by the channel they came in on."""

    phone: int
    web: int
    whatsapp: int


class InsightsSpend(WireModel):
    """What one agent's window cost by stage, in US dollars, and per minute of its ended calls."""

    llm_usd: float
    stt_usd: float
    tts_usd: float
    phone_usd: float
    platform_usd: float
    minutes: float
    per_minute_usd: float | None


class InsightsAgent(WireModel):
    """One agent's window: its calls, the share of judgments it held, what it cost by stage."""

    slug: str
    calls: int
    score: float | None
    spend: InsightsSpend


class InsightsStage(WireModel):
    """One stage of the window's turns on one vendor and model: how slow, how sure the ears were."""

    stage: Stage
    vendor: str | None
    model: str | None
    turns: int
    median_s: float | None
    p95_s: float | None
    confidence: float | None


class InsightsBudget(WireModel):
    """What the org may spend in a month and what it has spent so far, both envs together."""

    limit_usd: int | None
    spent_usd_month: float


class InsightsEnding(WireModel):
    """One way the window's calls ended, and how many did."""

    reason: str
    count: int


class InsightsDay(WireModel):
    """One UTC day of the window: its calls by channel, what they cost, how their judges answered."""

    day: str
    phone: int
    web: int
    whatsapp: int
    spend_usd: float
    judged: int
    passed: int


class Insights(WireModel):
    """GET /v1/insights: whole UTC days of the key's env and scope, counted off the call index."""

    day: str
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


class SeriesStage(WireModel):
    """One stage over one day's turns: how many, and how slow at the median and the tail."""

    stage: Stage
    turns: int
    median_s: float | None
    p95_s: float | None


class SeriesJudge(WireModel):
    """One judge over one day: the verdicts that held, and those settled."""

    name: str
    held: int
    judged: int


class SeriesDay(WireModel):
    """One UTC day of the window, every number the Observability screen draws."""

    day: str
    calls: int
    finished: int
    escalated: int
    spend_usd: float
    mean_length_s: float | None
    e2e_median_s: float | None
    e2e_p95_s: float | None
    endings: list[InsightsEnding]
    stages: list[SeriesStage]
    judges: list[SeriesJudge]
    tools_ran: int
    tools_failed: int


class Series(WireModel):
    """GET /v1/insights/series: the window day by day, every number a chart draws."""

    day: str
    days: int
    agent: str | None
    timezone: str
    series: list[SeriesDay]


class DriftSide(WireModel):
    """One side of a drift as asked: a day, a version; and the versions its calls ran."""

    day: str | None
    version: int | None
    versions: list[int]


class JudgeTally(WireModel):
    """One judge on one side: its verdicts that held, those settled, and the share that held."""

    held: int
    judged: int
    pass_rate: float | None


class DriftJudge(WireModel):
    """One judge on both sides, how far its pass rate moved, and whether its question changed."""

    name: str
    before: JudgeTally | None
    after: JudgeTally | None
    moved: float | None
    criteria_changed: bool


class StageTally(WireModel):
    """One stage on one side: its turns, median and p95 in seconds, the ears' confidence."""

    turns: int
    median_s: float | None
    p95_s: float | None
    confidence: float | None


class DriftStage(WireModel):
    """One stage on one vendor and model on both sides, and how far its median and p95 moved."""

    stage: Stage
    vendor: str | None
    model: str | None
    before: StageTally | None
    after: StageTally | None
    median_moved_s: float | None
    p95_moved_s: float | None


class DriftVersion(WireModel):
    """A version of the agent's settings a side ran or that was set between: who, when, why."""

    version: int
    holder: str
    author: str
    note: str | None
    set_at: float
    ran_before: bool
    ran_after: bool


class Drift(WireModel):
    """GET /v1/insights/drift: what moved between two days or versions of an agent, and why."""

    agent: str
    world: Env
    before: DriftSide
    after: DriftSide
    judges: list[DriftJudge]
    stages: list[DriftStage]
    versions: list[DriftVersion]


class InsightsQuery(Schema):
    """What insights count: the window's last day (today), its days, one agent or every one."""

    day: date | None = None
    days: int = 1
    agent: str | None = None


class DriftQuery(Schema):
    """What a drift compares: an agent, two days (today and the day before) or two versions."""

    agent: str
    before: str | None = None
    after: str | None = None


class UsageQuery(Schema):
    """Where the usage feed goes on from, and how many rows a page."""

    after: int = Field(0, ge=0)
    limit: int = Field(DEFAULT_LIMIT, ge=1, le=DEFAULT_LIMIT)


# FastAPI reads a query model flat only when it is an endpoint's one query parameter: the operator's
# `org` rides in the model, never beside it.
class BoxUsageQuery(UsageQuery):
    """The usage feed across the box, or one org's when `org` names it (its slug or its id)."""

    org: str | None = None
