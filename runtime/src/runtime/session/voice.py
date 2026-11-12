"""A session built for a spoken call: the pipeline or one model alone, the turn options, the ears' keyterms."""

from collections.abc import Sequence
from functools import cache
from typing import Literal

from livekit.agents import NOT_GIVEN, NotGivenOr, inference, llm
from livekit.agents.voice import AgentSession, STTContextOptions
from livekit.agents.voice import text_transforms as transforms
from livekit.agents.voice.agent_session import DEFAULT_TTS_TEXT_TRANSFORMS
from livekit.agents.voice.turn import InterruptionOptions, TurnDetectionMode, TurnHandlingOptions
from smart_turn_livekit import SmartTurnDetector  # pyright: ignore[reportMissingTypeStubs]

from runtime.agents.declaration import Declaration, Turn
from runtime.enums import Stage
from runtime.kit.words import replace_in_stream
from runtime.providers import service as providers
from runtime.providers.stage import Ears, Pipeline, Running, TurnModel
from runtime.session.call import Call
from runtime.session.hearing import TurnPolicy, keyterms, policy_for
from runtime.session.line import Line
from runtime.session.lookups import VOICE_LOOKUP_MS, Lookups
from runtime.session.session import TOOL_STEPS, OnEnded, Place, Session
from runtime.session.stages import Built, write_switches
from runtime.wire import events as wire

# The local end-of-turn model: left unset, livekit may pick the hosted one and send the
# caller's words to a cloud.
LOCAL_TURN_VERSION: inference.TurnDetectorVersions = "v1-mini"
# The checkpoint in smart-turn-livekit's registry: upstream's, benchmarked on 23 languages.
SMART_TURN: TurnModel = "smart-turn-v3"
# How long Silero must hear speech before it opens a segment for the ears. livekit's 0.05 s opens
# one on a breath or a sigh, and Whisper-family ears write each as words ("Thank you.", "We'll be
# right back."): on a real call (gpu.pinecall.io, 2026-10-17) 0.05 s opened 8 segments for the
# caller's 4 sentences, 0.25 s exactly the 4, while "Sí." and "No." alone still open one (0.35 s
# of speech, the shortest measured). Keeping noise from the ears is how Whisper is kept honest.
MIN_SPEECH_S = 0.25
# livekit's own longest wait for a detector that is unsure the caller is done.
MAX_SILENCE_S = 3.0
# The least silence before the detector is asked, where the agent sets none. livekit's 0.3 s (0.5
# for its own detector) closed the turn inside a caller's sentence: on 2026-11-07 the pauses between
# "Yes, please." and "Go ahead and book it." ran 0.35 to 0.5 s, and at 500 ms four lines of five were
# cut in two, the phone number among them; 800 ms cut none and the answer felt late.
SILENCE_S = 0.7


def voice_session(
    call: Call,
    stages: Pipeline,
    place: Place,
    *,
    lookup_budget_ms: int | None = None,
    tool_steps: int | None = None,
    on_ended: OnEnded | None = None,
) -> Session:
    """A voice call: its three stages built, the turn taken as a phone line needs; or the realtime model it names."""
    declaration = call.declaration
    policy = policy_for(declaration.language, declaration.turn)
    lookups = Lookups(call, lookup_budget_ms or VOICE_LOOKUP_MS)
    if stages.realtime is not None:
        alone, voices = _realtime_session(call, stages.realtime, stages.tts, tool_steps or TOOL_STEPS)
        line = Line(call, alone, place.melody)
        return Session(alone, voices, lookups, line, policy, running={}, place=place, on_ended=on_ended)
    thinking = providers.build_thinking(stages.llm)
    ears = providers.build_ears(stages.stt, declaration.turn, keyterms(declaration, {}), speech_detector())
    voice = providers.build_voice(stages.tts)
    write_switches(call.writing, (thinking, ears, voice))
    live: AgentSession[Call] = AgentSession(
        userdata=call,
        llm=thinking,
        stt=ears,
        tts=voice,
        turn_handling=_spoken_turns(policy, declaration.turn, stages.stt),
        vad=speech_detector(),
        # Word timings reach transcription_node only from an aligned voice.
        use_tts_aligned_transcript=True,
        tts_text_transforms=_text_transforms_of(declaration),
        stt_context_options=context_of(declaration, ears),
        max_tool_steps=tool_steps or TOOL_STEPS,
    )
    return Session(
        live,
        (thinking, ears, voice),
        lookups,
        Line(call, live, place.melody),
        policy,
        running={Stage.llm: stages.llm, Stage.stt: stages.stt, Stage.tts: stages.tts},
        place=place,
        turn=_turn_detection(stages.stt, declaration.turn),
        on_ended=on_ended,
    )


# Said on the log as the call opens, so a transcript says who ended each caller's turn and on what silence.
def _turn_detection(ears: Running, turn: Turn | None) -> wire.TurnDetection:
    if ears.ends_the_turn:
        return wire.TurnDetection(by="stt", model=ears.model or ears.vendor)
    by: Literal["livekit", "smart-turn"] = "smart-turn" if ears.turn_model == SMART_TURN else "livekit"
    return wire.TurnDetection(by=by, model=ears.turn_model, min_silence_s=_min_silence(turn))


# The agent's endpointing, in seconds, for the detector the session stacks on ears that leave the turn open.
def _min_silence(turn: Turn | None) -> float:
    return SILENCE_S if turn is None or turn.endpointing_ms is None else turn.endpointing_ms / 1000


# A realtime model hears the caller, takes the turn and answers in its own voice: the session has no
# ears and leaves the turn to the model. One that says given words itself (xAI's) says the notice, a
# greeting given as words and a read-back too, so the call has one voice: livekit says through a TTS
# whenever the session has one. A model that cannot keeps the call's voice for them. The realtime
# model reports its measures through its session, not itself: only the voice is listened to.
def _realtime_session(
    call: Call, model: Running, speaks_with: Running, tool_steps: int
) -> tuple[AgentSession[Call], tuple[Built, ...]]:
    realtime: llm.RealtimeModel = providers.build_realtime(model)
    if realtime.capabilities.supports_say:
        return AgentSession(userdata=call, llm=realtime, max_tool_steps=tool_steps), ()
    voice = providers.build_voice(speaks_with)
    write_switches(call.writing, (voice,))
    live: AgentSession[Call] = AgentSession(
        userdata=call,
        llm=realtime,
        tts=voice,
        tts_text_transforms=_text_transforms_of(call.declaration),
        max_tool_steps=tool_steps,
    )
    return live, (voice,)


def context_of(declaration: Declaration, ears: Ears) -> NotGivenOr[STTContextOptions]:
    """The keyterms the ears are told at start, when they take any."""
    if not declaration.hears or not ears.capabilities.keyterms:
        return NOT_GIVEN
    return {"keyterms": keyterms(declaration, {})}


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


def _end_of_turn(model: TurnModel) -> TurnDetectionMode:
    detector: TurnDetectionMode = (
        smart_turn() if model == SMART_TURN else inference.TurnDetector(version=LOCAL_TURN_VERSION)
    )
    return detector


# The parameter replaces livekit's defaults, so they come first and the tenant's words after: found
# as whole words (kit.words), where livekit's own replace would find `CLI` inside "cliente".
def _text_transforms_of(declaration: Declaration) -> NotGivenOr[Sequence[transforms.TextTransforms]]:
    if not declaration.says:
        return NOT_GIVEN
    return [*DEFAULT_TTS_TEXT_TRANSFORMS, replace_in_stream(dict(declaration.says))]


# Interruptions are judged by the local VAD: livekit's adaptive detector streams the caller's
# audio to its cloud. A sound that brings no words within the policy's second is a false
# interruption, and the reply it stopped goes on where it was paused: with no resume, a reply
# cancelled while still being written was never said, and the agent sat silent for 33 s after a
# caller finished a phone number the ears had already closed (2026-11-06).
# The agent's endpointing reaches the ears that end the turn (Flux's timeout), and the detector
# stacked on the others as the least silence before it is asked: never both, which would wait twice.
def _spoken_turns(policy: TurnPolicy, turn: Turn | None, ears: Running) -> TurnHandlingOptions:
    interruption: InterruptionOptions = {
        "min_words": policy.min_words,
        "mode": "vad",
        "false_interruption_timeout": policy.false_interruption_s,
        "resume_false_interruption": True,
    }
    if policy.min_speech_s is not None:
        interruption["min_duration"] = policy.min_speech_s
    handling: TurnHandlingOptions = {
        # Ears that end the turn themselves decide it; the local detector stacked on them waits
        # its whole delay after a pause in the middle of a sentence.
        "turn_detection": "stt" if ears.ends_the_turn else _end_of_turn(ears.turn_model),
        # A reply started inside a tool's window, on a context without its result, answers its
        # own question.
        "preemptive_generation": {"enabled": False},
        "interruption": interruption,
    }
    if not ears.ends_the_turn:
        silence = _min_silence(turn)
        # The most it waits when the detector is unsure stays livekit's, unless the least is longer.
        handling["endpointing"] = {"min_delay": silence, "max_delay": max(silence, MAX_SILENCE_S)}
    return handling
