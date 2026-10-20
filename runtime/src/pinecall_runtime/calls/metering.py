"""What a log counts for the bill: a metered entry folded into usage, and usage added up."""

import logging
from collections.abc import Iterable
from dataclasses import dataclass, field, replace
from typing import Self

from pinecall_runtime.calls.repository.entries import Positioned
from pinecall_runtime.exceptions import ValidationError
from pinecall_runtime.wire.events import CallSummary, event_of
from pinecall_runtime.wire.metrics import LLMModelUsage, TTSModelUsage
from pinecall_runtime.wire.scores import CallScore, EvalsSpent

logger = logging.getLogger(__name__)

UNOWNED = "unowned"
A_MINUTE_S = 60.0


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

    def __add__(self, other: Self) -> Self:
        """The two added up, field by field."""
        return type(self)(
            calls=self.calls + other.calls,
            minutes=self.minutes + other.minutes,
            messages=self.messages + other.messages,
            input_tokens=self.input_tokens + other.input_tokens,
            output_tokens=self.output_tokens + other.output_tokens,
            characters=self.characters + other.characters,
            judge_calls=self.judge_calls + other.judge_calls,
            evals=self.evals + other.evals,
            simulations=self.simulations + other.simulations,
            cost_usd=self.cost_usd + other.cost_usd,
            lent_minutes=self.lent_minutes + other.lent_minutes,
        )


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
            return replace(row, used=_used_by_a_call(data))
        case CallScore() | EvalsSpent():
            # Evals the org's own key answered are counted nowhere: they are never billed.
            evals = 0 if data.own_key else data.evals
            return replace(
                row, used=Usage(judge_calls=data.judge_calls, evals=evals, cost_usd=data.judge_cost_usd or 0.0)
            )
        case _:
            return row


def lent_row(row: UsageRow, vendors: tuple[str, ...]) -> UsageRow:
    """A summary's row with the vendors its call ran on the box's own key, and its minutes counted as lent."""
    if not vendors:
        return row
    return replace(row, lent=vendors, used=replace(row.used, lent_minutes=row.used.minutes))


def totals_by_org(rows: Iterable[UsageRow]) -> dict[str, Usage]:
    """The rows added up per org, in the order each org first appears."""
    totals: dict[str, Usage] = {}
    for row in rows:
        totals[row.org] = totals.get(row.org, Usage()) + row.used
    return totals


# Tokens are counted from the LLM rows and characters from the TTS rows; every other row's
# audio seconds are already the call's minutes.
# A simulated call is a simulation and an eval run's call is the run's: neither spends minutes.
def _used_by_a_call(summary: CallSummary) -> Usage:
    llm = [row for row in summary.usage if isinstance(row, LLMModelUsage)]
    tts = [row for row in summary.usage if isinstance(row, TTSModelUsage)]
    not_minutes = summary.simulated or summary.run is not None
    return Usage(
        calls=1,
        minutes=0.0 if not_minutes else summary.duration_s / A_MINUTE_S,
        messages=summary.turns,
        input_tokens=sum(row.input_tokens or 0 for row in llm),
        output_tokens=sum(row.output_tokens or 0 for row in llm),
        characters=sum(row.characters_count or 0 for row in tts),
        simulations=int(summary.simulated),
        cost_usd=summary.cost.usd,
    )
