"""What a feed says of a change no log holds: a run, a release, a worker, a tool, a judge; ids alone."""

from pinecall.wire.frames import WireModel


class ReleaseChanged(WireModel):
    """A hosted app's release changed where it stands: uploaded, live, failed or replaced."""

    app: str
    release: int


class RunChanged(WireModel):
    """A run of goldens and cases opened a call, judged one, or finished."""

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
    """A tool of a call failed or timed out; its name and seconds, never what it said."""

    call: str
    agent: str
    name: str
    duration_s: float | None


class JudgeBroke(WireModel):
    """A judge found a sealed call broken; its name, never its reason or its evidence."""

    call: str
    agent: str
    judge: str
