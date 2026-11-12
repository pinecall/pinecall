"""What a log counts for the bill: a metered entry folded into usage, and usage added up."""

import logging
from collections.abc import Iterable
from dataclasses import dataclass, field, fields, replace
from typing import Self

from runtime.calls.models import Opener
from runtime.calls.repository.entries import Positioned
from runtime.exceptions import ValidationError
from runtime.kit.time import A_MINUTE_S
from runtime.wire.events import CallSummary, event_of
from runtime.wire.metrics import LLMModelUsage, TTSModelUsage
from runtime.wire.scores import CallScore, EvalsSpent

logger = logging.getLogger(__name__)

UNOWNED = "unowned"
# The gateway opens a call as a written session and nothing else: a call spoken in a room is opened
# by the fleet's worker or by an app. The same words are `opened_by` in the totals' fold
# (migrations/versions/20261023_000013). A call whose head says neither, opened before heads said
# who opened them, counts as it always did: its minutes and its turns both.
WRITTEN_CALLS_OPENER = Opener.gateway
SPOKEN_CALLS_OPENERS = frozenset({Opener.fleet, Opener.app})


# cost_usd is the vendors' estimate, what the call cost the operator, never what is charged.
@dataclass(frozen=True, slots=True)
class Usage:
    """What was consumed: calls, minutes, turns, tokens, characters, judges asked, the cost."""

    calls: int = 0
    minutes: float = 0.0
    messages: int = 0
    input_tokens: int = 0
    output_tokens: int = 0
    characters: int = 0
    judge_calls: int = 0
    # Judges that answered a call's question on the platform's key: the evals billed (N/A,
    # deferred, skipped and the org's own key's are not counted).
    evals: int = 0
    # Calls a simulated caller played.
    simulations: int = 0
    cost_usd: float = 0.0
    # The minutes of calls a stage of which ran on the box's own key: what a plan that includes
    # the box's vendors bills apart from the minutes an org ran on keys of its own.
    lent_minutes: float = 0.0
    # What simulated callers' own models and voices cost, beside the calls' cost_usd: the harness's.
    caller_cost_usd: float = 0.0

    # Over the fields as declared: until 2026-11 the twelve were listed here by hand, and a new one
    # was three edits.
    def __add__(self, other: Self) -> Self:
        """The two added up, field by field."""
        return type(self)(**{one.name: getattr(self, one.name) + getattr(other, one.name) for one in fields(self)})


@dataclass(frozen=True, slots=True)
class UsageRow:
    """What one metered entry consumed, and whose it was."""

    cursor: int
    org: str
    agent: str
    call: str
    type: str
    at: float
    used: Usage = field(default_factory=Usage)
    # The vendors a call ran on the box's own key; the gateway keeps them with the call's facts.
    lent: tuple[str, ...] = ()


def usage_row(metered: Positioned) -> UsageRow:
    """What a summary, a score or a try consumed; an entry nobody can read, nothing."""
    entry = metered.entry
    row = UsageRow(
        cursor=metered.position,
        org=metered.org or UNOWNED,
        agent=entry.agent,
        call=entry.call or "",
        type=entry.type,
        at=entry.ts,
    )
    try:
        data = event_of(entry)
    except ValidationError:
        logger.warning("usage: %s at seq %d is unreadable", entry.type, entry.seq, exc_info=True)
        return row
    match data:
        case CallSummary():
            return replace(row, used=_usage_of_call(data, metered.opened_by))
        case CallScore() | EvalsSpent():
            # Evals the org's own key answered are counted nowhere: they are never billed.
            evals = 0 if data.own_key else data.evals
            return replace(
                row, used=Usage(judge_calls=data.judge_calls, evals=evals, cost_usd=data.judge_cost_usd or 0.0)
            )
        case _:
            return row


# The vendors and the caller's cost are not in the summary: they are kept beside the call's fold,
# and whoever reads the feed hands them in.
def bill_row(row: UsageRow, vendors: tuple[str, ...], caller_cost_usd: float = 0.0) -> UsageRow:
    """A summary's row with the vendors its call ran on the box's key, its minutes lent, and its caller's cost."""
    used = replace(row.used, lent_minutes=row.used.minutes if vendors else 0.0, caller_cost_usd=caller_cost_usd)
    return replace(row, lent=vendors, used=used)


def total_by_org(rows: Iterable[UsageRow]) -> dict[str, Usage]:
    """The rows added up per org, in the order each org first appears."""
    totals: dict[str, Usage] = {}
    for row in rows:
        totals[row.org] = totals.get(row.org, Usage()) + row.used
    return totals


# Tokens are counted from the LLM rows and characters from the TTS rows; every other row's
# audio seconds are already the call's minutes.
# A simulated call is a simulation and an eval run's call is the run's: neither spends minutes. One
# quota for each kind of call: a spoken call spends minutes and no messages, a written one messages
# and no minutes.
def _usage_of_call(summary: CallSummary, opened_by: Opener | None) -> Usage:
    llm = [row for row in summary.usage if isinstance(row, LLMModelUsage)]
    tts = [row for row in summary.usage if isinstance(row, TTSModelUsage)]
    not_minutes = summary.simulated or summary.run is not None or opened_by is WRITTEN_CALLS_OPENER
    not_messages = opened_by in SPOKEN_CALLS_OPENERS
    return Usage(
        calls=1,
        minutes=0.0 if not_minutes else summary.duration_s / A_MINUTE_S,
        messages=0 if not_messages else summary.turns,
        input_tokens=sum(row.input_tokens or 0 for row in llm),
        output_tokens=sum(row.output_tokens or 0 for row in llm),
        characters=sum(row.characters_count or 0 for row in tts),
        simulations=int(summary.simulated),
        cost_usd=summary.cost.usd,
    )
