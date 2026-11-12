"""Judging's rules, one module per noun; what another domain uses is named here, and nothing else."""

from runtime.judging.repository.groups import GroupCounted
from runtime.judging.service.asking import ASKED_WITHIN, Context, force_tool
from runtime.judging.service.cases import (
    Born,
    Decision,
    check_decision,
    decide_case,
    keep_at_hangup,
    list_cases,
    pick_cases,
)
from runtime.judging.service.declaration import check_declaration
from runtime.judging.service.groups import A_GROUP, decide_group, propose_for_group
from runtime.judging.service.judge_model import EVALS_SPENT, JudgeRun, Unjudged, ask_judge_model, judge_model_of
from runtime.judging.service.judges import RosterJudge, judge_named, roster_of, spec_of
from runtime.judging.service.judges import Wanted as JudgeWanted
from runtime.judging.service.library import library_personas
from runtime.judging.service.panel import (
    OUT_OF_EVALS,
    PromptTexts,
    ask_judge,
    context_of,
    gate_of,
    judge_call,
    prompt_of,
    surroundings_of,
)
from runtime.judging.service.personas import Played, check_persona_models, get_persona, put_persona
from runtime.judging.service.specs import LONGEST_PAUSE_S, Behavior, JudgeSpec, Persona
from runtime.judging.service.transcript import (
    AGENT,
    CALLER,
    Failed,
    GateKind,
    GateLine,
    Said,
    Transcript,
    conversation_of,
    is_simulated,
    transcript_of,
)

__all__ = [
    "AGENT",
    "ASKED_WITHIN",
    "A_GROUP",
    "CALLER",
    "EVALS_SPENT",
    "LONGEST_PAUSE_S",
    "OUT_OF_EVALS",
    "Behavior",
    "Born",
    "Context",
    "Decision",
    "Failed",
    "GateKind",
    "GateLine",
    "GroupCounted",
    "JudgeRun",
    "JudgeSpec",
    "JudgeWanted",
    "Persona",
    "Played",
    "PromptTexts",
    "RosterJudge",
    "Said",
    "Transcript",
    "Unjudged",
    "ask_judge",
    "ask_judge_model",
    "check_decision",
    "check_declaration",
    "check_persona_models",
    "context_of",
    "conversation_of",
    "decide_case",
    "decide_group",
    "force_tool",
    "gate_of",
    "get_persona",
    "is_simulated",
    "judge_call",
    "judge_model_of",
    "judge_named",
    "keep_at_hangup",
    "library_personas",
    "list_cases",
    "pick_cases",
    "prompt_of",
    "propose_for_group",
    "put_persona",
    "roster_of",
    "spec_of",
    "surroundings_of",
    "transcript_of",
]
