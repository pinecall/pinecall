"""An org's calls for its export: each one a line with its facts and its whole log, a page at a time."""

from dataclasses import dataclass

from sqlalchemy import text

from runtime.calls.models import CallLogHead
from runtime.enums import Env
from runtime.kit.repository import Repository

# One page of calls at a time, each with its whole log, so an org of any size streams in bounded
# memory. Written by Postgres, so every value comes out as it is stored.
CALLS = text("""
SELECT jsonb_build_object(
    'kind', 'call', 'call', head.call, 'agent', head.agent, 'holder', head.holder,
    'started_at', head.started_at, 'sealed', head.sealed,
    'facts', to_jsonb(facts) - 'call',
    'entries', (
        SELECT coalesce(jsonb_agg(jsonb_build_object(
            'seq', entry.seq, 'ts', entry.ts, 'type', entry.type, 'data', entry.data
        ) ORDER BY entry.seq), '[]'::jsonb)
        FROM call_log entry WHERE entry.log = head.log
    )
)::text AS line, coalesce(head.started_at, 0) AS at, head.call
FROM call_log_head head
LEFT JOIN call_facts facts ON facts.call = head.call
WHERE head.org = :org AND head.env = :env AND head.call IS NOT NULL
  AND (coalesce(head.started_at, 0), head.call) > (:at, :call)
ORDER BY coalesce(head.started_at, 0), head.call
LIMIT :page
""")


@dataclass(frozen=True, slots=True)
class CallLine:
    """One call as a line, and the cursor it moves the page to."""

    line: str
    at: float
    call: str


class CallExportRepository(Repository[CallLogHead]):
    """The org's calls in an env, each already a JSON line."""

    model = CallLogHead

    async def list_after(self, org: str, env: Env, at: float, call: str, *, page: int) -> list[CallLine]:
        """One page of calls after the cursor: the line, and the cursor each moves to."""
        params = {"org": org, "env": env.value, "at": at, "call": call, "page": page}
        rows = await self.session.execute(CALLS, params)
        return [CallLine(str(line), float(moved), str(moved_call)) for line, moved, moved_call in rows]
