"""How a job lets a call go: its writer, a call no session ran ended and sealed, and its room."""

from functools import partial

from livekit import api

from pinecall_runtime.calls import service as calls
from pinecall_runtime.fleet import service as fleet
from pinecall_runtime.jobs.service.client import GatewayClient
from pinecall_runtime.session import service as session
from pinecall_runtime.wire.events import CallEnded
from pinecall_runtime.wire.parts import EndedBy, EndReason


# A call has one writer from its open to its seal: a job that ends a call no session runs writes
# through one too, following on from whatever the log took from the writer before it.
def open_writer(gateway: GatewayClient, call: str, *, after: int = 0) -> session.Writing:
    """The call's writer on the gateway's batch endpoint, sending."""
    writing = session.Writing(partial(gateway.append_many, call), call, after=after)
    writing.open()
    return writing


async def end_and_seal(gateway: GatewayClient, writing: session.Writing, ended: CallEnded, outcome: str) -> None:
    """End a call no session ran: its `call.ended` written once, what is queued sent, the seal."""
    writing.write("call.ended", ended)
    await writing.close(session.WRITTEN_WITHIN_S)
    await gateway.sealed(writing.call, calls.SealCallRequest(usage=[], outcome=outcome))


# The agent leaving ends no SIP phone_leg: with the room still up, a phone caller hears a silent
# line until they hang up themselves. A transfer leaves them with the far end and a hand-over with
# the next worker, so only a call its session hung up takes the room with it (the model's end_call
# already did, and a room gone is fine).
async def release_room(server: api.LiveKitAPI, name: str, ended: tuple[EndReason, EndedBy] | None) -> None:
    """Delete the room once the session hung up the call for any reason but a transfer."""
    if ended is not None and ended[0] != "transferred":
        await fleet.close_room(server, name)
