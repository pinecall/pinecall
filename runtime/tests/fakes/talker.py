"""The vendor `talker`: a plain model, and a realtime one that hears and speaks itself, installed as a plugin."""

import sys
import types
from typing import Literal, Never, override

import pytest
from livekit.agents import llm

from pinecall_runtime.providers.service import plugins

TALKER = "talker"
# What its realtime class types its `model` argument as, as xAI's does.
REALTIME = ("voice-1", "voice-3")
PLAIN = "plain-1"

ABLE = llm.RealtimeCapabilities(
    message_truncation=False,
    turn_detection=True,
    user_transcription=True,
    auto_tool_reply_generation=False,
    audio_output=True,
    manual_function_calls=False,
)


class TalkerLLM:
    """Its plain model's class, never built here."""


class TalkerRealtime(llm.RealtimeModel):
    """Its realtime model: built with its key, its model and its options, and kept what it was given."""

    def __init__(
        self, *, api_key: str, model: Literal["voice-1", "voice-3"] | str = "voice-1", voice: str | None = "Ara"
    ) -> None:
        super().__init__(capabilities=ABLE)
        self.given = {"api_key": api_key, "model": model, "voice": voice}

    @override
    def session(self, *, turn_detection_disabled: bool = False) -> llm.RealtimeSession[Never]:
        raise NotImplementedError

    @override
    async def aclose(self) -> None:
        return None


def install(monkeypatch: pytest.MonkeyPatch) -> str:
    """Put `livekit.plugins.talker` where the runtime looks for vendors, for one test."""
    module = types.ModuleType(f"{plugins.PLUGINS}.{TALKER}")
    vars(module).update(LLM=TalkerLLM, realtime=types.SimpleNamespace(RealtimeModel=TalkerRealtime))
    monkeypatch.setitem(sys.modules, module.__name__, module)
    monkeypatch.setitem(plugins.installed(), TALKER, plugins.Vendor(TALKER, frozenset({"llm"}), realtime=REALTIME))
    return TALKER
