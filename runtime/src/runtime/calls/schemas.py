"""The bodies of the record's endpoints, a family after another: logs, lists, the inbox, callbacks, usage."""

from typing import Annotated, Literal, Self

from pydantic import AliasPath, BeforeValidator, Field

from runtime.enums import Channel, Direction, Env
from runtime.kit.schemas import Epoch, Row, Schema
from runtime.kit.text import JsonObject
from runtime.wire.base import Entry, WireModel
from runtime.wire.parts import CallStatus, Contact, Cost, EndReason, SessionFlag, ThreadKind
from runtime.wire.state import AttentionState

# A listing's page is never longer than this, whatever the reader asks.
LONGEST_LIST = 200
# A screen of a listing, when the reader names no size.
A_SCREENFUL = 20
# A log's page, and the usage feed's, when the reader names no size; and the most either takes.
A_LOG_PAGE = 500
# An inbox's page of contacts.
THREADS_A_PAGE = 30


# ── logs ──


class TokenQuery(Schema):
    """A query a page may carry its call's token in: EventSource sets no header, so the token rides the URL."""

    # The reading dependency reads it (`calls/auth.py`); it is named here so the query, which refuses
    # every name it does not know, lets it through.
    token: str | None = None


class LogQuery(TokenQuery):
    """What a log's reader asks for: the cursor, the types, only what is kept, a page's size."""

    after: int = Field(0, ge=0)
    types: str | None = None
    durable: bool = False
    limit: int = Field(A_LOG_PAGE, ge=1, le=A_LOG_PAGE)


# Projected entries keep only part of the envelope, so they travel as plain JSON.
class LogPage(Row):
    """One page of a log: the entries above the cursor, and where the next page starts."""

    entries: list[JsonObject]
    live: bool
    next: int | None


class CallState(Row):
    """GET /v1/calls/{call}/state: the folded state as its reader may see it, and the seq a stream resumes from."""

    state: JsonObject
    last_seq: int
    live: bool


class PromptBlockRow(Row):
    """One block of a call's prompt as its log names it, with the words the org kept of it."""

    seq: int
    name: str
    hash: str
    chars: int
    # Null for a block no gateway kept the words of (a call from before they were kept).
    text: str | None


class CallPromptResponse(Row):
    """GET /v1/calls/{call}/prompt: every block the call was told, in the order it was told."""

    call: str
    blocks: list[PromptBlockRow]


# What the box says of itself belongs to no org, and its frame names no env at all.
class BoxEvent(WireModel):
    """One frame of GET /v1/ops/events: an entry of some org's feed, whose, and in which env."""

    org: str
    env: Env | None = None
    entry: Entry

    @classmethod
    def of(cls, org: str, env: Env | None, entry: Entry) -> Self:
        """The frame of an entry: an org's with its env, the box's own with neither."""
        return cls(org=org, env=env, entry=entry) if org else cls(org=org, entry=entry)


# ── lists ──


class SessionScore(Row):
    """What the judges said of a call, as a list row carries it."""

    held: int
    judged: int
    passed: bool
    reason: str | None


class CallRow(Row):
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
    # Whose copy of the agent took it, to a list asked with holders: a member's id and name, "" the org's own.
    holder: str | None = None
    holder_name: str | None = None


class CallList(Row):
    """A page of calls, newest first."""

    calls: list[CallRow]
    total: int | None = None
    next: str | None = None


class ListQuery(Schema):
    """What a list of calls asks for: an agent, words, a channel, a page below a call."""

    limit: int = Field(A_SCREENFUL, ge=1, le=LONGEST_LIST)
    q: str | None = Field(None, max_length=200)
    agent: str | None = None
    # Compared as text: a channel nobody has lists nothing, it is not refused.
    channel: str | None = None
    before: str | None = None
    # Each row also says whose copy of the agent took it (holder, holder_name).
    holders: bool = False


# ── the inbox ──


class ThreadLast(Row):
    """The newest thing on a contact's thread."""

    text: str | None
    at: float
    kind: ThreadKind


class ThreadRow(Row):
    """One contact of an agent's inbox: every call of theirs, folded into one line."""

    contact: str
    name: str | None
    channel_last: Channel
    last: ThreadLast
    unread: int
    calls: int


class ThreadList(Row):
    """GET /v1/agents/{slug}/threads: the agent's contacts, the newest thread first."""

    threads: list[ThreadRow]
    next: str | None


class ThreadMessage(Row):
    """One message of a thread, or one spoken call drawn as a pill."""

    kind: ThreadKind
    text: str | None
    at: float
    call: str
    channel: Channel
    duration_s: float | None = None
    answered: bool | None = None


class ThreadResponse(Row):
    """GET /v1/agents/{slug}/threads/{contact}: every call of one contact, merged, oldest first."""

    contact: str
    name: str | None
    messages: list[ThreadMessage]


class ThreadQuery(Schema):
    """One page of an inbox: after the cursor of the last one, so many contacts."""

    after: str | None = None
    limit: int = Field(THREADS_A_PAGE, ge=1, le=LONGEST_LIST)


# ── callbacks ──


class CallbackRequest(WireModel):
    """Somebody the overflow told to wait for a call back."""

    agent: str
    channel: Channel
    number: str
    call: str | None = None


class CallbackRow(Row):
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


class CallbackList(Row):
    """A page of the org's callbacks, oldest first, and where the next starts."""

    requests: list[CallbackRow]
    next: int | None


class CallbackQuery(Schema):
    """Where the org's list of callbacks continues, and whose."""

    after: int = 0
    agent: str | None = None


# ── what the org used: the usage feed ──


class UsageTotals(Row):
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
    # The minutes of calls a stage of which ran on the box's own key.
    lent_minutes: float = 0.0
    # What simulated callers' own models and voices cost, beside the calls' cost.
    caller_cost_usd: float = 0.0


# Flat, as v1 wrote it: a billing layer that reads the feed today reads it unchanged. Each number is
# read off what the row used (`folds.usage.UsageRow.used`): until 2026-11 an endpoint copied the
# seventeen fields by hand.
class UsageRow(Row):
    """One metered entry: whose it was, which call, what it consumed, and where the feed is."""

    cursor: int
    org: str
    agent: str
    call: str
    type: str
    at: float
    minutes: float = Field(validation_alias=AliasPath("used", "minutes"))
    messages: int = Field(validation_alias=AliasPath("used", "messages"))
    input_tokens: int = Field(validation_alias=AliasPath("used", "input_tokens"))
    output_tokens: int = Field(validation_alias=AliasPath("used", "output_tokens"))
    characters: int = Field(validation_alias=AliasPath("used", "characters"))
    judge_calls: int = Field(validation_alias=AliasPath("used", "judge_calls"))
    evals: int = Field(validation_alias=AliasPath("used", "evals"))
    # A call.summary of a call a simulated caller played: billed as one simulation, not minutes.
    simulated: Annotated[bool, BeforeValidator(bool)] = Field(validation_alias=AliasPath("used", "simulations"))
    cost_usd: float = Field(validation_alias=AliasPath("used", "cost_usd"))
    # A call.summary's vendors that ran on the box's own key: the stages the operator paid for.
    lent: list[str] = Field(default_factory=list[str])
    # A simulated call.summary's caller: what its own model and voice cost, beside the agent's cost_usd.
    caller_cost_usd: float = Field(0.0, validation_alias=AliasPath("used", "caller_cost_usd"))


class UsagePage(Row):
    """GET /v1/usage: the org's metered rows after the cursor, their totals, the next cursor."""

    rows: list[UsageRow]
    totals: UsageTotals | None
    next: int | None


class BoxUsagePage(Row):
    """GET /v1/ops/usage: every org's metered rows after the cursor, totals per org, the next."""

    rows: list[UsageRow]
    totals: dict[str, UsageTotals]
    next: int | None


class UsageQuery(Schema):
    """Where the usage feed goes on from, and how many rows a page."""

    after: int = Field(0, ge=0)
    limit: int = Field(A_LOG_PAGE, ge=1, le=A_LOG_PAGE)


# FastAPI reads a query model flat only when it is an endpoint's one query parameter: the operator's
# `org` rides in the model, never beside it.
class BoxUsageQuery(UsageQuery):
    """The usage feed across the box, or one org's when `org` names it (its slug or its id)."""

    org: str | None = None


# ── a carrier's traceback ──


class TracebackCall(Row):
    """One phone call with the number: whose, which way, when, how it ended, whether erased."""

    call: str
    org: str | None
    env: str | None
    direction: str | None
    from_number: str | None
    to_number: str | None
    started_at: float | None
    ended_at: float | None
    end_reason: str | None
    # The call's log is gone and only its record is left.
    erased: bool


class TracebackDial(Row):
    """One dial to the number: whose, the call it placed, the number shown, who asked, the guard."""

    org: str
    env: str
    agent: str
    call: str | None
    shown: str | None
    asked_by: str
    refused: str | None
    at: Epoch


class Traceback(Row):
    """GET /v1/ops/traceback: what the box keeps of one number since a day, oldest first."""

    number: str
    since: float
    calls: list[TracebackCall]
    dials: list[TracebackDial]
