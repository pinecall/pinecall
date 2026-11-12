"""The dial_policy and dials tables: an org's dial guards, and the ledger of every dial asked for."""

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime
from typing import Any

from sqlalchemy import delete, exists, func, literal, select

from runtime.compliance.models import Dial, DialPolicy
from runtime.kit.repository import Repository
from runtime.kit.time import now


class DialPolicyRepository(Repository[DialPolicy]):
    """An org's dial guards, one row."""

    model = DialPolicy

    async def find(self, org: str) -> DialPolicy | None:
        """The org's row, or None when nobody set one."""
        return await self.one_or_none(self.statement().where(DialPolicy.org == org))

    async def put(self, org: str, values: dict[str, Any]) -> DialPolicy:
        """Replace the org's guards whole."""
        return await self.upsert({"org": org, **values, "set_at": now()}, key=["org"])


@dataclass(frozen=True, slots=True)
class DialCounts:
    """What an org dialled lately: every dial of the last minute and day, and the calls placed to one number."""

    minute: int
    day: int
    to_number_placed: int


# The statements alone: which guard refuses, in what order, and what the row then says is the service's
# (`dial_guards`). Until 2026-11 one method here took the lock, counted, chose the guard and wrote the row.
class DialRepository(Repository[Dial]):
    """The dial ledger: every outbound call asked for, placed or refused."""

    model = Dial

    # The key is the one the previous runtime locks on, so the two count in turn on one database.
    async def lock(self, org: str) -> None:
        """Hold the org's ledger for this transaction: two dials of one org cannot both take the last slot."""
        await self.session.execute(select(func.pg_advisory_xact_lock(func.hashtext(literal(f"dials:{org}")))))

    # A number's own count is of the calls placed to it, not the refusals: a refused dial rang nobody.
    async def count_since(self, org: str, dialled: str, *, minute: datetime, day: datetime) -> DialCounts:
        """The org's dials since the two moments, and how many of the day's were placed to the number."""
        counted = select(
            func.count().filter(Dial.at > minute),
            func.count(),
            func.count().filter(Dial.dialled == dialled, Dial.refused.is_(None)),
        ).where(Dial.org == org, Dial.at > day)
        in_minute, in_day, to_number = (await self.session.execute(counted)).one()
        return DialCounts(minute=int(in_minute), day=int(in_day), to_number_placed=int(to_number))

    async def is_placed(self, org: str, call: str, dialled: str) -> bool:
        """Whether this call's own first leg to the number was placed: its ledger row names the call."""
        statement = select(
            exists().where(Dial.org == org, Dial.call == call, Dial.dialled == dialled, Dial.refused.is_(None))
        )
        return bool((await self.session.execute(statement)).scalar_one())

    async def list_to_number_since(self, number: str, since: datetime) -> Sequence[Dial]:
        """Every dial to the number since then, placed or refused, oldest first. Read box-wide by the caller."""
        return await self.all(self.statement().where(Dial.dialled == number, Dial.at >= since).order_by(Dial.at))

    async def delete_before(self, moment: datetime) -> int:
        """Forget the dials placed or refused before the moment; how many. Run box-wide by the caller."""
        return await self.change(delete(Dial).where(Dial.at < moment))
