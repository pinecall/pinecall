"""What the env's runner and the gateway tell each other: the beat, what is to run, a process's environment."""

from typing import Literal

from pydantic import ConfigDict, Field

from runtime.enums import Env
from runtime.wire.base import WireModel

# A runner is deployed apart from its gateway, and must outlive a gateway newer than itself: what
# the gateway answers it is read leniently, and every field added to it carries a default.
READ_BY_AN_OLDER_RUNNER = ConfigDict(extra="ignore", validate_by_name=True, validate_by_alias=True)


class RunnerReport(WireModel):
    """What the runner says of one app: the host it answers for went live, or failed and why."""

    org: str
    name: str
    host: str
    state: Literal["live", "failed"]
    why: str = Field(default="", max_length=2000)


class AppLogs(WireModel):
    """The last lines of one app's process, as the runner read them from its container."""

    org: str
    name: str
    host: str
    lines: str = Field(max_length=256 * 1024)


class RunnerHeartbeatRequest(WireModel):
    """POST /v1/runner/heartbeat: the runner's name, and what changed since its last."""

    runner: str
    reports: list[RunnerReport] = Field(default_factory=list[RunnerReport])
    logs: list[AppLogs] = Field(default_factory=list[AppLogs])


class WantedApp(WireModel):
    """One app the runner is to have running: a release, under the host name its process takes."""

    model_config = READ_BY_AN_OLDER_RUNNER

    org: str
    name: str
    release: int
    sha256: str
    host: str
    # Whether an app socket of the org says it runs on that host: the release is serving.
    registered: bool
    # Whether this host was already reported failed: the runner leaves it alone.
    failed: bool
    # Whether a person asked for its logs lately: the runner sends them with its next beat.
    logs_wanted: bool = False
    # The host that last went live: it serves until the one wanted registers, and is the one
    # started again when its process exits.
    live_host: str | None = None


class RunnerHeartbeatResponse(WireModel):
    """The answer to a heartbeat: the runner's env, and every app of it that has a release."""

    model_config = READ_BY_AN_OLDER_RUNNER

    env: Env = Field(validation_alias="world", serialization_alias="world")
    apps: list[WantedApp]


class AppEnvironment(WireModel):
    """GET /v1/runner/apps/{org}/{name}/environment: what the app's process is started with."""

    model_config = READ_BY_AN_OLDER_RUNNER

    environment: dict[str, str]
