"""The orgs table: an org by its id or its slug."""

from collections.abc import Sequence
from datetime import datetime

from sqlalchemy import or_

from runtime.accounts.models import Org
from runtime.kit.repository import Repository


class OrgRepository(Repository[Org]):
    """Orgs by id or slug."""

    model = Org

    async def find(self, named: str) -> Org | None:
        """By id or slug, or None."""
        return await self.one_or_none(self.statement().where(or_(Org.id == named, Org.slug == named)).limit(1))

    async def list_all(self) -> Sequence[Org]:
        """Every org, oldest first."""
        return await self.all(self.statement().order_by(Org.created_at, Org.id))

    async def list_born_between(self, since: datetime, until: datetime) -> Sequence[Org]:
        """The orgs made in the window, oldest first."""
        statement = self.statement().where(Org.created_at >= since, Org.created_at < until)
        return await self.all(statement.order_by(Org.created_at, Org.id))
