"""A comparison: a persona or more against the agent under several voices and models, its calls read side by side."""

from collections.abc import Iterable, Sequence
from statistics import median

from pinecall_runtime.calls import service as calls
from pinecall_runtime.evals.schemas import ComparisonRow, Latency, SessionScore
from pinecall_runtime.wire.base import Entry

# How many voices and models one comparison puts the agent under: each is a simulation placed at once.
COMPARED_AT_MOST = 10
TOO_MANY_COMPARED = (
    "a comparison places 10 calls at most: {personas} callers against {configs} configurations is one call per pair"
)
COMPARISON_PREFIX = "cmp_"
NO_SUCH_COMPARISON = "no comparison {comparison} in this key's org and env"
# The turn measures a row carries, each its median over the call (calls/latencies.py).
MEASURES = ("e2e_latency", "llm_node_ttft", "tts_node_ttfb", "transcription_delay", "end_of_turn_delay")


async def compared_row(serving: calls.Serving, run: calls.PersonaRun) -> ComparisonRow:
    """One call of the comparison as its row: what the agent ran on, how it went, its cost, its latencies."""
    facts = calls.facts_of(run.facts)
    entries = await serving.logs.store.whole(facts.call)
    score = None
    if facts.judged is not None and facts.passed is not None:
        score = SessionScore(held=facts.held or 0, judged=facts.judged, passed=facts.passed, reason=facts.reason)
    return ComparisonRow.model_validate(
        {
            "call": facts.call,
            "persona": facts.persona or "",
            "against": dict(facts.against or {}),
            "started_at": run.started_at,
            "ended_at": facts.ended_at,
            "turns": len(facts.heard_at),
            "end_reason": facts.end_reason,
            "score": None if score is None else score.dump(),
            "cost_usd": facts.cost_usd,
            "latency": latency_of(entries).model_dump(),
            "why": why_it_never_began(entries),
        }
    )


def why_it_never_began(entries: Iterable[Entry]) -> str | None:
    """The reason a call ended before it began, from its log's unrecoverable error; None for one that ran."""
    for entry in entries:
        if entry.type == "error" and entry.data.get("recoverable") is False:
            return str(entry.data.get("message") or "")
        if entry.type == "call.started":
            return None
    return None


def latency_of(entries: Iterable[Entry]) -> Latency:
    """Each measure's median over the call's turns; one no turn reported is None."""
    samples = calls.samples(calls.reduce(entries).turns)
    return Latency(**{name: median(samples[name]) if name in samples else None for name in MEASURES})


# The best is the one a person would pick first: every judge held, then the most that held, then the
# fastest reply, then the cheapest. A call still on the line is last: nothing of it is known yet.
def in_the_order_placed(rows: Sequence[ComparisonRow]) -> list[str]:
    """The comparison's callers, each once, in the order their calls were placed."""
    return list(dict.fromkeys(row.persona for row in sorted(rows, key=lambda row: row.started_at)))


# Each caller's rows together, the callers in the order placed, so a table reads one caller at a time.
def ranked(rows: Sequence[ComparisonRow]) -> list[ComparisonRow]:
    """The rows best first, caller by caller."""
    order = {persona: at for at, persona in enumerate(in_the_order_placed(rows))}

    def key(row: ComparisonRow) -> tuple[int, bool, bool, float, float, float]:
        judged = row.score is not None and row.score.judged > 0
        passed = row.score is not None and row.score.passed
        share = row.score.held / row.score.judged if judged and row.score is not None else 0.0
        e2e = row.latency.e2e_latency if row.latency.e2e_latency is not None else float("inf")
        cost = row.cost_usd if row.cost_usd is not None else float("inf")
        return (order[row.persona], row.ended_at is None, not passed, -share, e2e, cost)

    return sorted(rows, key=key)
