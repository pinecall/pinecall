"""What a feed says of a change no log holds: a run, a release, a worker, a tool, a judge, by ids alone."""

from pinecall_runtime.wire.base import WireModel


class AppFailed(WireModel):
    """A hosted app did not build, start or stay up: the org's alert, posted to its webhook, on no agent's log."""

    app: str
    host: str
    release: int | None = None
    why: str


class ReleaseChanged(WireModel):
    """A hosted app's release changed where it stands."""

    app: str
    release: int


class RunChanged(WireModel):
    """A run of goldens opened a call, judged one, or finished."""

    run: str
    agent: str
    finished: bool


class WorkerChanged(WireModel):
    """A worker of a fleet was first heard, cordoned, uncordoned, or stopped being heard."""

    worker: str
    fleet: str
    up: bool
    cordoned: bool


class ToolRan(WireModel):
    """A tool of a call answered; its name and seconds, never its arguments or its output."""

    call: str
    agent: str
    name: str
    duration_s: float | None


class ToolFailed(WireModel):
    """A tool of a call failed or timed out; its name and seconds, never its error, arguments or output."""

    call: str
    agent: str
    name: str
    duration_s: float | None


class JudgeBroke(WireModel):
    """A judge found a sealed call broken; its name, never its reason or its evidence."""

    call: str
    agent: str
    judge: str
