"""Tests for how a turn is taken: backchannels and false interruptions."""

import pinecall_runtime.session.text as text
from pinecall_runtime.agents.declaration import Turn
from pinecall_runtime.session.hearing import AgentWords, loops, policy_for
from pinecall_runtime.session.voice import MIN_SPEECH_S, speech_detector
from pinecall_runtime.wire.commands import TakeoverVerb
from tests.conftest import needs_the_database
from tests.session.conftest import (
    Box,
    a_session,
)
from tests.session.test_session import (
    A_SUPERVISOR,
    NOBODY,
    spoken_call,
    supervised,
)


@needs_the_database
async def test_interruptions_are_judged_locally_and_a_cut_sentence_is_never_said_twice(
    box: Box,
) -> None:
    options = spoken_call(box, NOBODY).live.options
    assert options.interruption.get("mode") == "vad"
    assert options.interruption.get("resume_false_interruption") is False
    assert options.interruption.get("false_interruption_timeout") == 1.0
    assert options.preemptive_generation.get("enabled") is False


def test_agreement_alone_is_a_backchannel_and_anything_that_takes_the_floor_is_not() -> None:
    spanish = policy_for("es-ES")
    assert spanish.is_a_backchannel("sí, claro")
    assert spanish.is_a_backchannel("Mm, ok.")
    assert not spanish.is_a_backchannel("sí, pero el martes no puedo")
    assert not spanish.is_a_backchannel("")


def test_what_only_agrees_depends_on_the_agents_language() -> None:
    assert policy_for("en-US").is_a_backchannel("uh-huh, right")
    assert not policy_for("en-US").is_a_backchannel("vale")
    assert policy_for("pt-BR").is_a_backchannel("aham, certo")
    assert policy_for(None).is_a_backchannel("vale")
    assert policy_for(None).is_a_backchannel("yep")
    assert policy_for("es").min_words == 2
    assert policy_for("es", Turn(min_interruption_words=1)).min_words == 1
    assert policy_for("es").min_speech_s is None
    assert policy_for("es", Turn(min_interruption_ms=800)).min_speech_s == 0.8


@needs_the_database
async def test_a_takeover_with_nothing_to_interrupt_still_takes_the_line(box: Box) -> None:
    session = a_session(box, NOBODY)
    await session.start()
    await session.apply(supervised(TakeoverVerb()))
    assert session.call.taken_by == A_SUPERVISOR
    await text.end_text(session, "caller_hung_up", "caller")


def test_what_the_ears_invent_is_known_whole_and_only_whole() -> None:
    """Whisper's "Thank you." on a breath is made up; a turn that goes on is the caller's."""
    english = policy_for("en-US")
    assert english.is_made_up("Thank you.")
    assert english.is_made_up("thanks for watching!")
    assert not english.is_made_up("Thank you, and the invoice?")
    assert policy_for("es").is_made_up("Gracias.")
    assert policy_for(None).is_made_up("muchas gracias")


def test_the_agents_own_words_heard_back_are_an_echo_for_a_while() -> None:
    """Most of a turn's words among what the agent said lately is its voice played back; old words are not."""
    now = [100.0]
    words = AgentWords(clock=lambda: now[0])
    words.spoke("Good day, Bernardo. How can I help")
    words.spoke(" you today?")
    assert words.echoes("How can I help you")
    assert not words.echoes("I want a replacement lamp")
    assert not words.echoes("")
    words.stopped()
    now[0] += 1.0
    assert words.just_stopped()
    now[0] += 1.0
    assert not words.just_stopped()
    now[0] += 20.0
    assert not words.echoes("How can I help you")


def test_the_ears_looping_on_one_phrase_is_never_a_caller() -> None:
    """Whisper's loop on a breath of noise is dropped whoever speaks; a caller who repeats a word is not."""
    assert loops("I'm going to make sure that " * 12)
    assert loops("so the thing is, and then the order and then the order and then the order came")
    # Two words said over and over is a person stuck on a word, not the ears' loop.
    assert not loops("the order the order the order")
    assert not loops("no, no, no, I said Tuesday")
    assert not loops("I'm going to make sure that I'm going to call you")
    assert not loops("")


@needs_the_database
async def test_the_ears_hear_only_speech_that_lasts(box: Box) -> None:
    """A breath opens no segment: Silero waits a quarter second of speech, where livekit's own waits 0.05."""
    assert spoken_call(box, NOBODY).live.vad is speech_detector()
    assert MIN_SPEECH_S == 0.25
