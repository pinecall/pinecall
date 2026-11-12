"""Judging's rules, one module per noun; what another domain uses is named here, and nothing else."""

from runtime.judging.service.cases import Born, keep_at_hangup
from runtime.judging.service.declaration import check_declaration
from runtime.judging.service.panel import OUT_OF_EVALS, judge_call
from runtime.judging.service.transcript import is_simulated, transcript_of

__all__ = [
    "OUT_OF_EVALS",
    "Born",
    "check_declaration",
    "is_simulated",
    "judge_call",
    "keep_at_hangup",
    "transcript_of",
]
