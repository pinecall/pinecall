"""The worker's stages from the gateway's answer, the realtime model only where handed out; a hang-up ends the call."""

from typing import cast

from pinecall_runtime.agents.schemas import PipelineKeys, RunningStage
from pinecall_runtime.calls.service import CALLER_HUNG_UP
from pinecall_runtime.jobs.service.job import follow_command, pipeline_of
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
