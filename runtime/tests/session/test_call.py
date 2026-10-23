"""A call's state and its writer: entries in the order they happened, whatever the log refuses."""

import asyncio
import gc
from dataclasses import dataclass, field

import pytest

from pinecall_runtime.agents.declaration import AgentConfig, ToolSpec, Voice
from pinecall_runtime.agents.service.declared import changed_by, with_app_fields
from pinecall_runtime.calls.logs import Log
from pinecall_runtime.calls.store import Store
from pinecall_runtime.exceptions import Conflict, ServiceUnavailable
from pinecall_runtime.kit.text import JsonObject
from pinecall_runtime.session.call import Call, Platform
from pinecall_runtime.session.writing import MOST_A_BATCH, MOST_QUEUED, Writing
from pinecall_runtime.wire.base import BatchedEntry, Entry
from pinecall_runtime.wire.commands import SessionConfigure, ToolsSet
from pinecall_runtime.wire.events import Custom, UserTranscript
from pinecall_runtime.wire.parts import AgentConfig as Declared
from pinecall_runtime.wire.parts import Supervisor, VoiceConfig
from pinecall_runtime.wire.parts import ToolSpec as WiredTool
from tests.conftest import needs_the_database
from tests.fakes.acme import ACME
from tests.session.conftest import Box, context_of

A_TOOL = ToolSpec("book", "Book.", {"type": "object"})


def _custom(name: str) -> Custom:
    return Custom(name=name, data={})


@needs_the_database
async def test_entries_queued_from_sync_callbacks_reach_the_log_in_that_order(
    box: Box, store: Store, call: str
) -> None:
    writing = Writing(box.log.append_many, call)
    writing.open()
    for name in ("uno", "dos", "tres"):
        writing.write("custom", _custom(name))
    await writing.close(5)
    assert [entry.data["name"] for entry in await store.whole(call)] == ["uno", "dos", "tres"]


@needs_the_database
async def test_an_entry_waited_for_comes_back_with_the_seq_the_log_gave_it(box: Box, call: str) -> None:
    writing = Writing(box.log.append_many, call)
    writing.open()
    entry = await writing.write("custom", _custom("uno"))
    await writing.close(5)
    assert entry.seq > 0


@dataclass
class Batches:
    """The call's real log, the size of each batch it was sent, and a gate on the first."""

    log: Log
    sizes: list[int] = field(default_factory=list[int])
    first_out: asyncio.Event = field(default_factory=asyncio.Event)
    let_go: asyncio.Event = field(default_factory=asyncio.Event)

    async def append_many(self, entries: list[BatchedEntry], *, after: int) -> list[Entry]:
        """Count the batch, hold the first until let go, then write it on the log."""
        self.sizes.append(len(entries))
        if len(self.sizes) == 1:
            self.first_out.set()
            await self.let_go.wait()
        return await self.log.append_many(entries, after=after)


@needs_the_database
async def test_what_is_queued_while_a_batch_is_out_goes_in_the_next_one_in_order(
    box: Box, store: Store, call: str
) -> None:
    batches = Batches(box.log)
    writing = Writing(batches.append_many, call)
    writing.open()
    written = [writing.write("custom", _custom("uno"))]
    await batches.first_out.wait()
    written += [writing.write("custom", _custom(name)) for name in ("dos", "tres", "cuatro")]
    batches.let_go.set()
    await writing.close(5)
    assert batches.sizes == [1, 3]
    assert [entry.data["name"] for entry in await store.whole(call)] == [
        "uno",
        "dos",
        "tres",
        "cuatro",
    ]
    assert [future.result().seq for future in written] == [1, 2, 3, 4]
    assert writing.after == 4


@needs_the_database
async def test_a_batch_carries_at_most_its_ceiling_and_the_rest_follow(box: Box, store: Store, call: str) -> None:
    batches = Batches(box.log)
    batches.let_go.set()
    writing = Writing(batches.append_many, call)
    for n in range(MOST_A_BATCH * 2 + 3):
        writing.write("custom", _custom(str(n)))
    writing.open()
    await writing.close(5)
    assert batches.sizes == [MOST_A_BATCH, MOST_A_BATCH, 3]
    names = [entry.data["name"] for entry in await store.whole(call)]
    assert names == [str(n) for n in range(MOST_A_BATCH * 2 + 3)]


@needs_the_database
async def test_an_entry_of_an_idle_call_goes_alone(box: Box, call: str) -> None:
    batches = Batches(box.log)
    batches.let_go.set()
    writing = Writing(batches.append_many, call)
    writing.open()
    await writing.write("custom", _custom("uno"))
    await writing.write("custom", _custom("dos"))
    await writing.close(5)
    assert batches.sizes == [1, 1]


async def test_a_refused_batch_refuses_each_of_its_entries_and_the_next_still_goes() -> None:
    kept: list[str] = []

    async def picky(entries: list[BatchedEntry], *, after: int) -> list[Entry]:
        if any(entry.data.get("name") == "no" for entry in entries):
            raise Conflict("refused")
        kept.extend(str(entry.data["name"]) for entry in entries)
        return [
            Entry(
                seq=after + place,
                ts=entry.ts,
                call="c",
                agent="a",
                type=entry.type,
                ephemeral=bool(entry.ephemeral),
                data=entry.data,
            )
            for place, entry in enumerate(entries, 1)
        ]

    writing = Writing(picky, "c")
    refused = [writing.write("custom", _custom("no")), writing.write("custom", _custom("tampoco"))]
    writing.open()
    await asyncio.gather(*refused, return_exceptions=True)
    taken = await writing.write("custom", _custom("también"))
    await writing.close(5)
    assert kept == ["también"]
    assert writing.refused == ["custom 'no'", "custom 'tampoco'"]
    assert all(isinstance(future.exception(), Conflict) for future in refused)
    assert (taken.seq, writing.after) == (1, 1)


async def test_at_the_ceiling_an_ephemeral_entry_is_shed_and_a_durable_one_is_queued() -> None:
    async def stuck(entries: list[BatchedEntry], *, after: int) -> list[Entry]:
        del entries, after
        await asyncio.sleep(60)
        raise AssertionError

    writing = Writing(stuck, "c")
    for n in range(MOST_QUEUED):
        writing.write("custom", _custom(str(n)))
    heard = writing.write("user.transcript", UserTranscript(text="ho", final=False))
    kept = writing.write("custom", _custom("durable"))
    assert isinstance(heard.exception(), ServiceUnavailable)
    assert writing.shed == ["user.transcript"]
    assert not kept.done()
    assert writing.queued.qsize() == MOST_QUEUED + 1
    await writing.close(0.01)


# asyncio logs an exception nobody retrieved when its future is collected: once per shed entry.
async def test_a_shed_entry_nobody_waits_for_is_not_logged_as_an_exception_never_retrieved(
    caplog: pytest.LogCaptureFixture,
) -> None:
    async def stuck(entries: list[BatchedEntry], *, after: int) -> list[Entry]:
        del entries, after
        await asyncio.sleep(60)
        raise AssertionError

    writing = Writing(stuck, "c")
    for n in range(MOST_QUEUED):
        writing.write("custom", _custom(str(n)))
    writing.write("user.transcript", UserTranscript(text="ho", final=False))
    gc.collect()
    await asyncio.sleep(0)
    assert [record.getMessage() for record in caplog.records if record.name == "asyncio"] == []
    assert writing.shed == ["user.transcript"]
    await writing.close(0.01)


async def test_a_close_past_its_budget_lets_the_queue_go_rather_than_wait_for_ever() -> None:
    async def stuck(entries: list[BatchedEntry], *, after: int) -> list[Entry]:
        del entries, after
        await asyncio.sleep(60)
        raise AssertionError

    writing = Writing(stuck, "c")
    writing.open()
    writing.write("custom", _custom("uno"))
    writing.write("custom", _custom("dos"))
    await asyncio.wait_for(writing.close(0.05), 1)
    assert writing.draining is None
    assert writing.refused == ["custom 'uno'", "custom 'dos'"]


@needs_the_database
async def test_speech_ids_are_numbered_from_one(box: Box, call: str) -> None:
    ongoing = Call(context_of(call), AgentConfig(slug="a"), box.platform())
    assert (ongoing.speech(), ongoing.speech()) == ("sp_1", "sp_2")


# As the simulation of 2026-10-12 had it: "let me look that up" 0.6 s after the caller, the answer
# after the tool, and livekit's e2e on the answer alone, the tool's wait in it.
@needs_the_database
async def test_a_replys_end_to_end_is_the_wait_to_its_first_sound_and_no_later_turn_has_one(
    box: Box, call: str
) -> None:
    ongoing = Call(context_of(call), AgentConfig(slug="a"), box.platform())
    ongoing.heard({"started_speaking_at": 100.0, "stopped_speaking_at": 104.0})
    preamble = ongoing.replied({"started_speaking_at": 104.6, "stopped_speaking_at": 105.5})
    answer = ongoing.replied({"started_speaking_at": 108.2, "e2e_latency": 4.53})
    assert preamble["e2e_latency"] == pytest.approx(0.6)
    assert "e2e_latency" not in answer
    assert answer["started_speaking_at"] == 108.2


# A reply that started before the caller stopped talked over them: no wait to measure.
@needs_the_database
async def test_a_reply_over_the_caller_or_with_no_stop_known_carries_no_end_to_end(box: Box, call: str) -> None:
    ongoing = Call(context_of(call), AgentConfig(slug="a"), box.platform())
    ongoing.heard({"stopped_speaking_at": 104.0})
    assert "e2e_latency" not in ongoing.replied({"started_speaking_at": 103.5, "e2e_latency": 1.0})
    ongoing.heard({})
    assert "e2e_latency" not in ongoing.replied({"started_speaking_at": 110.0, "e2e_latency": 1.0})
    # The agent's opening follows no caller turn.
    fresh = Call(context_of(call), AgentConfig(slug="a"), box.platform())
    assert "e2e_latency" not in fresh.replied({"started_speaking_at": 1.0, "e2e_latency": 0.4})


# A realtime model's caller turn carries no `stopped_speaking_at` (Grok Voice, 2026-10-19): the
# wait is timed from when the session saw the caller go quiet, and the ears' own stop wins.
@needs_the_database
async def test_a_turn_with_no_stop_of_its_own_is_timed_from_when_the_caller_went_quiet(box: Box, call: str) -> None:
    ongoing = Call(context_of(call), AgentConfig(slug="a"), box.platform())
    ongoing.went_quiet(104.0)
    ongoing.heard({"started_speaking_at": 100.0})
    assert ongoing.replied({"started_speaking_at": 104.9})["e2e_latency"] == pytest.approx(0.9)
    ongoing.went_quiet(110.0)
    ongoing.heard({"stopped_speaking_at": 110.4})
    assert ongoing.replied({"started_speaking_at": 111.0})["e2e_latency"] == pytest.approx(0.6)
    # Each quiet times the one turn it ended.
    ongoing.heard({})
    assert "e2e_latency" not in ongoing.replied({"started_speaking_at": 120.0})


@needs_the_database
async def test_the_model_keeps_quiet_while_a_person_has_the_line_or_is_being_waited_for(box: Box, call: str) -> None:
    ongoing = Call(context_of(call), AgentConfig(slug="a"), box.platform())
    assert not ongoing.a_person_has_the_line
    ongoing.waiting_for_a_person = True
    assert ongoing.a_person_has_the_line
    ongoing.waiting_for_a_person = False
    ongoing.taken_by = Supervisor(id="mem_1")
    assert ongoing.a_person_has_the_line


@needs_the_database
async def test_everything_declared_is_open_until_a_tools_set_narrows_it(box: Box, store: Store, call: str) -> None:
    ongoing = Call(context_of(call), AgentConfig(slug="a", tools=(A_TOOL,)), box.platform())
    ongoing.writing.open()
    assert ongoing.open_tools == {"book"}
    undeclared = WiredTool(name="ghost", description="d", parameters={"type": "object"})
    await ongoing.set_tools(ToolsSet(tools=[undeclared]))
    assert ongoing.open_tools == frozenset()
    await ongoing.writing.close(5)
    assert [entry.data for entry in await store.whole(call)] == [{"visible": []}]


@needs_the_database
async def test_an_event_from_a_widget_names_the_seat_it_came_from(box: Box, store: Store, call: str) -> None:
    config = AgentConfig(slug="a", events={"clicked": frozenset({"participant"})})
    ongoing = Call(context_of(call), config, box.platform())
    ongoing.writing.open()
    await ongoing.receive("clicked", {"x": 1}, source="participant", identity="visitor_1")
    await ongoing.writing.close(5)
    (received,) = await store.whole(call)
    assert received.data == {
        "name": "clicked",
        "data": {"x": 1},
        "source": "participant",
        "identity": "visitor_1",
    }


def test_a_declaration_changes_only_the_fields_the_app_sent() -> None:
    current = AgentConfig(slug="a", language="es-ES", tools=(A_TOOL,))
    parameters: JsonObject = {"type": "object", "properties": {"phone": {"type": "string"}}}
    wired = WiredTool(name="cancel", description="d", parameters=parameters, pii=["phone"])
    data = Declared(tools=[wired], uses_knowledge=True)
    patched = with_app_fields(current, data)
    assert patched.language == "es-ES"
    assert patched.uses_knowledge
    assert [(tool.name, tool.pii) for tool in patched.tools] == [("cancel", frozenset({"phone"}))]
    assert patched.tools[0].timeout_s == A_TOOL.timeout_s


def test_what_the_class_declares_of_its_environment_is_taken_and_fixed() -> None:
    current = AgentConfig(slug="a")
    voice = VoiceConfig(provider=ACME, voice_id="v")
    patched = with_app_fields(current, Declared(voice=voice))
    assert patched.voice == Voice(ACME, None, "v")
    assert patched.fixed == frozenset({"voice"})


def test_the_fields_a_declaration_changed_are_named_sorted() -> None:
    assert changed_by(Declared(view=None, language="en")) == ["language", "view"]


@needs_the_database
async def test_a_configure_declares_for_this_call_and_sets_its_state(box: Box, store: Store, call: str) -> None:
    ongoing = Call(context_of(call), AgentConfig(slug="a"), box.platform())
    ongoing.writing.open()
    await ongoing.configure(SessionConfigure(config=Declared(language="en-US"), state={"step": "greeted"}))
    await ongoing.writing.close(5)
    assert ongoing.config.language == "en-US"
    written = await store.whole(call)
    assert [(entry.type, entry.data.get("changed")) for entry in written] == [
        ("agent.configured", ["language"]),
        ("state.changed", ["step"]),
    ]


# The app's word after its end hook says the seal may go on: it comes after what the app wrote before it.
@needs_the_database
async def test_the_apps_end_hook_done_is_said_to_the_platform_after_its_lines_were_written(
    box: Box, store: Store, call: str
) -> None:
    said: list[str] = []

    async def done() -> None:
        said.append("done")

    platform = Platform(append_many=box.log.append_many, tool=box.tool, lookup=box.lookup, seal=box.seal, done=done)
    ending = Call(context_of(call), AgentConfig(slug="clinica-norte"), platform)
    ending.writing.open()
    ending.writing.write("custom", _custom("closed"))
    await ending.app_finished()
    assert said == ["done"]
    assert [entry.data["name"] for entry in await store.whole(call)] == ["closed"]
    await ending.writing.close(5)


async def test_a_call_whose_platform_waits_for_nothing_takes_the_apps_word_and_goes_on(box: Box) -> None:
    await Call(context_of("call_1"), AgentConfig(slug="clinica-norte"), box.platform()).app_finished()


# An app's line logged after the log was sealed is lost; its name is what the warning keeps of it.
async def test_a_line_the_sealed_log_refused_is_named_in_what_is_logged(caplog: pytest.LogCaptureFixture) -> None:
    async def sealed(_entries: list[BatchedEntry], *, after: int) -> list[Entry]:
        raise Conflict(f"call call_1 has ended: its batch cannot be appended after {after}")

    writing = Writing(sealed, "call_1")
    writing.open()
    lost = writing.write("custom", _custom("closed"))
    with pytest.raises(Conflict):
        await lost
    await writing.close(5)
    assert "the log refused a batch of 1 (custom 'closed')" in caplog.text
    assert "the log refused 1 entries (custom 'closed')" in caplog.text
