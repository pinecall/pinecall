"""Tests for a live call taking its model and its voice anew, as the agent's settings name them now."""

import pytest
from livekit.agents import llm

import pinecall_runtime.session.text as text
import pinecall_runtime.session.voice as voice_module
from pinecall_runtime.agents.declaration import AgentConfig
from pinecall_runtime.calls.store import Store
from pinecall_runtime.exceptions import Conflict, PinecallError
from pinecall_runtime.providers.service.plugins import Running
from pinecall_runtime.session.stages import take_stages
from pinecall_runtime.session.writing import WRITTEN_WITHIN_S
from pinecall_runtime.wire.events import StageChanged
from tests.conftest import needs_the_database
from tests.fakes.acme import ACME
from tests.fakes.talker import TalkerRealtime
from tests.session.conftest import Box, a_session, kinds
from tests.session.test_session import settled, spoken_call

NOBODY = AgentConfig(slug="clinica-norte")


@needs_the_database
async def test_a_call_answers_on_the_model_its_settings_name_now_and_remembers_what_was_said(
    box: Box, store: Store, call: str
) -> None:
    session = a_session(box, NOBODY, ["Hola, soy la primera"])
    await session.start()
    assert await text.hear_text(session, "hola") == "Hola, soy la primera"
    before = session.agent
    now = Running(ACME, "a-key", model="acme-2", options={"replies": [["Y yo la segunda"]]})
    assert await take_stages(session, {"llm": now}, alone=False) == ["llm"]
    await settled()
    assert await text.hear_text(session, "¿y ahora?") == "Y yo la segunda"
    assert session.agent is not before and session.running == {"llm": now}
    said = [item.text_content for item in session.agent.chat_ctx.items if isinstance(item, llm.ChatMessage)]
    assert "Hola, soy la primera" in said and "Y yo la segunda" in said
    await text.end_text(session, "caller_hung_up", "caller")
    changed = [entry for entry in await store.whole(call) if entry.type == "stage.changed"]
    assert [StageChanged.model_validate(entry.data) for entry in changed] == [
        StageChanged(stage="llm", vendor=ACME, model="acme-2")
    ]


# A spoken call's room is livekit's own: the stages are taken on a call built and not started, its writer open.
@needs_the_database
async def test_a_spoken_call_takes_the_voice_alone_and_keeps_its_ears_and_its_model(
    box: Box, store: Store, call: str
) -> None:
    session = spoken_call(box, NOBODY)
    session.call.writing.open()
    model, ears, _ = session.built
    vera = Running(ACME, "k", voice="vera")
    assert await take_stages(session, {"llm": session.running["llm"], "tts": vera}, alone=False) == ["tts"]
    kept_model, kept_ears, voice = session.built
    assert (kept_model, kept_ears) == (model, ears) and voice is session.agent.voice
    assert session.listener.components == session.built
    await session.call.writing.close(WRITTEN_WITHIN_S)
    assert (await kinds(store, call)).count("stage.changed") == 1


@needs_the_database
async def test_new_ears_are_said_and_left_for_the_next_call(box: Box, store: Store, call: str) -> None:
    session = spoken_call(box, NOBODY)
    session.call.writing.open()
    built, agent = session.built, session.agent
    flux = Running(ACME, "k", model="acme-ears-2")
    assert await take_stages(session, {**session.running, "stt": flux}, alone=False) == []
    assert (session.built, session.agent) == (built, agent)
    # Said once: the call knows what its settings name now, and asked again it has nothing new to say.
    assert await take_stages(session, {**session.running, "stt": flux}, alone=False) == []
    await session.call.writing.close(WRITTEN_WITHIN_S)
    said = [entry for entry in await store.whole(call) if entry.type == "stage.changed"]
    assert [StageChanged.model_validate(entry.data) for entry in said] == [
        StageChanged(stage="stt", vendor=ACME, model="acme-ears-2", applied=False)
    ]


@needs_the_database
async def test_settings_that_name_what_already_runs_change_nothing_and_say_nothing(
    box: Box, store: Store, call: str
) -> None:
    session = spoken_call(box, NOBODY)
    before = session.agent
    assert await take_stages(session, dict(session.running), alone=False) == []
    await settled()
    assert session.agent is before and "stage.changed" not in await kinds(store, call)


@needs_the_database
async def test_a_call_on_one_model_that_hears_and_speaks_is_refused_and_so_are_settings_that_name_one(
    box: Box, monkeypatch: pytest.MonkeyPatch
) -> None:
    model = TalkerRealtime(api_key="k")
    model.capabilities.supports_say = True

    def built(_stage: Running) -> llm.RealtimeModel:
        return model

    monkeypatch.setattr(voice_module.providers, "build_realtime", built)
    alone = spoken_call(box, NOBODY, realtime=True)
    with pytest.raises(Conflict, match="runs on the next call"):
        await take_stages(alone, {"llm": Running(ACME, "k", model="acme-2")}, alone=False)
    staged = spoken_call(box, NOBODY)
    with pytest.raises(Conflict, match="runs on the next call"):
        await take_stages(staged, dict(staged.running), alone=True)


@needs_the_database
async def test_a_stage_its_vendor_refuses_leaves_the_call_on_the_stages_it_had(box: Box) -> None:
    session = spoken_call(box, NOBODY)
    built, running, agent = session.built, dict(session.running), session.agent
    with pytest.raises(PinecallError):
        await take_stages(session, {**running, "tts": Running("a-vendor-nobody-installed", "k")}, alone=False)
    assert (session.built, session.running, session.agent) == (built, running, agent)
