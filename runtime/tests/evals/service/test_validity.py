"""A simulated call counts when its agent's model answered for it on a caller's clean line, and says why when not."""

from runtime.evals.service.validity import BREAKS_A_MINUTE_AT_MOST, VALID, breaks_a_minute, judge
from runtime.wire.base import Entry


def an_error(code: str, message: str, seq: int = 5) -> Entry:
    """An error the call's log holds."""
    data = {"code": code, "message": message, "recoverable": False}
    return Entry.model_construct(
        call="call_1", seq=seq, ts=1.0, agent="front-desk", type="error", ephemeral=False, data=data
    )


# A minute of the caller's lines, at ten milliseconds a frame.
A_MINUTE = 6000


def test_a_call_with_no_error_on_a_line_that_kept_to_the_clock_counts() -> None:
    line = {"frames": 9000, "speech_frames": A_MINUTE, "breaks_in_speech": 3}
    assert judge([], "caller_hung_up", line) == VALID
    assert judge([], "caller_hung_up", line).valid


# 2026-11-25: OpenAI out of credit refused gpt-5.4-mini's calls and gpt-realtime-2's; their rows were
# counted as the models' failures.
def test_a_vendor_that_refused_a_stage_of_the_agent_makes_the_call_count_for_nothing() -> None:
    refused = an_error(
        "component_dead_end", "openai refused this call's model: You have no credits remaining.\nlivekit"
    )
    verdict = judge([refused], "error", None)
    assert not verdict.valid and verdict.invalid is not None
    assert verdict.invalid.kind == "vendor"
    assert (
        verdict.invalid.why
        == "a vendor of the agent failed the call: openai refused this call's model: You have no credits remaining."
    )


def test_a_call_our_side_never_served_or_lost_its_worker_in_counts_for_nothing() -> None:
    for code in ("never_served", "worker_lost", "session_failed"):
        verdict = judge([an_error(code, "no agent joined room call_1 in 110s")], "error", None)
        assert verdict.invalid is not None and verdict.invalid.kind == "platform", code


def test_a_vendors_failure_is_the_reason_over_ours_when_a_call_holds_both() -> None:
    errors = [
        an_error("worker_lost", "the call's worker went away", 3),
        an_error("component_failed", "cartesia failed on its side (502): x", 9),
    ]
    verdict = judge(errors, "error", None)
    assert verdict.invalid is not None and verdict.invalid.kind == "vendor"


# 2026-11-25: nineteen callers on one gateway's loop, 36 to 137 silences a minute inside each one's
# speech; five at a time, 0 to 6.
def test_a_caller_whose_voice_broke_up_makes_the_call_count_for_nothing() -> None:
    broken = {"speech_frames": A_MINUTE, "breaks_in_speech": 36}
    verdict = judge([], "caller_hung_up", broken)
    assert verdict.invalid is not None and verdict.invalid.kind == "caller"
    assert verdict.invalid.why.startswith("the simulated caller's voice broke up: 36 silences a minute")
    clean = {"speech_frames": A_MINUTE, "breaks_in_speech": int(BREAKS_A_MINUTE_AT_MOST)}
    assert judge([], "caller_hung_up", clean).valid


def test_a_caller_that_broke_on_the_line_makes_the_call_count_for_nothing() -> None:
    verdict = judge(
        [], "caller_hung_up", {"broke": "the gateway could not play this call's caller (KeyError): its log says why"}
    )
    assert verdict.invalid is not None and verdict.invalid.kind == "caller"


def test_too_little_speech_or_a_line_measured_before_breaks_were_counted_says_nothing() -> None:
    assert breaks_a_minute({"speech_frames": 500, "breaks_in_speech": 40}) is None
    assert breaks_a_minute({"frames": 9000, "late_frames": 300, "late_ms": 9000.0, "worst_ms": 80.0}) is None
    assert breaks_a_minute(None) is None


def test_a_model_that_is_slow_or_wrong_is_the_eval_and_its_call_counts() -> None:
    slow = an_error("llm_timeout", "the model took over 10 s to answer")
    assert judge([slow], "caller_hung_up", None).valid
    assert judge([], "agent_hung_up", None).valid


def test_a_call_that_ended_in_error_with_no_reason_on_its_log_is_ours() -> None:
    verdict = judge([], "error", None)
    assert verdict.invalid is not None and verdict.invalid.kind == "platform"
