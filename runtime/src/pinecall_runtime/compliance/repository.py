"""The org's policy row, the access log, each call's recording key and the telemetry row."""

from collections.abc import Sequence
from datetime import timedelta

from sqlalchemy import delete, exists, func, insert, literal, select
from sqlalchemy.dialects.postgresql import insert as upsert

from pinecall_runtime.accounts.models import Org
from pinecall_runtime.compliance.models import OrgPolicy, OrgTelemetry, Read, RecordingKey
from pinecall_runtime.enums import Env, ReadKind
from pinecall_runtime.kit.repository import Repository

# The same reader reading the same thing again within the hour is the same read.
A_READ_LASTS = timedelta(hours=1)
A_PAGE = 200


class PolicyRepository(Repository[OrgPolicy]):
    """One row per org; an org without one has the platform's defaults."""

    model = OrgPolicy

    async def get(self, org: str) -> OrgPolicy | None:
        """The org's policy row, or None when nobody set one."""
        return await self.one_or_none(self.statement().where(OrgPolicy.org == org))

    async def put(
        self,
        org: str,
        *,
        retention_days: int | None,
        calling_from: int | None,
        calling_until: int | None,
        per_number_day: int | None,
        consent_everywhere: bool,
        disclosure: str | None,
        recording_notice: bool,
        set_by: str,
    ) -> None:
        """Replace the org's policy whole."""
        values = {
            "org": org,
            "retention_days": retention_days,
            "calling_from": calling_from,
            "calling_until": calling_until,
            "per_number_day": per_number_day,
            "consent_everywhere": consent_everywhere,
            "disclosure": disclosure,
            "recording_notice": recording_notice,
            "set_by": set_by,
        }
        statement = upsert(OrgPolicy).values(**values)
        replaced = {name: statement.excluded[name] for name in values if name != "org"}
        await self.session.execute(
            statement.on_conflict_do_update(index_elements=["org"], set_={**replaced, "set_at": func.now()})
        )


class ReadRepository(Repository[Read]):
    """Who read what: a row per reader, subject and kind an hour."""

    model = Read

    # One statement: the read waits on its record and on nothing more. An org erased has no access
    # log left to write to, so the insert is guarded by the org's row.
    async def record(self, org: str, env: Env | None, subject: str, what: ReadKind, reader: str) -> None:
        """Write the read down, unless the same reader read the same thing within the hour."""
        same = select(Read.id).where(
            Read.org == org,
            Read.subject == subject,
            Read.what == what,
            Read.reader == reader,
            Read.env.is_not_distinct_from(env),
            Read.at > func.now() - A_READ_LASTS,
        )
        row = (
            select(
                literal(org).label("org"),
                literal(env).label("env"),
                literal(subject).label("subject"),
                literal(what).label("what"),
                literal(reader).label("reader"),
            )
            .where(exists(select(Org.id).where(Org.id == org)))
            .where(~exists(same))
        )
        statement = insert(Read).from_select(["org", "env", "subject", "what", "reader"], row)
        await self.session.execute(statement)

    async def of_org(self, org: str, *, subject: str | None = None, limit: int = A_PAGE) -> Sequence[Read]:
        """The org's reads, newest first, of one subject when named."""
        statement = self.statement().where(Read.org == org)
        if subject is not None:
            statement = statement.where(Read.subject == subject)
        return await self.all(statement.order_by(Read.at.desc(), Read.id.desc()).limit(limit))


class RecordingKeyRepository(Repository[RecordingKey]):
    """A recording's own key, sealed; erased with the call."""

    model = RecordingKey

    # The insert is the mint: of two asks at once, or a retry, the first key stands and is the
    # answer. Asked for another org's call, nothing: the update's WHERE fails and nothing returns.
    async def mint(self, call: str, org: str, sealed: str) -> str | None:
        """The call's sealed key, this one or the one minted before; None for another org's call."""
        statement = (
            upsert(RecordingKey)
            .values(call=call, org=org, sealed=sealed)
            .on_conflict_do_update(
                index_elements=["call"],
                set_={"call": RecordingKey.call},
                where=RecordingKey.org == org,
            )
            .returning(RecordingKey.sealed)
        )
        return (await self.session.execute(statement)).scalar_one_or_none()

    async def get(self, call: str) -> RecordingKey | None:
        """The call's key row, or None when it was never recorded sealed."""
        return await self.one_or_none(self.statement().where(RecordingKey.call == call))


class TelemetryRepository(Repository[OrgTelemetry]):
    """One row per org: where its calls' traces go."""

    model = OrgTelemetry

    async def get(self, org: str) -> OrgTelemetry | None:
        """The org's telemetry row, or None when its traces go nowhere."""
        return await self.one_or_none(self.statement().where(OrgTelemetry.org == org))

    async def put(self, org: str, *, endpoint: str, ciphertext: str | None, pii: bool) -> None:
        """Keep where the org's traces go, replacing what it had."""
        statement = upsert(OrgTelemetry).values(org=org, endpoint=endpoint, ciphertext=ciphertext, pii=pii)
        replaced = {
            "endpoint": statement.excluded.endpoint,
            "ciphertext": statement.excluded.ciphertext,
            "pii": statement.excluded.pii,
            "set_at": func.now(),
        }
        await self.session.execute(statement.on_conflict_do_update(index_elements=["org"], set_=replaced))

    async def drop(self, org: str) -> bool:
        """Forget where the org's traces went; whether they went anywhere."""
        return await self.changed(delete(OrgTelemetry).where(OrgTelemetry.org == org)) > 0
