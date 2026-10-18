"""A session opened for a spoken call: the pipeline, the turn options, the ears' keyterms."""

from collections.abc import Sequence
from functools import cache

from livekit.agents import NOT_GIVEN, NotGivenOr, inference, llm
from livekit.agents.voice import AgentSession, STTContextOptions
from livekit.agents.voice import text_transforms as transforms
from livekit.agents.voice.agent_session import DEFAULT_TTS_TEXT_TRANSFORMS
from livekit.agents.voice.turn import InterruptionOptions, TurnDetectionMode, TurnHandlingOptions
from smart_turn_livekit import SmartTurnDetector  # pyright: ignore[reportMissingTypeStubs]

from pinecall_runtime.agents.declaration import AgentConfig
from pinecall_runtime.providers import service as providers
from pinecall_runtime.session.call import Call
from pinecall_runtime.session.hearing import keyterms, policy_for
from pinecall_runtime.session.listener import write_switches
from pinecall_runtime.session.lookups import VOICE_LOOKUP_MS, Lookups
from pinecall_runtime.session.session import ONE_ANSWER_PER_TOOL, Session

# The local end-of-turn model: left unset, livekit may pick the hosted one and send the
# caller's words to a cloud.
LOCAL_TURN_VERSION: inference.TurnDetectorVersions = "v1-mini"
# The checkpoint in smart-turn-livekit's registry: upstream's, benchmarked on 23 languages.
SMART_TURN: providers.TurnModel = "smart-turn-v3"
# How long Silero must hear speech before it opens a segment for the ears. livekit's 0.05 s opens
# one on a breath or a sigh, and Whisper-family ears write each as words ("Thank you.", "We'll be
# right back."): on a real call (gpu.pinecall.io, 2026-10-17) 0.05 s opened 8 segments for the
# caller's 4 sentences, 0.25 s exactly the 4, while "Sí." and "No." alone still open one (0.35 s
# of speech, the shortest measured). Keeping noise from the ears is how Whisper is kept honest.
MIN_SPEECH_S = 0.25


def voice_session(call: Call, stages: providers.Pipeline, lookup_budget_ms: int | None = None) -> Session:
    """A voice call: the three stages built for it, the turn taken as a phone line needs; or the
    realtime model the agent names, alone."""
    if stages.realtime is not None:
        return _realtime_session(call, providers.build_realtime(stages.realtime), stages, lookup_budget_ms)
    thinking = providers.build_thinking(stages.llm)
    ears = providers.build_ears(stages.stt, call.config.turn, keyterms(call.config, {}))
    voice = providers.build_voice(stages.tts)
    write_switches(call.writing, (thinking, ears, voice))
    live: AgentSession[None] = AgentSession(
        llm=thinking,
        stt=ears,
        tts=voice,
        turn_handling=_spoken_turns(call.config, stages.stt),
        vad=speech_detector(),
        # Word timings reach transcription_node only from an aligned voice.
        use_tts_aligned_transcript=True,
        tts_text_transforms=_text_transforms_of(call.config),
        stt_context_options=context_of(call.config, ears),
        max_tool_steps=ONE_ANSWER_PER_TOOL,
    )
    return Session(
        live, (thinking, ears, voice), Lookups(call, call.platform.lookup, lookup_budget_ms or VOICE_LOOKUP_MS)
    )


# A realtime model hears the caller, takes the turn and answers in its own voice: the session has no
# ears and leaves the turn to the model. One that says given words itself (xAI's) says the notice, a
# greeting given as words and a read-back too, so the call has one voice: livekit says through a TTS
# whenever the session has one. A model that cannot keeps the call's voice for them.
def _realtime_session(
    call: Call, realtime: llm.RealtimeModel, stages: providers.Pipeline, lookup_budget_ms: int | None
) -> Session:
    if realtime.capabilities.supports_say:
        alone: AgentSession[None] = AgentSession(llm=realtime, max_tool_steps=ONE_ANSWER_PER_TOOL)
        return Session(alone, (), Lookups(call, call.platform.lookup, lookup_budget_ms or VOICE_LOOKUP_MS))
    voice = providers.build_voice(stages.tts)
    write_switches(call.writing, (voice,))
    live: AgentSession[None] = AgentSession(
        llm=realtime,
        tts=voice,
        tts_text_transforms=_text_transforms_of(call.config),
        max_tool_steps=ONE_ANSWER_PER_TOOL,
    )
    # The realtime model reports its measures through its session, not itself: only the voice is listened to.
    return Session(live, (voice,), Lookups(call, call.platform.lookup, lookup_budget_ms or VOICE_LOOKUP_MS))


def context_of(config: AgentConfig, ears: providers.Ears) -> NotGivenOr[STTContextOptions]:
    """The keyterms the ears are told at start, when they take any."""
    if not config.hears or not ears.capabilities.keyterms:
        return NOT_GIVEN
    return {"keyterms": keyterms(config, {})}


# One detector per process, as livekit makes its own: each session streams to it on its own.
@cache
def speech_detector() -> inference.VAD:
    """Silero, opening a segment only on speech that lasts."""
    return inference.VAD(model="silero", min_speech_duration=MIN_SPEECH_S)


# One Smart Turn per process: its weights load once and its first inference runs when it is made,
# so only the first call that asks for it pays. Each session streams to it on its own.
@cache
def smart_turn() -> SmartTurnDetector:
    """Smart Turn v3, the row's alternative to livekit's own detector."""
    return SmartTurnDetector(SMART_TURN)


def _end_of_turn(model: providers.TurnModel) -> TurnDetectionMode:
    detector: TurnDetectionMode = (
        smart_turn() if model == SMART_TURN else inference.TurnDetector(version=LOCAL_TURN_VERSION)
    )
    return detector


# The parameter replaces livekit's defaults, so they come first and the tenant's words after.
def _text_transforms_of(config: AgentConfig) -> NotGivenOr[Sequence[transforms.TextTransforms]]:
    if not config.says:
        return NOT_GIVEN
    return [*DEFAULT_TTS_TEXT_TRANSFORMS, transforms.replace(dict(config.says))]


# Interruptions are judged by the local VAD: livekit's adaptive detector streams the caller's
# audio to its cloud. A false interruption is not resumed: livekit replays the whole sentence.
# No endpointing here: the agent's own already reaches the ears, and both would wait twice.
def _spoken_turns(config: AgentConfig, ears: providers.Running) -> TurnHandlingOptions:
    policy = policy_for(config.language, config.turn)
    interruption: InterruptionOptions = {
        "min_words": policy.min_words,
        "mode": "vad",
        "false_interruption_timeout": policy.false_interruption_s,
        "resume_false_interruption": False,
    }
    if policy.min_speech_s is not None:
        interruption["min_duration"] = policy.min_speech_s
    return {
        # Ears that end the turn themselves decide it; the local detector stacked on them waits
        # its whole delay after a pause in the middle of a sentence.
        "turn_detection": "stt" if ears.ends_the_turn else _end_of_turn(ears.turn_model),
        # A reply started inside a tool's window, on a context without its result, answers its
        # own question.
        "preemptive_generation": {"enabled": False},
        "interruption": interruption,
    }
