"""The package against its wire: each command sent by one module or nobody's; each event folded."""

import re
from pathlib import Path

from pinecall.wire.commands import COMMANDS
from pinecall.wire.events import EVENTS

SOURCE = Path(__file__).resolve().parents[2] / "src" / "pinecall"

# Who sends each command: TypeScript's `test/the-wire.test.ts`, by this package's files.
SENT_BY: dict[str, tuple[str, ...]] = {
    "call.py": (
        "agent.say",
        "agent.reply",
        "room.send",
        "call.hangup",
        "call.transfer",
        "call.attention",
        "call.hold",
        "call.unhold",
        "call.dtmf",
        "call.claim",
        "call.callback",
        "call.opt_out",
    ),
    "_room.py": ("room.invite", "participant.mute", "participant.remove"),
    "_calls.py": ("call.log", "call.event", "prompt.set", "tools.set", "state.set", "tool.result"),
    "_agent_socket.py": ("agent.register", "agent.configure", "agent.drain", "dev.answer", "ping"),
}

NOT_THE_SDKS: dict[str, str] = {
    "call.dial": "placed through POST /v1/calls; the app socket refuses it",
    "call.mute": "the desk's: a supervisor mutes the agent",
    "call.unmute": "the desk's: a supervisor unmutes the agent",
    "session.configure": "the gateway's own",
    "supervisor.verb": "a supervisor's socket",
}

FOLDED_BY: dict[str, tuple[str, ...]] = {
    "_agent_socket.py": (
        "agent.registered",
        "agent.configured",
        "agent.draining",
        "dev.request",
        "tool.call",
        "error",
    ),
    "bridge.py": ("call.started", "call.attached", "event.received", "memory.ops"),
    "_calls.py": ("call.ringing", "call.dialing", "state.changed"),
    "call.py": (
        "turn.user",
        "turn.agent",
        "call.claimed",
        "call.transferred",
        "attention.answered",
        "participant.joined",
        "participant.left",
        "participant.speaking",
        "call.ended",
    ),
}

THE_GATEWAYS = "the gateway's or the console's to read; an app acts on none of it"
A_MEASURE = "a measure the runtime keeps; the reducer folds it for a reader of the log"
THE_DESKS = "a supervisor's move; what it caused arrives as turns and prompt changes"
THE_LOGS = "a log reader's, which observe() and the reducer handle"

IGNORED: dict[str, str] = {
    **dict.fromkeys(
        (
            "agent.state",
            "user.state",
            "attention.requested",
            "call.line",
            "call.score",
            "call.summary",
            "callback.requested",
            "code.claimed",
            "code.issued",
            "confirm.request",
            "confirm.granted",
            "confirm.declined",
            "credits.exhausted",
            "evals.spent",
            "docs.sources",
            "fleet.full",
            "release.changed",
            "run.changed",
            "worker.changed",
            "message.taken",
            "message.waiting",
            "prompt.changed",
            "tools.changed",
            "room.opened",
            "room.sent",
            "track.published",
            "track.unpublished",
            "spend.unusual",
            "vendor.switched",
        ),
        THE_GATEWAYS,
    ),
    **{name: A_MEASURE for name in EVENTS if name.startswith("metrics.")},
    **{name: THE_DESKS for name in EVENTS if name.startswith("supervisor.")},
    "log.caught_up": THE_LOGS,
    "log.gap": THE_LOGS,
    "agent.detached": "another socket letting go of the agent; this one is unaffected",
    "agent.transcript": "a partial line; the finished turn is turn.agent",
    "user.transcript": "a partial line; the finished turn is turn.user",
    "custom": "a line the app itself wrote",
    "dtmf.received": "the runtime's; a tone reaches the model, not the app",
    "pong": "the answer to the ping; the socket being up is the answer",
    "tool.result": "the gateway's echo of the answer this package sent",
}


def named_in(module: str, wire_name: str, model: str) -> bool:
    """Whether the module names the frame: its wire name, or its model's class as a word."""
    text = (SOURCE / module).read_text(encoding="utf-8")
    return f'"{wire_name}"' in text or re.search(rf"\b{model}\b", text) is not None


def test_every_command_is_sent_by_one_module_or_said_to_be_nobodys() -> None:
    owned = [name for names in SENT_BY.values() for name in names]
    assert sorted(owned + list(NOT_THE_SDKS)) == sorted(COMMANDS)
    assert len(owned) == len(set(owned))


def test_the_module_a_command_is_sent_by_names_it() -> None:
    assert [
        f"{module}: {name}"
        for module, names in SENT_BY.items()
        for name in names
        if not named_in(module, name, COMMANDS[name].__name__)
    ] == []


def test_every_event_is_folded_by_one_module_or_ignored_with_a_reason() -> None:
    folded = [name for names in FOLDED_BY.values() for name in names]
    assert sorted(folded + list(IGNORED)) == sorted(EVENTS)
    assert len(folded) == len(set(folded))
    assert all(reason for reason in IGNORED.values())


def test_the_module_an_event_is_folded_by_names_it() -> None:
    assert [
        f"{module}: {name}"
        for module, names in FOLDED_BY.items()
        for name in names
        if not named_in(module, name, EVENTS[name].__name__)
    ] == []
