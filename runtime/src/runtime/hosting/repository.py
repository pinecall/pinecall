"""The hosted apps, their releases, the time they served, and the org's secrets."""

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import UTC, date, datetime

from sqlalchemy import delete, func, insert, select, text, update
from sqlalchemy.dialects.postgresql import insert as upsert
from sqlalchemy.orm import defer

from runtime.enums import AppKind, Env
from runtime.hosting.models import HostedApp, HostedRelease, HostedUsage, OrgSecret
from runtime.kit.repository import Repository


@dataclass(frozen=True, slots=True)
class StandingRow:
    """A hosted app as one statement reads it: its row, its newest release, and a stamp of the org's secrets."""

    org: str
    name: str
    kind: AppKind
    created_by: str
    created_at: datetime
    live_release: int | None
    live_host: str | None
    failed_host: str | None
    failed_why: str
    stopped: bool
    # None before the first release, and its sha256 with it.
    release: int | None
    sha256: str | None
    logs_wanted: bool
    # `name@epoch,…` of the org's secrets: the host name is made of it, so a changed secret is a new host.
    secrets: str


# One row per app: what the runner last said of it, its newest release, whether its logs were asked
# for lately, and a stamp of the org's secrets in that env.
STANDING = text("""
SELECT app.org, app.name, app.kind, app.created_by, app.created_at, app.live_release, app.live_host,
       app.failed_host, app.failed_why, app.stopped_at IS NOT NULL AS stopped,
       newest.release, newest.sha256,
       app.logs_asked_at > now() - make_interval(secs => :logs_for_s) AS logs_wanted,
       (SELECT coalesce(string_agg(name || '@' || extract(epoch FROM set_at), ',' ORDER BY name), '')
        FROM org_secrets WHERE org = app.org AND env = app.env) AS secrets
FROM hosted_apps app
LEFT JOIN LATERAL (
    SELECT release, sha256 FROM hosted_releases
    WHERE org = app.org AND env = app.env AND name = app.name ORDER BY release DESC LIMIT 1
) newest ON true
WHERE app.env = :env AND (CAST(:org AS text) IS NULL OR app.org = :org)
ORDER BY app.org, app.name
""")

# One statement for an env's count. Every app that was being counted, or serves now, is locked and
# read once: the time since its last count goes on today's row, capped, and it is counted from now
# if it serves and from nothing if it does not. Two gateways counting at once wait on the lock and
# read the other's count, so no span is counted twice.
COUNT = text("""
WITH serving AS (
    SELECT * FROM unnest(CAST(:orgs AS text[]), CAST(:names AS text[])) AS app (org, name)
), previous AS (
    SELECT app.org, app.name, app.metered_at,
           EXISTS (SELECT 1 FROM serving WHERE org = app.org AND name = app.name) AS serves
    FROM hosted_apps app
    WHERE app.env = :env AND (app.metered_at IS NOT NULL OR EXISTS (
        SELECT 1 FROM serving WHERE org = app.org AND name = app.name))
    FOR UPDATE OF app
), counted AS (
    INSERT INTO hosted_usage (org, env, name, day, seconds)
    SELECT org, :env, name, :day,
           least(greatest(extract(epoch FROM CAST(:now AS timestamptz) - metered_at), 0), :longest)
    FROM previous WHERE serves AND metered_at IS NOT NULL
    ON CONFLICT (org, env, name, day)
    DO UPDATE SET seconds = hosted_usage.seconds + excluded.seconds
)
UPDATE hosted_apps app
SET metered_at = CASE WHEN previous.serves THEN CAST(:now AS timestamptz) END
FROM previous
WHERE app.env = :env AND app.org = previous.org AND app.name = previous.name
""")

# One statement, so a report read and written is one fact: the host is recorded as failed, the
# release it served is no longer live when it was the one serving, and the host that had failed
# before comes back, which says whether this failure is news.
FAIL = text("""
UPDATE hosted_apps app
SET failed_host = :host, failed_why = :why, reported_by = :runner, reported_at = now(),
    live_release = CASE WHEN app.live_host = :host THEN NULL ELSE app.live_release END,
    live_host = CASE WHEN app.live_host = :host THEN NULL ELSE app.live_host END
FROM (
    SELECT failed_host FROM hosted_apps WHERE org = :org AND env = :env AND name = :name FOR UPDATE
) previous
WHERE app.org = :org AND app.env = :env AND app.name = :name
RETURNING previous.failed_host
""")


class HostedAppRepository(Repository[HostedApp]):
    """One row per org, env and name; what the runner last said of it is on the row."""

    model = HostedApp

    async def find(self, org: str, env: Env, name: str) -> HostedApp | None:
        """The app, or None when the box does not host it."""
        statement = self.statement().where(HostedApp.org == org, HostedApp.env == env, HostedApp.name == name)
        return await self.one_or_none(statement)

    # The lock is what makes two uploads at once two releases, never one number twice.
    async def lock(self, org: str, env: Env, name: str) -> HostedApp | None:
        """The app's row, locked for the rest of the transaction."""
        statement = (
            self.statement().where(HostedApp.org == org, HostedApp.env == env, HostedApp.name == name).with_for_update()
        )
        return await self.one_or_none(statement)

    # Two uploads of a new app at once: the second insert writes nothing.
    async def open(
        self, org: str, env: Env, name: str, *, kind: AppKind, key_fingerprint: str, sealed_key: str, created_by: str
    ) -> bool:
        """Start hosting the app; False when another request opened it first."""
        statement = (
            upsert(HostedApp)
            .values(
                org=org,
                env=env,
                name=name,
                kind=kind,
                key_fingerprint=key_fingerprint,
                sealed_key=sealed_key,
                created_by=created_by,
            )
            .on_conflict_do_nothing(index_elements=["org", "env", "name"])
            .returning(HostedApp.name)
        )
        return (await self.session.execute(statement)).scalar_one_or_none() is not None

    async def list_standing(self, env: Env, org: str | None, *, logs_for_s: float) -> list[StandingRow]:
        """Every app of the env, one org's or every one, with its newest release beside it."""
        rows = await self.session.execute(STANDING, {"env": env.value, "org": org, "logs_for_s": logs_for_s})
        return [
            StandingRow(
                org=row.org,
                name=row.name,
                kind=AppKind(row.kind),
                created_by=row.created_by,
                created_at=row.created_at,
                live_release=row.live_release,
                live_host=row.live_host,
                failed_host=row.failed_host,
                failed_why=row.failed_why,
                stopped=bool(row.stopped),
                release=row.release,
                sha256=row.sha256,
                logs_wanted=bool(row.logs_wanted),
                secrets=str(row.secrets),
            )
            for row in rows
        ]

    async def mark_live(self, org: str, env: Env, name: str, *, release: int | None, host: str, runner: str) -> None:
        """Record that the host serves the app now, and with it the release it runs."""
        statement = (
            update(HostedApp)
            .where(HostedApp.org == org, HostedApp.env == env, HostedApp.name == name)
            .values(live_release=release, live_host=host, reported_by=runner, reported_at=func.now())
        )
        await self.change(statement)

    async def mark_failed(self, org: str, env: Env, name: str, *, host: str, why: str, runner: str) -> bool:
        """Record that the host did not build, start or stay up; True the first time this host is said to."""
        params = {"org": org, "env": env.value, "name": name, "host": host, "why": why, "runner": runner}
        previous = (await self.session.execute(FAIL, params)).first()
        return previous is not None and previous.failed_host != host

    async def stop(self, org: str, env: Env, name: str, *, by: str) -> bool:
        """Stop running the app; whether the box hosts it."""
        statement = (
            update(HostedApp)
            .where(HostedApp.org == org, HostedApp.env == env, HostedApp.name == name)
            .values(stopped_at=func.now(), stopped_by=by)
        )
        return await self.change(statement) > 0

    async def start(self, org: str, env: Env, name: str) -> bool:
        """Run a stopped app again, the host it failed on forgotten; whether the box hosts it."""
        statement = (
            update(HostedApp)
            .where(HostedApp.org == org, HostedApp.env == env, HostedApp.name == name)
            .values(stopped_at=None, stopped_by="", failed_host=None, failed_why="")
        )
        return await self.change(statement) > 0

    async def ask_for_logs(self, org: str, env: Env, name: str) -> HostedApp | None:
        """Tell the runner to send the app's logs; the row with what it sent last, or None."""
        statement = (
            update(HostedApp)
            .where(HostedApp.org == org, HostedApp.env == env, HostedApp.name == name)
            .values(logs_asked_at=func.now())
            .returning(HostedApp)
        )
        return (await self.session.execute(statement)).scalar_one_or_none()

    async def keep_logs(self, org: str, env: Env, name: str, *, host: str, lines: str) -> None:
        """Keep what the runner read of the app's output."""
        statement = (
            update(HostedApp)
            .where(HostedApp.org == org, HostedApp.env == env, HostedApp.name == name)
            .values(logs=lines, logs_host=host, logs_at=func.now())
        )
        await self.change(statement)

    async def count_serving(
        self, env: Env, serving: Sequence[tuple[str, str]], now: datetime, *, longest_s: float
    ) -> None:
        """Count the time the env's serving apps, each an (org, name), served since the last count."""
        params = {
            "env": env.value,
            "orgs": [org for org, _ in serving],
            "names": [name for _, name in serving],
            "now": now,
            "day": now.astimezone(UTC).date(),
            "longest": longest_s,
        }
        await self.session.execute(COUNT, params)


class ReleaseRepository(Repository[HostedRelease]):
    """An app's uploads, numbered from 1, never edited."""

    model = HostedRelease

    async def keep(
        self,
        org: str,
        env: Env,
        name: str,
        *,
        source: bytes,
        sha256: str,
        author: str,
        note: str,
        page_dir: str | None,
        page_agent: str | None,
    ) -> HostedRelease:
        """Keep the upload as the next release; the app's row is locked by the caller."""
        same_app = (HostedRelease.org == org) & (HostedRelease.env == env) & (HostedRelease.name == name)
        next_number = select(func.coalesce(func.max(HostedRelease.release), 0) + 1).where(same_app).scalar_subquery()
        statement = (
            insert(HostedRelease)
            .values(
                org=org,
                env=env,
                name=name,
                release=next_number,
                source=source,
                sha256=sha256,
                bytes=len(source),
                author=author,
                note=note,
                page_dir=page_dir,
                page_agent=page_agent,
            )
            .returning(HostedRelease)
        )
        return (await self.session.execute(statement)).scalar_one()

    async def prune(self, org: str, env: Env, name: str, *, below: int, live: int | None) -> None:
        """Let the releases numbered `below` or less go, but the one serving now."""
        statement = delete(HostedRelease).where(
            HostedRelease.org == org,
            HostedRelease.env == env,
            HostedRelease.name == name,
            HostedRelease.release <= below,
            HostedRelease.release.is_distinct_from(live),
        )
        await self.change(statement)

    async def list_of_app(self, org: str, env: Env, name: str) -> Sequence[HostedRelease]:
        """The app's releases, newest first, their sources left on disk."""
        statement = (
            self.statement()
            .options(defer(HostedRelease.source))
            .where(HostedRelease.org == org, HostedRelease.env == env, HostedRelease.name == name)
            .order_by(HostedRelease.release.desc())
        )
        return await self.all(statement)

    async def find_serving_page(self, org: str, env: Env, name: str, live: int | None) -> HostedRelease | None:
        """The release whose page is served, its sources left on disk: the one that runs, else the newest."""
        statement = (
            self.statement()
            .options(defer(HostedRelease.source))
            .where(HostedRelease.org == org, HostedRelease.env == env, HostedRelease.name == name)
            .order_by((HostedRelease.release == live).desc(), HostedRelease.release.desc())
            .limit(1)
        )
        return await self.one_or_none(statement)

    async def find(self, org: str, env: Env, name: str, release: int) -> HostedRelease | None:
        """One release, its sources with it."""
        statement = self.statement().where(
            HostedRelease.org == org,
            HostedRelease.env == env,
            HostedRelease.name == name,
            HostedRelease.release == release,
        )
        return await self.one_or_none(statement)


class UsageRepository(Repository[HostedUsage]):
    """The seconds an app served each UTC day: what the org is billed for, so it outlives the app."""

    model = HostedUsage

    async def list_between(
        self, since: date, until: date, *, org: str | None, env: Env | None
    ) -> Sequence[HostedUsage]:
        """The time apps served per UTC day in [since, until), one org's or every org's."""
        statement = self.statement().where(HostedUsage.day >= since, HostedUsage.day < until)
        if org is not None:
            statement = statement.where(HostedUsage.org == org)
        if env is not None:
            statement = statement.where(HostedUsage.env == env)
        return await self.all(statement.order_by(HostedUsage.org, HostedUsage.env, HostedUsage.day, HostedUsage.name))


class SecretRepository(Repository[OrgSecret]):
    """An org's secrets in an env: the values its hosted apps are started with, kept sealed."""

    model = OrgSecret

    async def list_of_env(self, org: str, env: Env) -> Sequence[OrgSecret]:
        """The org's secrets in the env, by name."""
        statement = self.statement().where(OrgSecret.org == org, OrgSecret.env == env).order_by(OrgSecret.name)
        return await self.all(statement)

    async def put(self, org: str, env: Env, name: str, *, sealed: str, set_by: str) -> None:
        """Keep the secret, sealed, replacing the value it had."""
        statement = upsert(OrgSecret).values(org=org, env=env, name=name, sealed=sealed, set_by=set_by)
        replaced = {"sealed": statement.excluded.sealed, "set_by": statement.excluded.set_by, "set_at": func.now()}
        await self.session.execute(
            statement.on_conflict_do_update(index_elements=["org", "env", "name"], set_=replaced)
        )

    async def delete_named(self, org: str, env: Env, name: str) -> bool:
        """Forget one secret; whether it was set."""
        statement = delete(OrgSecret).where(OrgSecret.org == org, OrgSecret.env == env, OrgSecret.name == name)
        return await self.change(statement) > 0
