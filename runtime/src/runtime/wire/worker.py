"""What a worker and the gateway tell each other over HTTP: a worker's heartbeat, and the answer to it."""

from runtime.wire.base import WireModel


class HeartbeatRequest(WireModel):
    """A worker's report: its fleet, its name, what it holds and how loaded it is."""

    fleet: str
    worker: str
    # The name the worker registered under with LiveKit: the one a dispatch reaches it by; null
    # until LiveKit registered it, so no call is offered to a worker nobody can give it to.
    agent_name: str | None = None
    active: int
    # Measured slots; null when the worker is gated on its machine's CPU.
    max_jobs: int | None
    load: float
    draining: bool
    # Its last minute, as its calls' jobs told it; absent from a worker of an older release.
    ended: int | None = None
    failed: int | None = None
    errors: int | None = None
    turns: int | None = None
    first_audio_p95_s: float | None = None


# Both shapes change by addition alone while the release before 2026-11 runs: its workers, draining
# calls for up to an hour, beat to these gateways, and after a rollback these workers beat to its
# gateways; each refuses a field it does not know and requires every one it does.
class HeartbeatResponse(WireModel):
    """The answer to a heartbeat: whether this worker is cordoned, and its fleet full."""

    cordoned: bool
    # No worker ever read it, and the workers of the release before 2026-11 require it: answered
    # until that release is gone, then removed with `slots.accepts_nobody`.
    full: bool
