"""The vendor `talker`: a plain model, and a realtime one that hears and speaks itself, installed as a plugin."""

import dataclasses
import types
from typing import Literal, Never, override

from livekit.agents import llm

from tests.fakes.plugins import install_plugin

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

    # What it can do, as its vendor's class declares it.
    able: llm.RealtimeCapabilities = ABLE

    def __init__(
        self, *, api_key: str, model: Literal["voice-1", "voice-3"] | str = "voice-1", voice: str | None = "Ara"
    ) -> None:
        super().__init__(capabilities=self.able)
        self.given = {"api_key": api_key, "model": model, "voice": voice}

    @override
    def session(self, *, turn_detection_disabled: bool = False) -> llm.RealtimeSession[Never]:
        raise NotImplementedError

    @override
    async def aclose(self) -> None:
        return None


SAYING = "talker-saying"
ABLE_TO_SAY = dataclasses.replace(ABLE, supports_say=True)


class SayingRealtime(TalkerRealtime):
    """A realtime model that says given words itself, as xAI's does: the call has its one voice."""

    able = ABLE_TO_SAY


def install_saying() -> str:
    """Put `livekit.plugins.talker-saying` where the runtime looks for vendors; its name."""
    return install_plugin(SAYING, LLM=TalkerLLM, realtime=types.SimpleNamespace(RealtimeModel=SayingRealtime))


def install() -> str:
    """Put `livekit.plugins.talker` where the runtime looks for vendors; its name."""
    return install_plugin(TALKER, LLM=TalkerLLM, realtime=types.SimpleNamespace(RealtimeModel=TalkerRealtime))
