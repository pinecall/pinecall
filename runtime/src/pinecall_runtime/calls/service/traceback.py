"""A number's calls for a carrier's traceback: the calls kept, the calls erased, every dial, and who looked."""

from datetime import datetime, timedelta

from sqlalchemy.ext.asyncio import AsyncSession

from pinecall_runtime.calls.service import lists
from pinecall_runtime.compliance import service as compliance
from pinecall_runtime.enums import Env, ReadKind
from pinecall_runtime.kit.auth import Scope
from pinecall_runtime.kit.text import parse_e164
from pinecall_runtime.kit.time import now
from pinecall_runtime.postgres import box_wide
from pinecall_runtime.telephony import service as telephony

# How long a call's detail record is kept once its log is gone: the traceback reaches that far.
RECORDS_KEPT = timedelta(days=730)


# Box-wide: a carrier asks about a number, whatever org it reached. The lookup is written into
# the access log of every org whose calls or dials it showed.
async def traceback_of(session: AsyncSession, number: str, since: float | None, *, read_by: str) -> telephony.Traceback:
    """Every phone call with the number and every dial to it, since an epoch second or 24 months."""
    kept = parse_e164(number)
    start = (now() - RECORDS_KEPT).timestamp() if since is None else since
    with box_wide():
        found = await lists.phone_calls_with(session, kept, since=start)
        dials = await telephony.dials_to(session, kept, datetime.fromtimestamp(start, tz=now().tzinfo))
    traceback = telephony.Traceback(
        number=kept,
        since=start,
        calls=[
            telephony.TracebackCall(
                call=item.call,
                org=item.org,
                env=item.env,
                direction=item.direction,
                from_number=item.from_number,
                to_number=item.to_number,
                started_at=item.started_at,
                ended_at=item.ended_at,
                end_reason=item.end_reason,
                erased=item.erased,
            )
            for item in found
        ],
        dials=[
            telephony.TracebackDial(
                org=dial.org,
                env=dial.env.value,
                agent=dial.agent,
                call=dial.call,
                shown=dial.shown,
                asked_by=dial.asked_by,
                refused=dial.refused,
                at=dial.at.timestamp(),
            )
            for dial in dials
        ],
    )
    seen = {(call.org, call.env) for call in traceback.calls if call.org is not None}
    seen |= {(dial.org, dial.env) for dial in traceback.dials}
    for org, env in sorted(seen, key=str):
        await compliance.record_read(
            session, Scope(org, Env(env) if env else Env.production), kept, ReadKind.traceback, by=read_by
        )
    return traceback
