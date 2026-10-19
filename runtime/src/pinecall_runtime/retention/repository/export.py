"""An org's env as JSON Lines, one line per row, written by Postgres so values come out as stored."""

from dataclasses import dataclass

from sqlalchemy import TextClause, text

from pinecall_runtime.calls.models import CallLogHead
from pinecall_runtime.enums import Env
from pinecall_runtime.kit.repository import Repository

# One page of calls at a time, each with its whole log, so an org of any size streams in bounded
# memory. Every read is unbounded: an org's list of anything has no size.
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

# The embedding is the box's to compute again; the words are the org's.
MEMORIES = text("""
SELECT jsonb_build_object(
    'kind', 'memory', 'contact', contact, 'holder', holder, 'text', text, 'category', category,
    'valid_from', valid_from, 'invalidated_at', invalidated_at, 'source_call', source_call
)::text AS line
FROM contact_memories WHERE org = :org AND env = :env
ORDER BY contact, valid_from
""")

SETTINGS = text("""
SELECT jsonb_build_object(
    'kind', 'agent_config', 'agent', agent, 'holder', holder, 'version', version,
    'config', config, 'author', author, 'note', note, 'set_at', set_at
)::text AS line
FROM agent_config WHERE org = :org AND env = :env
ORDER BY agent, holder, version
""")

# Every canary set and cleared, as the settings are: nothing is ever updated.
CANARIES = text("""
SELECT jsonb_build_object(
    'kind', 'canary', 'agent', agent, 'holder', holder, 'version', version, 'share', share,
    'author', author, 'note', note, 'set_at', set_at
)::text AS line
FROM agent_canaries WHERE org = :org AND env = :env
ORDER BY agent, holder, set_at, id
""")

LEXICON = text("""
SELECT jsonb_build_object(
    'kind', 'lexicon', 'agent', agent, 'holder', holder, 'version', version,
    'said', said, 'heard', heard, 'author', author, 'note', note, 'set_at', set_at
)::text AS line
FROM lexicon WHERE org = :org AND env = :env
ORDER BY agent, holder, version
""")

DOCUMENTS = text("""
SELECT jsonb_build_object(
    'kind', 'knowledge_file', 'base', base, 'holder', holder, 'path', path, 'text', text,
    'pushed_at', pushed_at
)::text AS line
FROM knowledge_files WHERE org = :org AND env = :env
ORDER BY base, path
""")

CONSENTS = text("""
SELECT jsonb_build_object(
    'kind', 'consent', 'number', number, 'consent', kind, 'source', source, 'text', text,
    'evidence', evidence, 'given_by', given_by, 'call', call, 'given_at', given_at
)::text AS line
FROM contact_consents WHERE org = :org AND env = :env
ORDER BY number, given_at, id
""")

# The dataset is the org's in both envs: every export carries it whole, with the env its call ran in.
CASES = text("""
SELECT jsonb_build_object(
    'kind', 'eval_case', 'id', id, 'agent', agent, 'name', name, 'golden', golden,
    'source_call', source_call, 'source_env', source_env, 'held_out', held_out,
    'author', author, 'created_at', created_at
)::text AS line
FROM eval_cases WHERE org = :org
ORDER BY agent, name
""")

# Each block of prompt the org's calls were told, once per text, the same in both envs.
PROMPTS = text("""
SELECT jsonb_build_object(
    'kind', 'prompt', 'hash', hash, 'text', text, 'first_used_at', first_used_at
)::text AS line
FROM prompts WHERE org = :org
ORDER BY first_used_at, hash
""")

# What the seal counted of each day, by agent and version: numbers and the judges' names.
STAGE_DAYS = text("""
SELECT jsonb_build_object(
    'kind', 'stage_day', 'holder', holder, 'agent', agent, 'day', day,
    'config_version', config_version, 'stage', stage, 'vendor', vendor, 'model', model,
    'turns', turns, 'buckets', buckets, 'confidence_sum', confidence_sum,
    'confidence_turns', confidence_turns
)::text AS line
FROM stage_days WHERE org = :org AND env = :env
ORDER BY day, agent, config_version, stage, vendor, model
""")

JUDGE_DAYS = text("""
SELECT jsonb_build_object(
    'kind', 'judge_day', 'holder', holder, 'agent', agent, 'day', day,
    'config_version', config_version, 'judge', judge, 'criteria', criteria, 'held', held,
    'broken', broken
)::text AS line
FROM judge_days WHERE org = :org AND env = :env
ORDER BY day, agent, config_version, judge, criteria
""")

TOOL_DAYS = text("""
SELECT jsonb_build_object(
    'kind', 'tool_day', 'holder', holder, 'agent', agent, 'day', day, 'tool', tool, 'ran', ran,
    'failed', failed, 'buckets', buckets, 'last_error_call', last_error_call,
    'last_error_at', last_error_at, 'last_error_text', last_error_text
)::text AS line
FROM tool_days WHERE org = :org AND env = :env
ORDER BY day, agent, tool
""")

# The slowest turns of each call, with the caller's name.
SLOW_TURNS = text("""
SELECT jsonb_build_object(
    'kind', 'slow_turn', 'holder', holder, 'agent', agent, 'day', day, 'call', call, 'seq', seq,
    'at', at, 'name', name, 'e2e_s', e2e_s, 'hears_s', hears_s, 'thinks_s', thinks_s,
    'tools_s', tools_s, 'speaks_s', speaks_s
)::text AS line
FROM slow_turns WHERE org = :org AND env = :env
ORDER BY day, agent, call, seq
""")

# What follows the calls, in this order.
AFTER_THE_CALLS: tuple[TextClause, ...] = (
    MEMORIES,
    SETTINGS,
    CANARIES,
    LEXICON,
    DOCUMENTS,
    CONSENTS,
    CASES,
    PROMPTS,
    STAGE_DAYS,
    JUDGE_DAYS,
    TOOL_DAYS,
    SLOW_TURNS,
)


@dataclass(frozen=True, slots=True)
class CallLine:
    """One call as a line, and the cursor it moves the page to."""

    line: str
    at: float
    call: str


class ExportRepository(Repository[CallLogHead]):
    """The org's env, table by table, each row already a JSON line."""

    model = CallLogHead

    async def calls_after(self, org: str, env: Env, at: float, call: str, *, page: int) -> list[CallLine]:
        """One page of calls after the cursor: the line, and the cursor each moves to."""
        params = {"org": org, "env": env.value, "at": at, "call": call, "page": page}
        rows = (await self.session.execute(CALLS, params)).all()
        return [CallLine(str(line), float(moved), str(moved_call)) for line, moved, moved_call in rows]

    async def lines_of(self, query: TextClause, org: str, env: Env) -> list[str]:
        """Every row of one of the tables after the calls, as lines."""
        rows = (await self.session.execute(query, {"org": org, "env": env.value})).scalars()
        return [str(line) for line in rows]
