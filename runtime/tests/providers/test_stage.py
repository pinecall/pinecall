"""A pipeline as the worker reads it off the gateway's answer: three stages, and a realtime model where handed out."""

from runtime.providers.stage import Pipeline
from runtime.wire.worker import PipelineKeys, RunningStage

STAGE = RunningStage(vendor="acme", credentials="k", model="acme-1")


def test_an_answer_with_no_realtime_model_builds_none() -> None:
    answer = PipelineKeys(llm=STAGE, stt=STAGE, tts=STAGE)
    assert Pipeline.read(answer.model_dump()).realtime is None


def test_a_realtime_model_handed_out_is_the_pipelines_beside_its_llm() -> None:
    talking = RunningStage(vendor="xai", credentials="k", model="grok-voice-3.0", options={"voice": "eve"})
    built = Pipeline.read(PipelineKeys(llm=STAGE, stt=STAGE, tts=STAGE, realtime=talking).model_dump())
    assert built.realtime is not None
    assert (built.realtime.vendor, built.realtime.model, dict(built.realtime.options)) == (
        "xai",
        "grok-voice-3.0",
        {"voice": "eve"},
    )
    assert built.llm.model == "acme-1"


# A worker of the release before refuses a field it does not know: the answer names none it was not given.
def test_the_answer_leaves_out_a_realtime_model_nobody_names_for_a_worker_of_the_release_before() -> None:
    assert "realtime" not in PipelineKeys(llm=STAGE, stt=STAGE, tts=STAGE).model_dump(exclude_unset=True)
