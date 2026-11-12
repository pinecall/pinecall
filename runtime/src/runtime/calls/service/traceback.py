"""A number's calls for a carrier's traceback: the calls kept, the calls erased, every dial, and who looked."""

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import UTC, datetime

from runtime.actor import Scope
from runtime.calls.repository.records import PhoneCall, RecordRepository
from runtime.calls.service.erasing import RECORDS_KEPT_S
from runtime.compliance import service as compliance
from runtime.compliance.models import Dial
from runtime.enums import Env, ReadKind
from runtime.kit.text import parse_e164
from runtime.kit.time import epoch
from runtime.postgres import BoxSession


@dataclass(frozen=True, slots=True)
class Traced:
    """What the box keeps of one number since a moment: every phone call with it and every dial to it."""

    number: str
    since: float
    calls: list[PhoneCall]
    dials: Sequence[Dial]


# Box-wide: a carrier asks about a number, whatever org it reached. The look is written into the
# access log of every org whose calls or dials it showed.
async def trace_number(session: BoxSession, number: str, since: float | None, *, read_by: str) -> Traced:
    """Every phone call with the number and every dial to it, since an epoch second or two years back."""
    kept = parse_e164(number)
    start = epoch() - RECORDS_KEPT_S if since is None else since
    found = await RecordRepository(session).list_with_number(kept, since=start)
    dials = await compliance.list_dials_to(session, kept, datetime.fromtimestamp(start, UTC))
    seen = {(call.org, call.env) for call in found if call.org is not None}
    seen |= {(dial.org, dial.env.value) for dial in dials}
    for org, env in sorted(seen, key=str):
        scope = Scope(org, Env(env) if env else Env.production)
        await compliance.record_read(session, scope, kept, ReadKind.traceback, by=read_by)
    return Traced(number=kept, since=start, calls=found, dials=dials)
