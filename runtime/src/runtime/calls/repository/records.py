"""A number's phone calls for a carrier's traceback: the kept ones by their facts, the erased ones by their records."""

from collections.abc import Sequence
from dataclasses import dataclass

from sqlalchemy import delete, func, select, text
from sqlalchemy.dialects.postgresql import insert as upsert

from runtime.calls.models import CallFact, CallLogHead, CallRecord
from runtime.enums import Channel
from runtime.kit.repository import Repository

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

RECORDED = (
    "call",
    "org",
    "env",
    "direction",
    "from_number",
    "to_number",
    "started_at",
    "ended_at",
    "end_reason",
)


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


class RecordRepository(Repository[CallRecord]):
    """What the box keeps of a phone call past its log, and what a traceback reads of a number."""

    model = CallRecord

    # A phone call's numbers, times and end stay: they name numbers and moments, never what was said.
    async def record_phone_calls(self, calls: Sequence[str]) -> None:
        """Write each phone call's record off its facts, before the facts go; a call recorded stays as it is."""
        recorded = (
            select(
                CallFact.call,
                CallLogHead.org,
                CallLogHead.env,
                CallFact.direction,
                CallFact.from_number,
                CallFact.to_number,
                CallLogHead.started_at,
                CallFact.ended_at,
                CallFact.end_reason,
            )
            .join(CallLogHead, CallLogHead.call == CallFact.call)
            .where(CallFact.call.in_(calls), CallFact.channel == Channel.phone)
        )
        statement = (
            upsert(CallRecord).from_select(list(RECORDED), recorded).on_conflict_do_nothing(index_elements=["call"])
        )
        await self.session.execute(statement)

    # A record of a call that never started goes by when it ended, or when it was erased.
    async def delete_before(self, before: float) -> int:
        """Delete the records of erased calls older than the moment; how many."""
        went = func.coalesce(CallRecord.started_at, CallRecord.ended_at, func.extract("epoch", CallRecord.erased_at))
        return await self.change(delete(CallRecord).where(went < before))

    async def list_with_number(self, number: str, *, since: float) -> list[PhoneCall]:
        """Every phone call with the number since then, oldest first, erased ones included."""
        rows = await self.session.execute(WITH_NUMBER, {"number": number, "since": since})
        return [
            PhoneCall(
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
            for row in rows
        ]
