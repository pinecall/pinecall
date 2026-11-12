"""What the processes of a box tell each other outside the log: entries, sockets, jobs."""

from typing import Any

from pydantic import AliasChoices, BaseModel, ConfigDict, Field, RootModel

from runtime.enums import Env
from runtime.wire.base import Command, Entry


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


class Commanded(BaseModel):
    """One command of a call as the gateways tell it to each other: the id it was sent under, and the command."""

    id: str
    command: Command


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


# ── the live side: who holds what, on which gateway ──

# Every shape below is read and said by the gateways of the release before 2026-11 too, for the hour a
# rollout takes and after a rollback: its names, types and what may be left out are that release's own
# (`calls/service/peers.py`, `agents/service/registry.py` there), and change by addition alone.


class Scoped(BaseModel):
    """A scope as the gateways tell it: an org, one of its envs, and the holder ("" for the org itself)."""

    model_config = ConfigDict(frozen=True)

    org: str
    env: Env = Env.production
    holder: str = ""


class SocketRow(BaseModel):
    """An app socket a gateway holds, as the org's list of apps shows it."""

    model_config = ConfigDict(frozen=True)

    app: str
    scope: Scoped
    address: str | None
    connected_at: float
    host: str | None = None


class SocketsShare(RootModel[tuple[SocketRow, ...]]):
    """One gateway's share of the sockets: every app socket open on it."""


class RunningShare(RootModel[dict[str, list[str]]]):
    """One gateway's share of the calls at once: the calls it opened, by `<org>|<env>`."""


class SimulatingShare(RootModel[dict[str, int]]):
    """One gateway's share of the simulated calls on the line: how many it plays, by `<org>|<env>`."""


class OwnedShare(BaseModel):
    """One gateway's share of what runs on it: the written calls whose sessions it runs, the threads it holds."""

    model_config = ConfigDict(frozen=True)

    texts: tuple[str, ...] = ()
    threads: tuple[str, ...] = ()


# `config` is the agent's declaration whole, as the release before 2026-11 says it and requires it of
# every registration it hears: it builds a call on the declaration of a socket another gateway holds.
# This release reads the declaration from its row and says it here for that one; it goes when that
# release does (agents-5).
class Registered(BaseModel):
    """One agent as one app socket holds it, as its gateway tells the others."""

    model_config = ConfigDict(frozen=True)

    slug: str
    scope: Scoped
    owner: str
    config: dict[str, Any]
    sdk: str | None = None
    takes_unclaimed: bool = True
    answers_dev: bool = False
    says_done: bool = False
    claimed: float = 0.0
    draining: bool = False


class HeldShare(BaseModel):
    """One gateway's share of the agents held: its sockets' agents, and the lines and phones it set."""

    model_config = ConfigDict(frozen=True)

    registrations: tuple[Registered, ...] = ()
    lines: tuple[Assignment, ...] = ()
    phones: tuple[Assignment, ...] = ()


class Taking(BaseModel):
    """A socket took an agent in a scope: the calls parked for it, on any gateway, are its to take."""

    app: str
    scope: Scoped
    agent: str


class Unbound(BaseModel):
    """A socket let a call go on the gateway that held it: the gateway that opened the call hands it on."""

    call: str
    app: str


class Handoff(BaseModel):
    """One message of the handoff channel: a socket that took an agent, or a call a socket let go."""

    taking: Taking | None = None
    unbound: Unbound | None = None


class HandedMessage(BaseModel):
    """A WhatsApp message one gateway hands to the one holding its contact's thread."""

    number: str
    phone_number_id: str
    wa_id: str
    name: str | None
    message_id: str
    kind: str
    text: str | None
