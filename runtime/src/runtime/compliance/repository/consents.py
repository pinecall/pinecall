"""The contact_consents table: facts about a number, never changed, the newest standing."""

from collections.abc import Sequence

from sqlalchemy import exists, select
from sqlalchemy.dialects.postgresql import distinct_on
from sqlalchemy.orm import aliased

from runtime.compliance.models import ContactConsent
from runtime.enums import ConsentKind, Env
from runtime.kit.repository import Repository


class ConsentRepository(Repository[ContactConsent]):
    """Facts about a number, never changed: the newest stands."""

    model = ContactConsent

    async def list_of_number(self, org: str, env: Env, number: str) -> Sequence[ContactConsent]:
        """Every fact about the number, newest first."""
        statement = self.statement().where(
            ContactConsent.org == org, ContactConsent.env == env, ContactConsent.number == number
        )
        return await self.all(statement.order_by(ContactConsent.given_at.desc(), ContactConsent.id.desc()))

    async def find_newest(self, org: str, env: Env, number: str) -> ContactConsent | None:
        """The newest fact about the number."""
        statement = self.statement().where(
            ContactConsent.org == org, ContactConsent.env == env, ContactConsent.number == number
        )
        return await self.one_or_none(
            statement.order_by(ContactConsent.given_at.desc(), ContactConsent.id.desc()).limit(1)
        )

    # The numbers whose newest row is an opt-out, newest row first, after the row id a page ended on.
    async def list_opted_out(self, org: str, env: Env, *, after: int | None, limit: int) -> Sequence[ContactConsent]:
        """A page of the do-not-call list: each number's standing row, the newest first."""
        newest = (
            self.statement()
            .where(ContactConsent.org == org, ContactConsent.env == env)
            .ext(distinct_on(ContactConsent.number))
            .order_by(ContactConsent.number, ContactConsent.given_at.desc(), ContactConsent.id.desc())
            .subquery("newest")
        )
        standing = aliased(ContactConsent, newest)
        statement = select(standing).where(standing.kind == ConsentKind.opt_out)
        if after is not None:
            statement = statement.where(standing.id < after)
        return await self.all(statement.order_by(standing.id.desc()).limit(limit))

    async def has_opt_out_on(self, call: str) -> bool:
        """Whether a number went on the do-not-call list on this call."""
        statement = select(exists().where(ContactConsent.call == call, ContactConsent.kind == ConsentKind.opt_out))
        return bool((await self.session.execute(statement)).scalar_one())
