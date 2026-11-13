"""The bodies of the hosting endpoints: an org's apps, releases, logs, usage and secrets, and a page's own."""

from collections.abc import Sequence
from typing import Any, Literal, Self

from pydantic import Field

from runtime.enums import AppKind, Env
from runtime.kit.schemas import Epoch, Row, Schema


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
    kind: AppKind = AppKind.code
    created_by: str
    created_at: Epoch
    # The agents its own processes hold now, by name: a voice app's agents are its, not apps beside it.
    # Empty while nothing of it is connected, and for a Studio agent, which the gateway holds itself.
    agents: list[str] = []

    @classmethod
    def of_standing(cls, app: Any, agents: Sequence[str]) -> Self:
        """The body an app answers as, with the agents its processes hold."""
        return cls.of(app).model_copy(update={"agents": list(agents)})


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
    created_at: Epoch
    # The folder of the app's page inside the sources, and the agent its visitors reach; null with no page.
    page_dir: str | None = None
    page_agent: str | None = None
    # Where the page is served, on a gateway that serves pages; null with no page, or where none is served.
    page_url: str | None = None

    @classmethod
    def of_released(cls, released: Any) -> Self:
        """The body a release answers as, with where its page is served."""
        return cls.of(released.release).model_copy(update={"page_url": released.page_url})


class ReleaseList(Row):
    """GET /v1/hosted/{name}/releases: the app's releases, newest first."""

    releases: list[ReleaseRow]

    @classmethod
    def of_released(cls, released: Sequence[Any]) -> Self:
        """The body an app's releases answer as."""
        return cls(releases=[ReleaseRow.of_released(one) for one in released])


class RollbackRequest(Schema):
    """POST /v1/hosted/{name}/rollback: which release goes again, as the next release."""

    release: int = Field(ge=1)


class AppLogsResponse(Row):
    """GET /v1/hosted/{name}/logs: the last lines the runner read, and which process, and when."""

    name: str
    host: str | None
    lines: str
    # Null before the runner has sent any: asking is what makes it send them.
    at: Epoch | None


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

    @classmethod
    def of_usage(cls, usage: Any) -> Self:
        """The body a month's usage answers as: each day as its date, each time to a tenth of a second."""
        rows = [
            ServedRow(org=row.org, env=row.env, name=row.name, day=row.day.isoformat(), seconds=round(row.seconds, 1))
            for row in usage.rows
        ]
        return cls(since=usage.since.isoformat(), until=usage.until.isoformat(), rows=rows)


class PutSecretRequest(Schema):
    """PUT /v1/secrets/{name}, the body: the value, which no endpoint ever answers back."""

    value: str


class SecretRow(Row):
    """One of the org's secrets as the list shows it: never its value."""

    name: str
    set_by: str
    set_at: Epoch


class SecretList(Row):
    """GET /v1/secrets: the org's secrets in the env, by name."""

    secrets: list[SecretRow]


class PageConfig(Row):
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


class PageDictationRequest(Schema):
    """POST /pinecall/dictation on an app's page: one dictation into the page's field, in a language."""

    # The language the visitor dictates in, as the page's widget says it; the ears' own when unsaid.
    language: str | None = Field(None, max_length=16)
    turnstile: str | None = None


class PageDictation(Row):
    """What a page opens one dictation with: the socket, a minute long, and the words to write its own way."""

    url: str
    # A page of Pinecall's has no words of its own to expect: the app's are the agent's, on a call.
    hear: list[str] = []


class PageCodeRequest(Schema):
    """POST /pinecall/code on an app's page: a code a visitor keys when they call the agent's number."""

    turnstile: str | None = None
