"""Tests for what a class declares of its environment: the shapes a declaration is written in."""

from pinecall.wire.config import AgentConfig, EventSpec, HoldConfig


def test_a_key_python_cannot_spell_travels_by_its_wire_name() -> None:
    spec = EventSpec.read({"name": "slot.released", "from": ["app"]}, "event")
    assert spec.from_ == ["app"]
    assert spec.written() == {"name": "slot.released", "from": ["app"]}


def test_a_melody_and_a_look_the_class_declares_are_written_as_the_gateway_reads_them() -> None:
    config = AgentConfig.read(
        {
            "hold": {"clip": "ab" * 32, "name": "wait.mp3", "after_s": 1.5},
            "widget": {"accent": "#0a0"},
        },
        "c",
    )
    assert isinstance(config.hold, HoldConfig)
    assert config.hold.after_s == 1.5
    assert config.written() == {
        "hold": {"clip": "ab" * 32, "name": "wait.mp3", "after_s": 1.5},
        "widget": {"accent": "#0a0"},
    }
