"""A call to run a session on: its context, its agent, and the platform around it, all real."""

import asyncio
import time
from collections.abc import AsyncIterator, Awaitable, Callable, Sequence
from dataclasses import dataclass, field
from datetime import date

import pytest
from livekit import rtc
from livekit.agents import llm, metrics, stt
from livekit.agents.language import LanguageCode
from livekit.protocol.sip import SIPOutboundConfig

from runtime.agents.declaration import Declaration, ToolSpec
from runtime.calls.context import CallContext, Contact, Route, log_name
from runtime.calls.log.log import Log
from runtime.calls.log.store import Store
from runtime.enums import Channel, Direction
from runtime.kit.text import Json, JsonObject
from runtime.providers.service.llm_requests import LLMWithRequest
from runtime.providers.stage import Pipeline, Running, TurnModel
from runtime.session.call import Call, ToolUse
from runtime.session.room import CallRoom
from runtime.session.session import Place, Session
from runtime.session.text import text_session
from runtime.session.voice import voice_session
from runtime.telephony.service.legs import CALLER_NUMBER, Legs, Trunk
from runtime.wire.base import BatchedEntry, Entry
from runtime.wire.commands import EndVerb, ReleaseVerb, SayVerb, SupervisorVerb, TakeoverVerb, TransferVerb, WhisperVerb
from runtime.wire.events import ToolCall
from runtime.wire.metrics import ModelUsage
from runtime.wire.parts import PlatformTool, Supervisor, ToolResult
from tests.fakes.acme import ACME, AcmeLLM
from tests.fakes.livekit import Room as AnOfflineRoom
from tests.fakes.livekit import Server, seat

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
    direction: Direction = Direction.inbound,
) -> CallContext:
    """A call of the agent's through its number, on the channel."""
    route = Route(org="org_1", agent=AGENT, channel=channel, number=None if channel == "web" else A_NUMBER)
    return CallContext(
        call=call,
        channel=channel,
        direction=direction,
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

    def through(self, run: "RunTool") -> "Through":
        """This box with the app's tools run through this function."""
        return Through(self, run)


type RunTool = Callable[[ToolUse, str | None], Awaitable[ToolResult]]
type Seal = Callable[[list[ModelUsage], str], Awaitable[None]]
type Release = Callable[[], Awaitable[None]]
type LookUp = Callable[[PlatformTool, JsonObject, str | None], Awaitable[JsonObject]]


@dataclass
class Through:
    """The box with the app's tools, or its seal, run through a test's own function: slowed, refused, read."""

    box: Box
    run: RunTool | None = None
    sealing: Seal | None = None
    releasing: Release | None = None
    looking: LookUp | None = None

    async def append_many(self, entries: Sequence[BatchedEntry], *, after: int) -> list[Entry]:
        """The box's log."""
        return await self.box.append_many(entries, after=after)

    async def run_tool(self, use: ToolUse, speech: str | None) -> ToolResult:
        """The test's function, else the box's."""
        return await (self.run or self.box.run_tool)(use, speech)

    async def look_up(self, tool: PlatformTool, arguments: JsonObject, speech: str | None) -> JsonObject:
        """The test's index, else the box's."""
        return await (self.looking or self.box.look_up)(tool, arguments, speech)

    async def seal(self, usage: list[ModelUsage], outcome: str) -> None:
        """The test's seal, else the box's."""
        await (self.sealing or self.box.seal)(usage, outcome)

    async def release_seal(self) -> None:
        """The test's word that the app's end hook ran, else the box's."""
        await (self.releasing or self.box.release_seal)()


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
    place_of: Callable[[Call], Place] | None = None,
    direction: Direction = Direction.inbound,
) -> Session:
    """A written session whose model answers with the replies, in order; in the place made for its call, if any."""
    assert box.log.call is not None
    call = Call(context_of(box.log.call, contact=contact, run=run, direction=direction), declaration, box)
    scripted: list[Json] = list(replies)
    script: JsonObject = {"replies": scripted}
    return text_session(call, Running(ACME, "a-key", options=script), Place() if place_of is None else place_of(call))


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


# ── what the session tests share: a supervisor, a spoken call, livekit's own events ──


A_SUPERVISOR = Supervisor(id="mem_1", name="Ana")


NOBODY = Declaration(slug="clinica-norte")


def supervised(
    verb: SayVerb | WhisperVerb | TakeoverVerb | ReleaseVerb | EndVerb | TransferVerb,
) -> SupervisorVerb:
    return SupervisorVerb(by=A_SUPERVISOR, verb=verb)


async def hear(session: Session, text: str) -> str:
    """The contact's message into the call; the agent's reply, or nothing while the line is not the agent's."""
    return (await session.hear(text)).reply


async def settled() -> None:
    """Let livekit's tasks and the call's queue run."""
    await asyncio.sleep(0.05)


def spoken_call(
    box: Box,
    config: Declaration,
    *,
    ends_the_turn: bool = False,
    keyterms: bool = False,
    turn_model: TurnModel = "v1-mini",
    realtime: str | None = None,
    server: Server | None = None,
    hears: tuple[str, ...] = (),
) -> Session:
    """A phone call's session on acme's stages, in its room when a server is given."""
    assert box.log.call is not None
    call = Call(context_of(box.log.call, Channel.phone), config, box)
    ears: JsonObject = {"keyterms": True} if keyterms else {}
    if hears:
        ears["hears"] = list(hears)
    stages = Pipeline(
        llm=Running(ACME, "k"),
        stt=Running(ACME, "k", ends_the_turn=ends_the_turn, options=ears, turn_model=turn_model),
        tts=Running(ACME, "k"),
        realtime=None if realtime is None else Running(realtime, "k", model="voice-1"),
    )
    return voice_session(call, stages, Place() if server is None else Place(room=a_room(box, call, server)))


async def no_audio() -> AsyncIterator[rtc.AudioFrame]:
    frames: tuple[rtc.AudioFrame, ...] = ()
    for frame in frames:
        yield frame


def speech_event(text: str) -> stt.SpeechEvent:
    return stt.SpeechEvent(
        type=stt.SpeechEventType.FINAL_TRANSCRIPT,
        alternatives=[stt.SpeechData(language=LanguageCode("es"), text=text)],
    )


def a_block(*, cancelled: bool = False) -> metrics.LLMMetrics:
    return metrics.LLMMetrics(
        label="acme", request_id="r1", timestamp=time.time(), duration=0.8, ttft=0.2,
        cancelled=cancelled, completion_tokens=5, prompt_tokens=20, prompt_cached_tokens=0,
        total_tokens=25, tokens_per_second=6.0,
    )  # fmt: skip


def a_room(box: Box, call: Call, server: Server) -> CallRoom:
    caller = seat(
        "sip_caller",
        kind=rtc.ParticipantKind.PARTICIPANT_KIND_SIP,
        attributes={CALLER_NUMBER: THE_CALLER},
    )
    assert box.log.call is not None

    async def trunks(_to: str) -> Trunk:
        return Trunk(SIPOutboundConfig(hostname="sip.carrier.test"))

    async def claim(_code: str) -> None:
        return

    async def sent_on(_to: str) -> None:
        return

    legs = Legs(trunk=trunks, send_on=sent_on)
    return CallRoom(call, AnOfflineRoom(box.log.call, caller), server, legs=legs, claim=claim)


# ── the declarations the session tests share ──

BOOK = ToolSpec(
    "book",
    "Book a table for a day.",
    {"type": "object", "properties": {"day": {"type": "string"}}},
    confirm="Reservado para el {{day}}, {{result.table}} {{result.missing}}.",
)
CANCEL = ToolSpec("cancel", "Cancel the booking.", {"type": "object", "properties": {}})
BOOKING = Declaration(
    slug="clinica-norte",
    tools=(BOOK, CANCEL),
    events={"paid": frozenset({"app"}), "clicked": frozenset({"participant"})},
)
LOOK = ToolSpec(
    "look",
    "Look at the agenda for a day.",
    {"type": "object", "properties": {"day": {"type": "string"}}},
    announce="Un momento, miro la agenda.",
)
LOOKING = Declaration(slug="clinica-norte", tools=(LOOK,))
TALKATIVE = ToolSpec(
    "look",
    "Look at the agenda for a day.",
    {"type": "object", "properties": {"day": {"type": "string"}}},
    announce="Un momento, miro la agenda.",
    delayed="Sigo buscando, un segundo.",
    delayed_after_s=0.05,
    failed="No pude consultar la agenda ahora mismo.",
)
TALKING = Declaration(slug="clinica-norte", tools=(TALKATIVE,))
POINT = ToolSpec(
    "point",
    "Point at an element of the caller's page.",
    {"type": "object", "properties": {"ref": {"type": "string"}}},
    quiet=True,
)
POINTING = Declaration(slug="clinica-norte", tools=(POINT,))


def output_of(session: Session, call_id: str) -> llm.FunctionCallOutput:
    """What the model was last sent of the tool call by this id."""
    items = model_of(session).requests[-1].items
    return next(item for item in items if isinstance(item, llm.FunctionCallOutput) and item.call_id == call_id)
