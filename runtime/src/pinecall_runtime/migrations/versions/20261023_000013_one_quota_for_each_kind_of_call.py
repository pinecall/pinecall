"""The totals' fold: one quota for each kind of call, a written call spends messages and a spoken one minutes.

Revision: 000013
Revises: 000012
Date: 2026-10-23

`entry_usage` counted every call.summary's `duration_s` as minutes except a simulated caller's and an eval
run's, and every call's turns as messages, so a `pinecall chat` of two seconds spent two seconds of the org's
minutes (and of the minutes its plan bills) as a spoken call does, and a spoken call spent messages as a
written one does. One quota for each kind of call: a written call spends messages and no minutes, a spoken
call minutes and no messages. The summary does not say how the call was had, and the wire is strict, so the
fold reads it where the head already says it: a call is opened by the fleet's worker, by an app, or by the
gateway, and the gateway opens only written sessions (`open_text_as`). `entry_usage` takes the head's
`opened_by`, and the three triggers and the rebuild hand it over.

A call opened before heads said who opened them has no `opened_by` and counts as it did, its minutes and its
turns both. The months already counted keep what was added to them: `pinecall-runtime usage rebuild` counts
them again from the logs.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "000013"
down_revision: str | None = "000012"
branch_labels: Sequence[str] | None = None
depends_on: Sequence[str] | None = None

# 0106's body, with the minutes of a call the gateway opened and the messages of one the fleet or an app opened
# left at zero.
ENTRY_USAGE_WRITTEN = """
CREATE FUNCTION entry_usage(
    kind text, data jsonb, opened_by text,
    OUT calls bigint, OUT minutes double precision, OUT messages bigint,
    OUT input_tokens bigint, OUT output_tokens bigint, OUT characters bigint,
    OUT evals bigint, OUT simulations bigint, OUT cost_usd double precision
)
    LANGUAGE sql IMMUTABLE
    AS $$
    SELECT CASE WHEN kind = 'call.summary' THEN 1 ELSE 0 END::bigint,
           CASE WHEN kind <> 'call.summary' THEN 0
                WHEN data -> 'simulated' = 'true'::jsonb
                     OR jsonb_typeof(data -> 'run') = 'string'
                     OR opened_by = 'gateway' THEN 0
                ELSE usage_number(data -> 'duration_s')::float8 / 60 END,
           CASE WHEN kind <> 'call.summary' OR opened_by IN ('fleet', 'app') THEN 0 ELSE used.messages END,
           CASE WHEN kind = 'call.summary' THEN used.input_tokens ELSE 0 END,
           CASE WHEN kind = 'call.summary' THEN used.output_tokens ELSE 0 END,
           CASE WHEN kind = 'call.summary' THEN used.characters ELSE 0 END,
           CASE WHEN kind = 'call.summary' OR data -> 'own_key' = 'true'::jsonb THEN 0
                ELSE usage_number(data -> 'evals') END::bigint,
           CASE WHEN kind = 'call.summary' AND data -> 'simulated' = 'true'::jsonb THEN 1
                ELSE 0 END::bigint,
           CASE WHEN kind = 'call.summary' THEN used.cost_usd ELSE 0 END
    FROM summary_usage(data) AS used
$$
"""

ENTRY_USAGE_BEFORE = """
CREATE FUNCTION entry_usage(
    kind text, data jsonb,
    OUT calls bigint, OUT minutes double precision, OUT messages bigint,
    OUT input_tokens bigint, OUT output_tokens bigint, OUT characters bigint,
    OUT evals bigint, OUT simulations bigint, OUT cost_usd double precision
)
    LANGUAGE sql IMMUTABLE
    AS $$
    SELECT CASE WHEN kind = 'call.summary' THEN 1 ELSE 0 END::bigint,
           CASE WHEN kind <> 'call.summary' THEN 0
                WHEN data -> 'simulated' = 'true'::jsonb
                     OR jsonb_typeof(data -> 'run') = 'string' THEN 0
                ELSE usage_number(data -> 'duration_s')::float8 / 60 END,
           CASE WHEN kind = 'call.summary' THEN used.messages ELSE 0 END,
           CASE WHEN kind = 'call.summary' THEN used.input_tokens ELSE 0 END,
           CASE WHEN kind = 'call.summary' THEN used.output_tokens ELSE 0 END,
           CASE WHEN kind = 'call.summary' THEN used.characters ELSE 0 END,
           CASE WHEN kind = 'call.summary' OR data -> 'own_key' = 'true'::jsonb THEN 0
                ELSE usage_number(data -> 'evals') END::bigint,
           CASE WHEN kind = 'call.summary' AND data -> 'simulated' = 'true'::jsonb THEN 1
                ELSE 0 END::bigint,
           CASE WHEN kind = 'call.summary' THEN used.cost_usd ELSE 0 END
    FROM summary_usage(data) AS used
$$
"""

USAGE_COUNTED = """
CREATE OR REPLACE FUNCTION usage_counted(summaries jsonb, sign integer) RETURNS void
    LANGUAGE sql
    AS $$
    INSERT INTO usage_totals AS total
        (org, env, period, calls, minutes, messages, input_tokens, output_tokens, characters,
         evals, simulations, cost_usd)
    SELECT one ->> 'org', one ->> 'env', usage_period((one ->> 'ts')::float8),
           sign * sum(used.calls), sign * sum(used.minutes), sign * sum(used.messages),
           sign * sum(used.input_tokens), sign * sum(used.output_tokens),
           sign * sum(used.characters), sign * sum(used.evals), sign * sum(used.simulations),
           sign * sum(used.cost_usd)
    FROM jsonb_array_elements(summaries) AS one
    CROSS JOIN LATERAL entry_usage(one ->> 'type', one -> 'data', one ->> 'opened_by') AS used
    WHERE one ->> 'org' IS NOT NULL AND one ->> 'env' IS NOT NULL
    GROUP BY 1, 2, 3
    ORDER BY 1, 2, 3
    ON CONFLICT (org, env, period) DO UPDATE SET
        calls = total.calls + excluded.calls,
        minutes = total.minutes + excluded.minutes,
        messages = total.messages + excluded.messages,
        input_tokens = total.input_tokens + excluded.input_tokens,
        output_tokens = total.output_tokens + excluded.output_tokens,
        characters = total.characters + excluded.characters,
        evals = total.evals + excluded.evals,
        simulations = total.simulations + excluded.simulations,
        cost_usd = total.cost_usd + excluded.cost_usd
$$
"""

USAGE_COUNTED_BEFORE = USAGE_COUNTED.replace(
    "entry_usage(one ->> 'type', one -> 'data', one ->> 'opened_by')", "entry_usage(one ->> 'type', one -> 'data')"
)

# The fold's three triggers, each handing the head's opened_by over beside the entry.
WRITTEN = """
CREATE OR REPLACE FUNCTION usage_of_summaries_written() RETURNS trigger
    LANGUAGE plpgsql
    AS $$
begin
    if not exists (
        select 1 from summaries where type in ('call.summary', 'call.score', 'evals.spent')
    ) then
        return null;
    end if;
    perform usage_counted(coalesce(jsonb_agg(jsonb_build_object(
        'org', head.org, 'env', usage_world(entry.type, entry.data, head.env), 'ts', entry.ts,
        'type', entry.type, 'data', entry.data, 'opened_by', head.opened_by)), '[]'), 1)
    from summaries entry join call_log_head head on head.log = entry.log
    where entry.type in ('call.summary', 'call.score', 'evals.spent');
    return null;
end;
$$
"""

ERASED = """
CREATE OR REPLACE FUNCTION usage_of_summaries_erased() RETURNS trigger
    LANGUAGE plpgsql
    AS $$
begin
    perform usage_counted(coalesce(jsonb_agg(jsonb_build_object(
        'org', head.org, 'env', usage_world(entry.type, entry.data, head.env), 'ts', entry.ts,
        'type', entry.type, 'data', entry.data, 'opened_by', head.opened_by)), '[]'), -1)
    from summaries entry join call_log_head head on head.log = entry.log
    where entry.type in ('call.summary', 'call.score', 'evals.spent');
    return null;
end;
$$
"""

MOVED = """
CREATE OR REPLACE FUNCTION usage_of_a_log_moved() RETURNS trigger
    LANGUAGE plpgsql
    AS $$
begin
    perform usage_counted(coalesce(jsonb_agg(jsonb_build_object(
        'org', old.org, 'env', usage_world(entry.type, entry.data, old.env), 'ts', entry.ts,
        'type', entry.type, 'data', entry.data, 'opened_by', old.opened_by)), '[]'), -1),
            usage_counted(coalesce(jsonb_agg(jsonb_build_object(
        'org', new.org, 'env', usage_world(entry.type, entry.data, new.env), 'ts', entry.ts,
        'type', entry.type, 'data', entry.data, 'opened_by', new.opened_by)), '[]'), 1)
    from call_log entry
    where entry.log = new.log and entry.type in ('call.summary', 'call.score', 'evals.spent');
    return null;
end;
$$
"""


def _without_the_opener(sql: str) -> str:
    return (
        sql.replace(", 'opened_by', head.opened_by", "")
        .replace(", 'opened_by', old.opened_by", "")
        .replace(", 'opened_by', new.opened_by", "")
    )


def upgrade() -> None:
    """The fold reads who opened the log, for minutes and messages; totals already counted wait for a rebuild."""
    op.execute(sa.text(ENTRY_USAGE_WRITTEN))
    op.execute(sa.text(USAGE_COUNTED))
    for function in (WRITTEN, ERASED, MOVED):
        op.execute(sa.text(function))
    op.execute(sa.text("DROP FUNCTION entry_usage(text, jsonb)"))


def downgrade() -> None:
    """Undo: a written call counts its seconds as minutes again, and a spoken one its turns as messages."""
    op.execute(sa.text(ENTRY_USAGE_BEFORE))
    op.execute(sa.text(USAGE_COUNTED_BEFORE))
    for function in (WRITTEN, ERASED, MOVED):
        op.execute(sa.text(_without_the_opener(function)))
    op.execute(sa.text("DROP FUNCTION entry_usage(text, jsonb, text)"))
