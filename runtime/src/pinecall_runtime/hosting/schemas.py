"""The bodies of the hosting endpoints: hosted apps, releases, secrets, and the runner's report."""

from datetime import datetime
from typing import Literal

from pydantic import ConfigDict, Field, field_serializer

from pinecall_runtime.enums import Env
from pinecall_runtime.kit.schemas import Row, Schema
from pinecall_runtime.wire.base import WireModel

# A runner is deployed apart from its gateway, and must outlive a gateway newer than itself: what
# the gateway answers it is read leniently, and every field added to it carries a default.
READ_BY_AN_OLDER_RUNNER = ConfigDict(extra="ignore", validate_by_name=True, validate_by_alias=True)


def _as_epoch(at: datetime | None) -> float | None:
    return None if at is None else at.timestamp()


class HostedAppRow(Row):
    """One app the box hosts for the org: its newest release, and how the runner left it."""

    name: str
    # The newest release, null before the first.
    release: int | None
    # The release serving the app now, null while none is.
    live_release: int | None
    # Why the newest release did not build or start, null when it did or is still on its way.
    failed_why: str | None
    # A person stopped it: nothing runs, and its releases and token stay.
    stopped: bool
    # `code`, sources the runner starts; `studio`, an agent built in the console the gateway holds.
    kind: str = "code"
    created_by: str
    created_at: datetime

    @field_serializer("created_at")
    def _created(self, at: datetime) -> float:
        return at.timestamp()


class HostedAppList(Row):
    """GET /v1/hosted: the apps the box hosts for the org in the env, by name."""

    apps: list[HostedAppRow]


class ReleaseRow(Row):
    """One release of a hosted app: its number, its sources' sha256 and size, who sent it."""

    name: str
    release: int
    sha256: str
    bytes: int
    author: str
    note: str
    created_at: datetime
    # The folder of the app's page inside the sources, and the agent its visitors reach; null with no page.
    page_dir: str | None = None
    page_agent: str | None = None
    # Where the page is served, once the gateway serves pages; null otherwise.
    page_url: str | None = None

    @field_serializer("created_at")
    def _created(self, at: datetime) -> float:
        return at.timestamp()


class ReleaseList(Row):
    """GET /v1/hosted/{name}/releases: the app's releases, newest first."""

    releases: list[ReleaseRow]


class RollbackRequest(Schema):
    """POST /v1/hosted/{name}/rollback: which release's sources go again, as the next release."""

    release: int = Field(ge=1)


class AppLogsResponse(Row):
    """GET /v1/hosted/{name}/logs: the last lines the runner read, and which process, and when."""

    name: str
    host: str | None
    lines: str
    # Null before the runner has sent any: asking is what makes it send them.
    at: datetime | None

    @field_serializer("at")
    def _at(self, at: datetime | None) -> float | None:
        return _as_epoch(at)


class ServedRow(Row):
    """The time one app served on one UTC day."""

    org: str
    env: Env
    name: str
    day: str
    seconds: float


class ServedPage(Row):
    """GET /v1/hosted/usage and GET /v1/ops/hosted-usage: the time apps served, per day."""

    since: str
    until: str
    rows: list[ServedRow]


class PutSecretRequest(Schema):
    """PUT /v1/secrets/{name}, the body: the value, which no endpoint ever answers back."""

    value: str


class SecretRow(Row):
    """One of the org's secrets as the list shows it: never its value."""

    name: str
    set_by: str
    set_at: datetime

    @field_serializer("set_at")
    def _set(self, at: datetime) -> float:
        return at.timestamp()


class SecretList(Row):
    """GET /v1/secrets: the org's secrets in the env, by name."""

    secrets: list[SecretRow]


# ── the runner ──


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


class PageConfig(Schema):
    """GET /pinecall/config on an app's page: what the page needs before it asks for a ticket."""

    # The agent a visitor reaches.
    agent: str
    # The Turnstile site key the page solves before a ticket, or null where the box asks for none.
    turnstile: str | None


class PageTicketRequest(Schema):
    """POST /pinecall/token on an app's page: a seat in a new call with the page's agent."""

    scope: Literal["talk", "chat"] = "talk"
    # A `resume_token` the page kept: back into that conversation.
    resume: str | None = Field(None, max_length=4096)
    turnstile: str | None = None


class PageCodeRequest(Schema):
    """POST /pinecall/code on an app's page: a code a visitor keys when they call the agent's number."""

    turnstile: str | None = None
