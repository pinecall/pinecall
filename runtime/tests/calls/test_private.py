"""What a call's log keeps of a private value: masked wherever the agent wrote it down, sealed aside."""

from cryptography.fernet import Fernet

from pinecall_runtime.agents.declaration import AgentConfig, ToolSpec, Versions
from pinecall_runtime.calls import private
from pinecall_runtime.calls.logs import Log, Logs
from pinecall_runtime.calls.repository.heads import Claim
from pinecall_runtime.calls.store import Store
from pinecall_runtime.enums import Env
from pinecall_runtime.kit.auth import Scope
from pinecall_runtime.kit.crypto import Vault
from pinecall_runtime.kit.text import JsonObject
from pinecall_runtime.wire.base import Entry
from tests.conftest import needs_the_database

ORG = "clinica"
VAULT = Vault(Fernet.generate_key().decode())
TAKE_MESSAGE = ToolSpec(
    "takeMessage",
    "Writes down who called.",
    {"type": "object", "properties": {"name": {}, "about": {}}},
    pii=frozenset({"name"}),
)
CONFIG = AgentConfig(slug="desk", tools=(TAKE_MESSAGE,), state_fields={"patient": "pii"})
ASKED: JsonObject = {
    "call_id": "tc_1",
    "name": "takeMessage",
    "arguments": {"name": "Ana Lopez", "about": "Ana Lopez wants a refund"},
}


def entry_of(kind: str, data: JsonObject, seq: int = 3) -> Entry:
    return Entry(seq=seq, ts=1.0, call="CA_1", agent="desk", type=kind, ephemeral=False, data=data)


def test_an_argument_named_pii_is_masked_and_the_others_hold_what_they_say_of_it() -> None:
    kept = private.split("tool.call", ASKED, CONFIG, ["Ana Lopez"])
    assert kept.kept["arguments"] == {"name": "***", "about": "*** wants a refund"}
    assert kept.private == {"arguments": {"name": "Ana Lopez", "about": "Ana Lopez wants a refund"}}


def test_a_state_field_that_holds_the_value_is_masked_though_it_was_never_declared() -> None:
    data: JsonObject = {
        "state": {"message": {"name": "Ana Lopez", "about": "a refund"}, "stage": "done"},
        "changed": [],
    }
    kept = private.split("state.changed", data, CONFIG, ["Ana Lopez"])
    assert kept.kept["state"] == {"message": {"name": "***", "about": "a refund"}, "stage": "done"}
    assert kept.private == {"state": {"message": {"name": "Ana Lopez", "about": "a refund"}}}


def test_a_field_declared_pii_is_masked_whole_with_or_without_a_secret() -> None:
    data: JsonObject = {"state": {"patient": {"id": 7}, "stage": "ask"}, "changed": ["patient"]}
    kept = private.split("state.changed", data, CONFIG)
    assert kept.kept["state"] == {"patient": "***", "stage": "ask"}


def test_what_a_tool_answered_is_masked_of_the_value_it_echoes_whole_or_inside_a_sentence() -> None:
    result: JsonObject = {"call_id": "tc_1", "name": "t"}
    echoed = private.split("tool.result", {**result, "output": {"name": "Ana Lopez", "id": 4}}, CONFIG, ["Ana Lopez"])
    assert echoed.kept["output"] == {"name": "***", "id": 4}
    said = private.split("tool.result", {**result, "output": "Saved for Ana Lopez."}, CONFIG, ["Ana Lopez"])
    assert said.kept["output"] == "Saved for ***."
    assert said.private == {"output": "Saved for Ana Lopez."}
    failed = private.split("tool.result", {**result, "error": "no patient Ana Lopez"}, CONFIG, ["Ana Lopez"])
    assert failed.kept["error"] == "no patient ***"


def test_a_line_the_agent_logged_is_masked_of_the_value() -> None:
    line: JsonObject = {"name": "booked", "data": {"who": "Ana Lopez", "n": 2}}
    assert private.split("custom", line, CONFIG, ["Ana Lopez"]).kept["data"] == {"who": "***", "n": 2}


def test_what_was_said_is_never_masked() -> None:
    said: JsonObject = {"speech_id": "s1", "text": "Soy Ana Lopez"}
    assert private.split("turn.user", said, CONFIG, ["Ana Lopez"]).kept == said


def test_a_number_that_was_an_argument_is_masked_as_the_number_it_was() -> None:
    state: JsonObject = {"state": {"dni": 12345678, "age": 31}, "changed": []}
    assert private.split("state.changed", state, CONFIG, ["12345678"]).kept["state"] == {"dni": "***", "age": 31}


def test_a_longer_value_is_masked_whole_before_a_shorter_one_it_holds() -> None:
    privacy = private.Privacy(VAULT, CONFIG)
    privacy.values.update(["Ana", "Ana Lopez"])
    assert privacy.secrets() == ["Ana Lopez", "Ana"]
    line: JsonObject = {"name": "x", "data": {"who": "Ana Lopez"}}
    assert private.split("custom", line, CONFIG, privacy.secrets()).kept["data"] == {"who": "***"}


def test_a_value_is_masked_only_where_it_stands_as_a_whole_word() -> None:
    """`Ana` is no part of `Banana` or `Anabel`; it is one in `Ana's`, in `Ana,` and in `(Ana)`."""
    line: JsonObject = {"name": "x", "data": {"said": "Banana and Anabel, but Ana's, Ana, (Ana) and José Ana"}}
    kept = private.split("custom", line, CONFIG, ["Ana"])
    assert kept.kept["data"] == {"said": "Banana and Anabel, but ***'s, ***, (***) and José ***"}


def test_a_value_is_masked_whole_where_it_is_a_number_and_not_inside_another_number() -> None:
    state: JsonObject = {
        "state": {"dni": 12345678, "other": 123456789, "text": "1234567890 and 12345678"},
        "changed": [],
    }
    kept = private.split("state.changed", state, CONFIG, ["12345678"])
    assert kept.kept["state"] == {"dni": "***", "other": 123456789, "text": "1234567890 and ***"}


def test_a_value_shorter_than_three_characters_is_never_learned_and_one_of_three_is() -> None:
    privacy = private.Privacy(VAULT, CONFIG)
    for name in ("7", "ok", "Al", "  Bo ", ""):
        privacy.learn("tool.call", {**ASKED, "arguments": {"name": name, "about": "x"}})
    assert privacy.values == set()
    assert private.LEAST_SECRET_CHARS == 3
    privacy.learn("tool.call", {**ASKED, "arguments": {"name": "Ann", "about": "x"}})
    assert privacy.values == {"Ann"}


def test_an_entry_with_nothing_private_is_the_entry_itself() -> None:
    data: JsonObject = {"state": {"stage": "ask"}, "changed": ["stage"]}
    assert private.split("state.changed", data, CONFIG, ["Ana Lopez"]).kept is data


def test_the_values_of_a_tool_call_are_learned_by_the_arguments_the_tool_lists_and_a_blank_is_none() -> None:
    privacy = private.Privacy(VAULT, CONFIG)
    privacy.learn("tool.call", ASKED)
    assert privacy.values == {"Ana Lopez"}
    privacy.learn("tool.call", {**ASKED, "arguments": {"name": "  ", "about": "x"}})
    privacy.learn("state.changed", {"state": {"name": "Eve"}, "changed": []})
    assert privacy.values == {"Ana Lopez"}


def test_the_masked_entry_gets_back_what_was_kept_aside_member_by_member_or_whole() -> None:
    written: JsonObject = {"state": {"message": {"name": "Ana Lopez"}, "stage": "done"}, "changed": []}
    state = private.split("state.changed", written, CONFIG, ["Ana Lopez"])
    result = private.split(
        "tool.result", {"call_id": "tc_1", "name": "t", "output": "For Ana Lopez."}, CONFIG, ["Ana Lopez"]
    )
    opened = private.restored(entry_of("state.changed", state.kept), state.private)
    assert opened.data["state"] == {"message": {"name": "Ana Lopez"}, "stage": "done"}
    assert private.restored(entry_of("tool.result", result.kept), result.private).data["output"] == "For Ana Lopez."


async def a_log(store: Store, call: str, agent: str) -> Log:
    logs = Logs(store)
    await store.claim(call, agent, ORG, Claim(Scope(ORG, Env.sandbox), Versions(config=1)))
    log = logs.writing(call, agent)
    log.privacy = private.Privacy(VAULT, CONFIG)
    return log


@needs_the_database
async def test_a_log_masks_the_value_in_the_state_the_result_and_the_line_that_echo_it(
    store: Store, call: str, agent: str
) -> None:
    log = await a_log(store, call, agent)
    await log.append("tool.call", ASKED)
    await log.append("state.changed", {"state": {"message": {"name": "Ana Lopez"}}, "changed": ["message"]})
    await log.answer({"call_id": "tc_1", "name": "takeMessage", "output": {"name": "Ana Lopez"}})
    await log.append("custom", {"name": "booked", "data": {"who": "Ana Lopez"}})
    kept = {entry.type: entry for entry in await store.whole(call)}
    assert kept["tool.call"].data["arguments"] == {"name": "***", "about": "*** wants a refund"}
    assert kept["state.changed"].data["state"] == {"message": {"name": "***"}}
    assert kept["tool.result"].data["output"] == {"name": "***"}
    assert kept["custom"].data["data"] == {"who": "***"}
    assert "Ana Lopez" not in str([entry.data for entry in kept.values()])


@needs_the_database
async def test_the_app_and_a_reader_of_the_whole_log_get_the_values_back(store: Store, call: str, agent: str) -> None:
    log = await a_log(store, call, agent)
    await log.append("tool.call", ASKED)
    await log.append("state.changed", {"state": {"message": {"name": "Ana Lopez"}}, "changed": ["message"]})
    await log.answer({"call_id": "tc_1", "name": "takeMessage", "output": {"name": "Ana Lopez"}})
    # Another gateway reads it: nothing of it in memory, the sealed copies in the store.
    other = await a_log(store, call, agent)
    opened = {entry.type: entry for entry in await other.whole()}
    assert opened["tool.call"].data["arguments"] == ASKED["arguments"]
    assert opened["state.changed"].data["state"] == {"message": {"name": "Ana Lopez"}}
    assert opened["tool.result"].data["output"] == {"name": "Ana Lopez"}
    stored = {entry.type: entry for entry in await store.whole(call)}
    assert (await other.opened(stored["tool.result"])).data["output"] == {"name": "Ana Lopez"}


@needs_the_database
async def test_a_gateway_that_never_saw_the_tool_call_learns_its_values_from_the_store(
    store: Store, call: str, agent: str
) -> None:
    asked = await a_log(store, call, agent)
    await asked.append("tool.call", ASKED)
    writing = await a_log(store, call, agent)
    await writing.append("state.changed", {"state": {"message": {"name": "Ana Lopez"}}, "changed": ["message"]})
    state = next(entry for entry in await store.whole(call) if entry.type == "state.changed")
    assert state.data["state"] == {"message": {"name": "***"}}


@needs_the_database
async def test_an_agent_that_declares_nothing_private_is_never_masked(store: Store, call: str, agent: str) -> None:
    logs = Logs(store)
    await store.claim(call, agent, ORG, Claim(Scope(ORG, Env.sandbox), Versions(config=1)))
    log = logs.writing(call, agent)
    log.privacy = private.Privacy(VAULT, AgentConfig(slug="desk", tools=(ToolSpec("t", "T.", {"type": "object"}),)))
    await log.append("custom", {"name": "x", "data": {"who": "Ana Lopez"}})
    assert (await store.whole(call))[0].data["data"] == {"who": "Ana Lopez"}
