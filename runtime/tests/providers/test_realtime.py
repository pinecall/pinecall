"""An LLM stage that names a realtime model builds one, for the whole conversation of a voice call;
any other builds no realtime model, and the call keeps its ears, its model and its voice."""

from typing import Never, override

import pytest
from livekit.agents import llm

from pinecall_runtime.agents.declaration import Modality
from pinecall_runtime.providers.service import stages
from pinecall_runtime.providers.service.plugins import Running

ABLE = llm.RealtimeCapabilities(
    message_truncation=False,
    turn_detection=True,
    user_transcription=True,
    auto_tool_reply_generation=False,
    audio_output=True,
    manual_function_calls=False,
)


class Talks(llm.RealtimeModel):
    """As xAI's `realtime.RealtimeModel`: built with its key, its model and its voice."""

    def __init__(self, *, api_key: str, model: str = "voice-1", voice: str | None = "Ara") -> None:
        super().__init__(capabilities=ABLE)
        self.given = {"api_key": api_key, "model": model, "voice": voice}

    @override
    def session(self, *, turn_detection_disabled: bool = False) -> llm.RealtimeSession[Never]:
        raise NotImplementedError

    @override
    async def aclose(self) -> None:
        return None


class Thinks:
    """A plain LLM's class: no realtime model."""


def _with(monkeypatch: pytest.MonkeyPatch, made: type) -> None:
    def the_class(_modality: Modality, _running: Running) -> type:
        return made

    monkeypatch.setattr(stages, "_class_of", the_class)


def test_a_stage_that_names_a_realtime_model_builds_it_with_its_key_and_model(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _with(monkeypatch, Talks)
    built = stages.build_realtime(Running(vendor="v", credentials="k", model="voice-3", builds="realtime.Talks"))
    assert isinstance(built, Talks)
    assert built.given == {"api_key": "k", "model": "voice-3", "voice": "Ara"}


def test_a_stage_of_a_plain_llm_builds_no_realtime_model(monkeypatch: pytest.MonkeyPatch) -> None:
    _with(monkeypatch, Thinks)
    assert stages.build_realtime(Running(vendor="v", credentials="k", model="m")) is None
