"""The Studio agents among the apps hosting keeps, each with its newest definition: an org's, or an env's running."""

from dataclasses import dataclass
from datetime import datetime

from sqlalchemy import text

from runtime.enums import AppKind, Env
from runtime.hosting.models import HostedApp
from runtime.kit.repository import Repository


@dataclass(frozen=True, slots=True)
class Kept:
    """A Studio agent as its newest release keeps it: whose, its definition's bytes, who saved it and when."""

    org: str
    name: str
    release: int
    definition: bytes
    author: str
    note: str
    saved_at: datetime
    stopped: bool


# One statement where hosting was asked three times an agent: the app, its newest release and the release's
# bytes. An agent with no release yet has no definition, and is no row.
NEWEST = text("""
SELECT app.org, app.name, app.stopped_at IS NOT NULL AS stopped,
       newest.release, newest.source, newest.author, newest.note, newest.created_at
FROM hosted_apps app
JOIN LATERAL (
    SELECT release, source, author, note, created_at FROM hosted_releases
    WHERE org = app.org AND env = app.env AND name = app.name ORDER BY release DESC LIMIT 1
) newest ON true
WHERE app.env = :env AND app.kind = :kind
  AND (CAST(:org AS text) IS NULL OR app.org = :org)
  AND (CAST(:name AS text) IS NULL OR app.name = :name)
  AND (NOT :running OR app.stopped_at IS NULL)
ORDER BY app.org, app.name
""")


# A domain reads the tables of one below it as it reads its own: a Studio agent is a hosted app of the
# kind `studio`, its definition the source of a release. What is hosting's (the app, its releases, its
# standing) stays hosting's to write.
class StudioAgentRepository(Repository[HostedApp]):
    """The hosted apps that are Studio agents, each with its newest definition."""

    model = HostedApp

    async def list_newest(
        self, env: Env, *, org: str | None = None, name: str | None = None, running: bool = False
    ) -> list[Kept]:
        """The env's Studio agents with a release, one org's or every org's, one or all; `running`, none stopped."""
        params = {"env": env.value, "kind": AppKind.studio.value, "org": org, "name": name, "running": running}
        rows = await self.session.execute(NEWEST, params)
        return [
            Kept(
                org=row.org,
                name=row.name,
                release=int(row.release),
                definition=bytes(row.source),
                author=row.author,
                note=row.note,
                saved_at=row.created_at,
                stopped=bool(row.stopped),
            )
            for row in rows
        ]
