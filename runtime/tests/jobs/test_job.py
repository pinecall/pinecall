"""The worker's stages from the gateway's answer, the realtime model only where handed out; a hang-up ends the call."""

from collections.abc import AsyncGenerator
from typing import cast

import pytest
from livekit.agents import JobContext

from pinecall_runtime.agents.schemas import PipelineKeys, RunningStage
from pinecall_runtime.calls.context import Route
from pinecall_runtime.calls.service import CALLER_HUNG_UP
from pinecall_runtime.enums import Channel, Env
from pinecall_runtime.exceptions import GatewayUnavailable, ValidationError
from pinecall_runtime.jobs.service.client import GatewayClient
from pinecall_runtime.jobs.service.job import (
    SESSION_FAILED,
    _follow_commands,
    _test_line,
    follow_command,
    pipeline_of,
    session_refused,
)
from pinecall_runtime.session import service as session
from pinecall_runtime.telephony.schemas import RingAtTestLine
from pinecall_runtime.wire.base import BatchedEntry, Command, Entry
from pinecall_runtime.wire.dispatch import Dispatch
from tests.channels.test_routes import A_PHONE, CALLER, IN_THE_SANDBOX, NUMBER

STAGE = RunningStage(vendor="acme", credentials="k", model="acme-1")


async def test_the_callers_hang_up_on_the_stream_is_the_caller_gone_and_no_command_of_the_apps() -> None:
    """The gateway's own word on the stream ends the call as the caller's; the session is never asked to apply it."""
    gone: list[str] = []
    said = Command(type=CALLER_HUNG_UP, agent="clinica-norte", call="call_1", id=None, data={})
    await follow_command(cast(session.Session, object()), said, lambda: gone.append("caller"))
    assert gone == ["caller"]


def test_an_answer_with_no_realtime_model_builds_none() -> None:
    answer = PipelineKeys.model_validate({"llm": STAGE, "stt": STAGE, "tts": STAGE})
    assert pipeline_of(answer).realtime is None


def test_a_realtime_model_handed_out_is_the_pipelines_beside_its_llm() -> None:
    talking = RunningStage(vendor="xai", credentials="k", model="grok-voice-3.0", options={"voice": "eve"})
    built = pipeline_of(PipelineKeys(llm=STAGE, stt=STAGE, tts=STAGE, realtime=talking))
    assert built.realtime is not None
    assert (built.realtime.vendor, built.realtime.model, dict(built.realtime.options)) == (
        "xai",
        "grok-voice-3.0",
        {"voice": "eve"},
    )
    assert built.llm.model == "acme-1"


def test_the_answer_leaves_out_a_realtime_model_nobody_names_for_a_worker_of_the_version_before() -> None:
    answer = PipelineKeys(llm=STAGE, stt=STAGE, tts=STAGE)
    assert "realtime" not in answer.model_dump(exclude_unset=True)


class Breaking:
    """A call's session that breaks on a command with what is no refusal of ours."""

    async def apply(self, _command: object) -> None:
        """Break."""
        raise RuntimeError("the session broke")


class Streaming:
    """The gateway's command stream for a call: one the session breaks on, then the caller's hang-up."""

    async def commands(self, call: str) -> AsyncGenerator[Command]:
        """The two commands, in order."""
        yield Command(type="state.set", agent="clinica-norte", call=call, id=None, data={"state": {}})
        yield Command(type=CALLER_HUNG_UP, agent="clinica-norte", call=call, id=None, data={})


# A follower that ended on a command the session broke on left the call deaf to its hang-up and to a
# supervisor's end, with nothing said of why (K F5's class of seat that never frees).
async def test_a_command_the_session_breaks_on_is_said_with_its_call_and_the_next_one_is_heard(
    caplog: pytest.LogCaptureFixture,
) -> None:
    gone: list[str] = []
    await _follow_commands(
        cast(GatewayClient, Streaming()), cast(session.Session, Breaking()), "call_1", lambda: gone.append("caller")
    )
    assert gone == ["caller"]
    assert "a command of the app failed on call_1" in caplog.text


class Sealing:
    """A gateway that keeps what a call's writer sent it and how the call was sealed."""

    def __init__(self) -> None:
        self.written: list[BatchedEntry] = []
        self.sealed_as: list[tuple[str, str]] = []

    async def append_many(self, call: str, entries: list[BatchedEntry], *, after: int) -> list[Entry]:
        self.written.extend(entries)
        return [
            Entry(seq=after + n + 1, ts=one.ts, call=call, agent="a", type=one.type, ephemeral=False, data=one.data)
            for n, one in enumerate(entries)
        ]

    async def sealed(self, call: str, sealing: object) -> None:
        self.sealed_as.append((call, str(getattr(sealing, "outcome", ""))))


class Shutting:
    """A job context that remembers why it was shut down."""

    def __init__(self) -> None:
        self.reasons: list[str] = []

    def shutdown(self, reason: str = "") -> None:
        self.reasons.append(reason)


# A worker whose session could not be built left the call ringing for the reaper's ten minutes, sealed
# `drained` with nothing of why (2026-11-05, a Soniox model the plugin refused as an argument).
async def test_a_session_the_worker_cannot_build_ends_the_call_at_once_with_the_refusal_on_its_log() -> None:
    gateway, ctx = Sealing(), Shutting()
    refused = ValidationError("soniox refused its STT: STT.__init__() got an unexpected keyword argument 'model'")
    await session_refused(cast(JobContext, ctx), cast(GatewayClient, gateway), "call_1", refused)
    assert [(one.type, one.data.get("code"), one.data.get("recoverable")) for one in gateway.written] == [
        ("error", SESSION_FAILED, False),
        ("call.ended", None, None),
    ]
    assert gateway.written[0].data["message"] == str(refused)
    assert gateway.written[1].data["reason"] == "error"
    assert gateway.sealed_as == [("call_1", f"the session could not be built: {refused}")]
    assert ctx.reasons == [SESSION_FAILED]


class Handing:
    """A gateway that answers whose a ring at the test line is, or fails to."""

    def __init__(self, handed: RingAtTestLine | Exception) -> None:
        self.handed = handed
        self.asked: list[tuple[str, str]] = []

    async def test_line_rings_for(self, number: str, caller: str) -> RingAtTestLine:
        self.asked.append((number, caller))
        if isinstance(self.handed, Exception):
            raise self.handed
        return self.handed


AT_THE_LINE = Dispatch(org="org_box", env=Env.sandbox)


async def test_a_ring_at_the_test_line_goes_on_as_the_callers_orgs_agents_in_the_copy_that_takes_it() -> None:
    gateway = Handing(RingAtTestLine(org="org_b", agent="front", holder="m_ana"))
    route, moved = await _test_line(cast(GatewayClient, gateway), AT_THE_LINE, A_PHONE, IN_THE_SANDBOX)
    assert route == Route(org="org_b", agent="front", channel=Channel.phone, number=NUMBER, env=Env.sandbox)
    assert (moved.org, moved.agent, moved.holder, moved.env, moved.caller) == (
        "org_b",
        "front",
        "m_ana",
        Env.sandbox,
        CALLER,
    )
    assert gateway.asked == [(NUMBER, CALLER)]


@pytest.mark.parametrize(
    "handed",
    [
        RingAtTestLine(),
        RingAtTestLine(org="org_b"),
        RingAtTestLine(org="org_b", agent="front"),
        GatewayUnavailable("the gateway did not answer"),
    ],
    ids=["nobody's phone", "no agent named among several", "nobody holds the agent", "the gateway is down"],
)
async def test_a_ring_the_gateway_hands_to_nobody_stays_with_the_numbers_own_agent(
    handed: RingAtTestLine | Exception,
) -> None:
    route, moved = await _test_line(cast(GatewayClient, Handing(handed)), AT_THE_LINE, A_PHONE, IN_THE_SANDBOX)
    assert (route, moved) == (IN_THE_SANDBOX, AT_THE_LINE)
