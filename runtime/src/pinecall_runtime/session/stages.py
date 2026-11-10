"""A live call taking its model and its voice anew, as the agent's settings name them now."""

from collections.abc import Mapping

from livekit.agents import llm, tts

from pinecall_runtime.exceptions import Conflict
from pinecall_runtime.providers import service as providers
from pinecall_runtime.session.listener import Built, Stage, write_switches
from pinecall_runtime.session.session import Session
from pinecall_runtime.session.tools import asked_first, signing
from pinecall_runtime.wire import events as wire

ONE_MODEL_ALONE = "this call runs on one model that hears and speaks: what its settings name now runs on the next call"
# The ears are built once a call, with the turn they end: theirs is said and waits for the next call.
REBUILT: tuple[Stage, ...] = ("llm", "tts")


# Built before anything of the call is touched: a stage its vendor refuses (a key, a voice it does
# not have) leaves the call on the stages it had, and the refusal is the caller's to write.
# livekit hands the call from the agent before to its successor once the reply being said is over,
# so no sentence changes voice in the middle.
async def take_stages(session: Session, wanted: Mapping[Stage, providers.Running], *, alone: bool) -> list[Stage]:
    """Rebuild the model and the voice that differ, and say every stage that changed; the stages rebuilt."""
    if alone or not session.running:
        raise Conflict(ONE_MODEL_ALONE)
    differs: list[Stage] = [
        stage for stage, running in session.running.items() if stage in wanted and wanted[stage] != running
    ]
    changed: list[Stage] = [stage for stage in differs if stage in REBUILT]
    if changed:
        _rebuild(session, wanted, changed)
    for stage in differs:
        now = session.running[stage] = wanted[stage]
        said = wire.StageChanged(
            stage=stage, vendor=now.vendor, model=now.model, voice=now.voice, applied=stage in REBUILT
        )
        await session.call.writing.write("stage.changed", said)
    return changed


def _rebuild(session: Session, wanted: Mapping[Stage, providers.Running], changed: list[Stage]) -> None:
    thinking = providers.build_thinking(wanted["llm"]) if "llm" in changed else None
    voice = providers.build_voice(wanted["tts"]) if "tts" in changed else None
    before = session.built
    fresh: tuple[Built, ...] = tuple(component for component in (thinking, voice) if component is not None)
    session.built = (*(component for component in before if not _replaced(component, thinking, voice)), *fresh)
    session.listener.measure(session.built)
    write_switches(session.call.writing, fresh)
    session.lookups.sign = signing(session.built)
    was = session.agent
    opens = [] if asked_first(before) else asked_first(session.built)

    # Read as the hand-over is asked and again as livekit makes it, the reply being said then over.
    def carried() -> llm.ChatContext:
        history = was.chat_ctx.copy()
        history.items[:0] = opens
        # A model reads the calls the one before it made: Gemini takes them signed as the platform's own.
        session.lookups.sign([item.call_id for item in history.items if isinstance(item, llm.FunctionCall)])
        return history

    session.agent = was.succeeded_by(carried, thinking, voice)
    session.live.update_agent(session.agent)


def _replaced(component: Built, thinking: providers.Thinking | None, voice: providers.Speaking | None) -> bool:
    return (thinking is not None and isinstance(component, llm.LLM)) or (
        voice is not None and isinstance(component, tts.TTS)
    )
