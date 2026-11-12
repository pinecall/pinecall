"""The reads table: who read what of an org's data, a row per reader, subject and kind an hour."""

from collections.abc import Sequence
from datetime import timedelta

from sqlalchemy import exists, func, insert, literal, select

from runtime.accounts.models import Org
from runtime.compliance.models import Read
from runtime.enums import Env, ReadKind
from runtime.kit.repository import Repository

# The same reader reading the same thing again within the hour is the same read.
A_READ_LASTS = timedelta(hours=1)
A_PAGE = 200


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

    async def list_of_env(
        self, org: str, env: Env, *, subject: str | None = None, limit: int = A_PAGE
    ) -> Sequence[Read]:
        """The org's reads in the env, newest first, of one subject when named."""
        statement = self.statement().where(Read.org == org, Read.env == env)
        if subject is not None:
            statement = statement.where(Read.subject == subject)
        return await self.all(statement.order_by(Read.at.desc(), Read.id.desc()).limit(limit))
