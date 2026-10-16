"""A number's phone calls: the ones kept, by their facts, and the ones erased, by their records."""

from dataclasses import dataclass
from typing import Any

from sqlalchemy import Row, text
from sqlalchemy.ext.asyncio import AsyncSession

# A kept call's facts, then an erased call's record: the same columns, oldest first. A call that
# never started (a dial nobody answered) is placed by when it ended.
WITH_NUMBER = text("""
SELECT call, org, env, direction, from_number, to_number, started_at, ended_at, end_reason, erased
FROM (
    SELECT head.call, head.org, head.env, facts.direction, facts.from_number, facts.to_number,
           head.started_at, facts.ended_at, facts.end_reason, false AS erased
    FROM call_facts facts JOIN call_log_head head ON head.call = facts.call
    WHERE facts.channel = 'phone'
      AND (facts.from_number = :number OR facts.to_number = :number)
    UNION ALL
    SELECT call, org, env, direction, from_number, to_number, started_at, ended_at, end_reason, true
    FROM call_records WHERE from_number = :number OR to_number = :number
) found
WHERE coalesce(started_at, ended_at, 0) >= :since
ORDER BY coalesce(started_at, ended_at, 0)
""")


@dataclass(frozen=True, slots=True)
class PhoneCall:
    """One phone call with a number, kept or erased: whose, which way, when, how it ended."""

    call: str
    org: str | None
    env: str | None
    direction: str | None
    from_number: str | None
    to_number: str | None
    started_at: float | None
    ended_at: float | None
    end_reason: str | None
    erased: bool


class RecordRepository:
    """What a carrier's traceback asks of the box's phone calls."""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def phone_calls_with(self, number: str, *, since: float) -> list[PhoneCall]:
        """Every phone call with the number since then, oldest first, erased ones included."""
        rows = (await self.session.execute(WITH_NUMBER, {"number": number, "since": since})).all()
        return [_phone_call(row) for row in rows]


def _phone_call(row: Row[Any]) -> PhoneCall:
    return PhoneCall(
        call=str(row.call),
        org=row.org,
        env=row.env,
        direction=row.direction,
        from_number=row.from_number,
        to_number=row.to_number,
        started_at=None if row.started_at is None else float(row.started_at),
        ended_at=None if row.ended_at is None else float(row.ended_at),
        end_reason=row.end_reason,
        erased=bool(row.erased),
    )
