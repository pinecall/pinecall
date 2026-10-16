"""The door, pinned by name: adding to what `import pinecall` gives is done here, on purpose."""

import re

import pinecall

THE_DOOR = [
    "Agent",
    "Block",
    "Blocks",
    "CallLine",
    "CallWorld",
    "Change",
    "Client",
    "DeclarationRefused",
    "DevRefused",
    "EventMeta",
    "Drawing",
    "Line",
    "Logged",
    "NotAStage",
    "NotConnected",
    "PinecallError",
    "Refused",
    "ToolFailed",
    "UnauthoredWrite",
    "Who",
    "WireError",
    "__version__",
    "hold",
    "improvise",
    "judge",
    "knowledge",
    "llm",
    "panel",
    "render",
    "show_prompt",
    "state",
    "stt",
    "tool",
    "voice",
    "words",
]


def test_the_door_gives_exactly_the_names_pinned_here() -> None:
    assert sorted(pinecall.__all__) == sorted(THE_DOOR)


def test_every_name_on_the_door_is_reachable_from_it() -> None:
    assert [name for name in pinecall.__all__ if not hasattr(pinecall, name)] == []


def test_a_class_on_the_door_is_named_by_the_door_and_not_by_its_module() -> None:
    assert pinecall.PinecallError.__module__ == "pinecall"
    assert pinecall.WireError.__module__ == "pinecall"
    assert repr(pinecall.PinecallError("x")) == "PinecallError('x')"


def test_the_version_is_three_numbers() -> None:
    assert re.fullmatch(r"\d+\.\d+\.\d+", pinecall.__version__)
