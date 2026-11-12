"""A call to run a session on: its context, its agent, and the platform around it, all real."""

from collections.abc import AsyncIterator, Sequence
from dataclasses import dataclass, field
from datetime import date

import pytest

from runtime.agents.declaration import Declaration
from runtime.calls.context import CallContext, Contact, Route, log_name
from runtime.calls.log.log import Log
from runtime.calls.log.store import Store
from runtime.enums import Channel, Direction
from runtime.kit.text import Json, JsonObject
from runtime.providers.service.llm_requests import LLMWithRequest
from runtime.providers.stage import Running
from runtime.session.call import Call, ToolUse
from runtime.session.session import Place, Session
from runtime.session.text import text_session
from runtime.wire.base import BatchedEntry, Entry
from runtime.wire.events import ToolCall
from runtime.wire.metrics import ModelUsage
from runtime.wire.parts import PlatformTool, ToolResult
from tests.fakes.acme import ACME, AcmeLLM
from tests.fakes.livekit import Server

AGENT = "clinica-norte"
A_NUMBER = "+59829001199"
THE_CALLER = "+59899123456"
MONDAY = date(2026, 9, 28)


def context_of(
    call: str,
    channel: Channel = Channel.whatsapp,
    *,
    contact: Contact | None = None,
    run: str | None = None,
) -> CallContext:
    """A call of the agent's through its number, on the channel."""
    route = Route(org="org_1", agent=AGENT, channel=channel, number=None if channel == "web" else A_NUMBER)
    return CallContext(
        call=call,
        channel=channel,
        direction=Direction.inbound,
        caller=THE_CALLER,
        route=route,
        today=MONDAY,
        contact=contact,
        run=run,
    )


@dataclass
class Box:
    """The platform a session reaches: the call's real log, and a gateway that answers as told."""

    # One writer's batches, numbered on the call's log as the gateway numbers them.

    log: Log
    answers: dict[str, ToolResult] = field(default_factory=dict[str, ToolResult])
    found: dict[PlatformTool, JsonObject] = field(default_factory=dict[PlatformTool, JsonObject])
    failing: set[PlatformTool] = field(default_factory=set[PlatformTool])
    used: list[ToolUse] = field(default_factory=list[ToolUse])
    lookups: list[tuple[PlatformTool, JsonObject]] = field(default_factory=list[tuple[PlatformTool, JsonObject]])
    sealed: list[tuple[list[ModelUsage], str]] = field(default_factory=list[tuple[list[ModelUsage], str]])

    async def append_many(self, entries: Sequence[BatchedEntry], *, after: int) -> list[Entry]:
        """The writer's entries on the call's log."""
        return await self.log.append_many(entries, after=after)

    # The gateway writes the round trip, as ToolCalls does, around the app's answer.
    async def run_tool(self, use: ToolUse, speech: str | None) -> ToolResult:
        """What the app answers the tool, or `ok`, written as the gateway writes it."""
        self.used.append(use)
        called = ToolCall(call_id=use.call_id, name=use.name, arguments=use.arguments, speech_id=speech)
        await self.log.append("tool.call", called.dump())
        answered = self.answers.get(use.name)
        result = answered or ToolResult(call_id=use.call_id, name=use.name, output="ok")
        await self.log.append("tool.result", result.dump())
        return result

    async def look_up(self, tool: PlatformTool, arguments: JsonObject, speech: str | None) -> JsonObject:
        """What the index finds, nothing, or a failure."""
        del speech
        self.lookups.append((tool, arguments))
        if tool in self.failing:
            raise ConnectionError(f"the {tool} index did not answer")
        return self.found.get(tool, {"facts": []} if tool == "recall" else {"chunks": []})

    # The gateway's seal prices, judges and writes call.score; the log is sealed by it.
    async def seal(self, usage: list[ModelUsage], outcome: str) -> None:
        """Keep what the session handed over, and end the log."""
        self.sealed.append((usage, outcome))
        await self.log.append("call.score", {"judges": [], "panel": [], "judge_calls": 0, "not_judged": "none"})

    async def release_seal(self) -> None:
        """Nothing waits for the app's end hook here."""


@pytest.fixture
def box(store: Store, call: str) -> Box:
    """The platform around one call, on the test's own log, the acme vendor installed."""
    return Box(Log(store, call, AGENT))


def a_session(
    box: Box,
    declaration: Declaration,
    *replies: list[Json],
    contact: Contact | None = None,
    run: str | None = None,
) -> Session:
    """A written session whose model answers with the replies, in order."""
    assert box.log.call is not None
    call = Call(context_of(box.log.call, contact=contact, run=run), declaration, box)
    scripted: list[Json] = list(replies)
    script: JsonObject = {"replies": scripted}
    return text_session(call, Running(ACME, "a-key", options=script), Place())


def model_of(session: Session) -> AcmeLLM:
    """The scripted model the session runs."""
    (staged,) = session.built
    assert isinstance(staged, LLMWithRequest) and isinstance(staged.built, AcmeLLM)
    return staged.built


def heard_live(box: Box) -> list[Entry]:
    """Every entry the log takes from now on, the ephemeral ones too."""
    seen: list[Entry] = []

    async def tap(entry: Entry) -> None:
        seen.append(entry)

    box.log.tap(tap)
    return seen


async def kinds(store: Store, call: str) -> list[str]:
    """The types of the call's entries, in log order."""
    return [entry.type for entry in await store.whole_of(log_name(call, AGENT))]


@pytest.fixture
async def server() -> AsyncIterator[Server]:
    """Livekit's server client, its doors the test's, closed at the end."""
    opened = Server()
    yield opened
    await opened.aclose()
