"""The worker builds its stages from the gateway's answer: the realtime model only where one was handed out."""

from pinecall_runtime.agents.schemas import PipelineKeys, RunningStage
from pinecall_runtime.jobs.service.job import pipeline_of

STAGE = RunningStage(vendor="acme", credentials="k", model="acme-1")


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
