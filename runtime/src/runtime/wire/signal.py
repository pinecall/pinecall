"""What the processes of a box tell each other outside the log: entries, sockets, jobs."""

from pydantic import AliasChoices, BaseModel, ConfigDict, Field

from runtime.wire.base import Entry


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


class Forgotten(BaseModel):
    """A revocation one gateway tells the others: one key by its fingerprint, or every key of a member."""

    model_config = ConfigDict(frozen=True)

    fingerprint: str | None = None
    subject: str | None = None


class Told(BaseModel):
    """One message on a shared state's channel: which process told it, and its share whole."""

    sender: str
    share: object


class Assignment(BaseModel):
    """A key of an env as one gateway last set it: to a holder, or to nobody, and when."""

    model_config = ConfigDict(frozen=True, from_attributes=True)

    env: str
    key: str
    holder: str | None
    at: float


class WorkerStatus(BaseModel):
    """One worker as its last heartbeat left it, and whether the operator cordoned it."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    fleet: str
    worker: str
    # The name the worker registered under with LiveKit: the one a dispatch reaches it by.
    agent_name: str | None = None
    active: int
    max_jobs: int | None
    load: float
    draining: bool
    cordoned: bool
    seen_at: float
    ended: int | None = None
    failed: int | None = None
    errors: int | None = None
    turns: int | None = None
    first_audio_p95_s: float | None = None


# Told as `seats`, the word the gateways of the previous release read and say: while a release
# rolls out, or back, the gateways of both hear each other's workers and one roster stands.
class RosterShare(BaseModel):
    """One gateway's share of the roster: the workers that beat on it lately, and the cordons it set."""

    model_config = ConfigDict(frozen=True, serialize_by_alias=True)

    workers: tuple[WorkerStatus, ...] = Field(
        default=(), validation_alias=AliasChoices("workers", "seats"), serialization_alias="seats"
    )
    cordons: tuple[Assignment, ...] = ()
