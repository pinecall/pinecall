"""A call no session ran, ended and sealed through its own writer; and the room a call leaves behind."""

from livekit import api

from runtime.jobs.service.call_client import CallClient
from runtime.livekit import close_room
from runtime.session import service as session
from runtime.wire.events import CallEnded
from runtime.wire.parts import EndedBy, EndReason


# A call has one writer from its open to its seal: a job that ends a call no session runs writes
# through one too, following on from whatever the log took from the writer before it.
def open_writer(link: CallClient, *, after: int = 0) -> session.Writing:
    """The call's writer on the gateway's entries socket, sending."""
    writing = session.Writing(link.append_many, link.call, after=after)
    writing.open()
    return writing


async def end_and_seal(link: CallClient, writing: session.Writing, ended: CallEnded, outcome: str) -> None:
    """End a call no session ran: its `call.ended` written once, what is queued sent, the seal."""
    writing.write("call.ended", ended)
    await writing.close(session.WRITTEN_WITHIN_S)
    await link.seal([], outcome)


# The agent leaving ends no SIP leg: with the room still up, a phone caller hears a silent line
# until they hang up themselves. A transfer leaves them with the far end and a hand-over with the
# next worker, so only a call its session hung up takes the room with it (the model's end_call
# already did, and a room gone is fine). A call still running when its worker's drain ran out has
# no end of its own: the gateway sends its room a job that tells the caller and closes it.
async def release_room(server: api.LiveKitAPI, name: str, ended: tuple[EndReason, EndedBy] | None) -> None:
    """Delete the room once the session hung up the call for any reason but a transfer."""
    if ended is not None and ended[0] != "transferred":
        await close_room(server, name)
