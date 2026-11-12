"""A call's stages as it runs them: what was built, whether it is spoken, a vendor lost or back, what a model asks."""

from collections.abc import Callable, Iterable, Iterator, Sequence
from typing import Literal, TypeIs

from livekit.agents import llm, stt, tts
from livekit.agents.voice import AgentSession

from runtime.enums import Stage
from runtime.providers.stage import Ears, Speaking, Thinking
from runtime.session.call import Call
from runtime.session.writing import Writing
from runtime.wire import events as wire

type Adapter = llm.FallbackAdapter | stt.FallbackAdapter | tts.FallbackAdapter
# What a session built and measures: the model, and on a voice call the ears and the voice.
type Built = Thinking | Ears | Speaking
# A stage as the log's entries name it.
type StageName = Literal["llm", "stt", "tts"]
NAME_OF: dict[Stage, StageName] = {Stage.llm: "llm", Stage.stt: "stt", Stage.tts: "tts"}

# Gemini refuses a function call that neither a user turn nor a function response comes before, and
# the clock's pair opens every history: for a Google model it opens behind a user turn of one dot,
# the turn livekit's own Gemini format adds at a history's end for the same rule.
OPENS_ON_A_USER_TURN = "."
# Gemini 3 refuses a request whose current turn holds a function call it did not write, with no
# thought signature: a lookup the platform ran before the turn is such a call. Google's documented
# signature for a call injected by the caller of the API skips the check; the google plugin sends
# what its own table holds for each call id, so the lookup's ids are written there.
INJECTED_SIGNATURE = b"skip_thought_signature_validator"


# A realtime model hears and speaks itself: its call has no ears, and is spoken all the same.
def is_spoken(live: AgentSession[Call], built: Sequence[Built]) -> bool:
    """Whether the call is heard and answered in audio: it has ears, or a model that hears."""
    hears = isinstance(live.llm, llm.RealtimeModel)  # pyright: ignore[reportUnknownMemberType]
    return hears or any(isinstance(component, stt.STT) for component in built)


# livekit's adapter says when a vendor goes down or comes back (`<stage>_availability_changed`,
# the vendor under the stage's own name), and names the next to serve. Its emitter is untyped:
# it is read as an object.
def write_switches(writing: Writing, built: Iterable[object]) -> None:
    """Write vendor.switched each time a stage's fallback adapter loses or regains a vendor."""
    for component in built:
        match component:
            case llm.FallbackAdapter():
                stage: StageName = "llm"
            case stt.FallbackAdapter():
                stage = "stt"
            case tts.FallbackAdapter():
                stage = "tts"
            case _:
                continue
        listen: object = getattr(component, "on", None)
        if callable(listen):
            listen(f"{stage}_availability_changed", _switch(writing, stage, component))


def switch_of(stage: StageName, event: object, adapter: Adapter) -> wire.VendorSwitched | None:
    """The entry for one vendor of a stage lost or back, and the one serving from now."""
    changed: object = getattr(event, stage, None)
    available: object = getattr(event, "available", None)
    if not isinstance(changed, (llm.LLM, stt.STT, tts.TTS)) or not isinstance(available, bool):
        return None
    return wire.VendorSwitched(
        stage=stage,
        vendor=changed.provider,
        model=changed.model,
        available=available,
        serving=adapter.provider,
        serving_model=adapter.model,
    )


# ── what one vendor's model asks of a history ──
#
# These two are facts of a model, and the plugin's own tables are read to act on them: they belong
# to `providers`, the one domain whose work is knowing plugins, as two facts of its row
# (`opens_on_a_user_turn`, `signs_injected_calls`) and two functions over what a call built. They
# stand here, as they did, until that domain takes them.


def opening_turn(built: Sequence[object]) -> list[llm.ChatItem]:
    """The user turn a history opens with when Gemini reads it; nothing for any other model."""
    if not any(True for component in built for _ in _geminis(component)):
        return []
    return [llm.ChatMessage(role="user", content=[OPENS_ON_A_USER_TURN])]


def sign_calls(built: Sequence[object], call_ids: Sequence[str]) -> None:
    """Sign the function calls the platform puts in a request, for each Gemini model among `built`."""
    for component in built:
        for gemini in _geminis(component):
            # The plugin's own table of signatures by call id (dict[str, bytes]), read where it keeps it.
            table: object = getattr(gemini, "_thought_signatures", None)
            if _a_table(table):
                for call_id in call_ids:
                    table.setdefault(call_id, INJECTED_SIGNATURE)


# The model may sit inside the operator's request wrapper, or among a stage's fallbacks.
def _geminis(component: object) -> Iterator[object]:
    inner: object = getattr(component, "built", component)
    if isinstance(inner, llm.FallbackAdapter):
        fallbacks: Iterable[object] = getattr(inner, "_llm_instances", ())
        for fallback in fallbacks:
            yield from _geminis(fallback)
    elif type(inner).__module__.startswith("livekit.plugins.google"):
        yield inner


def _a_table(value: object) -> TypeIs[dict[str, bytes]]:
    return isinstance(value, dict)


def _switch(writing: Writing, stage: StageName, adapter: Adapter) -> Callable[[object], None]:
    def write(event: object) -> None:
        switched = switch_of(stage, event, adapter)
        if switched is not None:
            writing.write("vendor.switched", switched)

    return write
