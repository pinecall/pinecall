"""The worker's stages from the gateway's answer, the realtime model only where handed out; a hang-up ends the call."""

from collections.abc import AsyncGenerator
from typing import cast

import pytest

from pinecall_runtime.agents.schemas import PipelineKeys, RunningStage
from pinecall_runtime.calls.service import CALLER_HUNG_UP
from pinecall_runtime.jobs.service.client import GatewayClient
from pinecall_runtime.jobs.service.job import _follow_commands, follow_command, pipeline_of
from pinecall_runtime.session import service as session
from pinecall_runtime.wire.base import Command

STAGE = RunningStage(vendor="acme", credentials="k", model="acme-1")


async def test_the_callers_hang_up_on_the_stream_is_the_caller_gone_and_no_command_of_the_apps() -> None:
    """The gateway's own word on the stream ends the call as the caller's; the session is never asked to apply it."""
    gone: list[str] = []
    said = Command(type=CALLER_HUNG_UP, agent="clinica-norte", call="call_1", id=None, data={})
    await follow_command(cast(session.Session, object()), said, lambda: gone.append("caller"))
    assert gone == ["caller"]


def test_an_answer_with_no_realtime_model_builds_none() -> None:
    answer = PipelineKeys.model_validate({"llm": STAGE, "stt": STAGE, "tts": STAGE})
    assert pipeline_of(answer).realtime is None


def test_a_realtime_model_handed_out_is_the_pipelines_beside_its_llm() -> None:
    talking = RunningStage(vendor="xai", credentials="k", model="grok-voice-3.0", options={"voice": "eve"})
    built = pipeline_of(PipelineKeys(llm=STAGE, stt=STAGE, tts=STAGE, realtime=talking))
    assert built.realtime is not None
    assert (built.realtime.vendor, built.realtime.model, dict(built.realtime.options)) == (
        "xai",
        "grok-voice-3.0",
        {"voice": "eve"},
    )
    assert built.llm.model == "acme-1"


def test_the_answer_leaves_out_a_realtime_model_nobody_names_for_a_worker_of_the_version_before() -> None:
    answer = PipelineKeys(llm=STAGE, stt=STAGE, tts=STAGE)
    assert "realtime" not in answer.model_dump(exclude_unset=True)


class Breaking:
    """A call's session that breaks on a command with what is no refusal of ours."""

    async def apply(self, _command: object) -> None:
        """Break."""
        raise RuntimeError("the session broke")


class Streaming:
    """The gateway's command stream for a call: one the session breaks on, then the caller's hang-up."""

    async def commands(self, call: str) -> AsyncGenerator[Command]:
        """The two commands, in order."""
        yield Command(type="state.set", agent="clinica-norte", call=call, id=None, data={"state": {}})
        yield Command(type=CALLER_HUNG_UP, agent="clinica-norte", call=call, id=None, data={})


# A follower that ended on a command the session broke on left the call deaf to its hang-up and to a
# supervisor's end, with nothing said of why (K F5's class of seat that never frees).
async def test_a_command_the_session_breaks_on_is_said_with_its_call_and_the_next_one_is_heard(
    caplog: pytest.LogCaptureFixture,
) -> None:
    gone: list[str] = []
    await _follow_commands(
        cast(GatewayClient, Streaming()), cast(session.Session, Breaking()), "call_1", lambda: gone.append("caller")
    )
    assert gone == ["caller"]
    assert "a command of the app failed on call_1" in caplog.text
