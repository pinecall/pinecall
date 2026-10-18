"""What the processes of a box tell each other outside the log: entries, sockets, jobs."""

from pydantic import BaseModel, ConfigDict

from pinecall_runtime.wire.base import Entry


class Stored(BaseModel):
    """Where a big entry is: the hearer reads it back from the store."""

    log: str
    seq: int


class Travelled(BaseModel):
    """What a message on a log's channel carries: an entry whole, or the address of a big one."""

    model_config = ConfigDict(extra="forbid")

    sender: str
    entry: Entry | None = None
    stored: Stored | None = None


class Bound(BaseModel):
    """A call bound to an app socket another gateway holds, and the seq its pump starts after."""

    call: str
    after: int


class Killed(BaseModel):
    """One agent an app socket is to let go of, and why."""

    agent: str
    why: str


class ForApp(BaseModel):
    """One message for an app socket: a call bound to it, an entry to send it, a stop, or a kill."""

    bound: Bound | None = None
    entry: Entry | None = None
    stop: str | None = None
    kill: Killed | None = None


class JobReport(BaseModel):
    """One thing a job tells its worker: a turn's first audio, an error, or how its call ended."""

    model_config = ConfigDict(frozen=True, extra="ignore")

    first_audio_s: float | None = None
    error: bool = False
    ended: str | None = None
