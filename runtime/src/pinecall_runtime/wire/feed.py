"""What a feed says of a change no log holds: a run, a release, a worker, by their ids alone."""

from pinecall_runtime.wire.base import WireModel


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
