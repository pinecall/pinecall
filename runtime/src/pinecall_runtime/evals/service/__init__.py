"""The eval rules, one module per noun; what other domains use is named here once."""

from pinecall_runtime.evals.service.callers import Spending, heard_in, improvise_line
from pinecall_runtime.evals.service.checks import irreversible_tools, replay
from pinecall_runtime.evals.service.comparisons import (
    COMPARED_AT_MOST,
    COMPARISON_PREFIX,
    NO_SUCH_COMPARISON,
    TOO_MANY_COMPARED,
    compared_row,
    in_the_order_placed,
    latency_of,
    ranked,
)
from pinecall_runtime.evals.service.players import caller_model, caller_voice
from pinecall_runtime.evals.service.playing import Played, converse, drive
from pinecall_runtime.evals.service.runs import (
    Runner,
    get_run,
    list_runs,
    new_run,
    put_run,
)
from pinecall_runtime.evals.service.simulations import (
    AT_ONCE,
    Placed,
    Simulations,
    TooManyAtOnce,
    admit_simulation,
    calling_as,
    claim_new_call,
    opens_with_a_notice,
    played_on,
    spoken_call,
    written_call,
    written_turns,
)
from pinecall_runtime.evals.service.spoken import Line, described, line_of
from pinecall_runtime.evals.service.suites import start_suite

__all__ = [
    "AT_ONCE",
    "COMPARED_AT_MOST",
    "COMPARISON_PREFIX",
    "NO_SUCH_COMPARISON",
    "TOO_MANY_COMPARED",
    "Line",
    "Placed",
    "Played",
    "Runner",
    "Simulations",
    "Spending",
    "TooManyAtOnce",
    "admit_simulation",
    "caller_model",
    "caller_voice",
    "calling_as",
    "claim_new_call",
    "compared_row",
    "converse",
    "described",
    "drive",
    "get_run",
    "heard_in",
    "improvise_line",
    "in_the_order_placed",
    "irreversible_tools",
    "latency_of",
    "line_of",
    "list_runs",
    "new_run",
    "opens_with_a_notice",
    "played_on",
    "put_run",
    "ranked",
    "replay",
    "spoken_call",
    "start_suite",
    "written_call",
    "written_turns",
]
