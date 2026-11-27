"""model.spent: a flow's model, asked outside a call, is counted as written turns, tokens and spend.

Revision: 000040
Revises: 000039
Date: 2026-11-27

A flow's `extract` step asks a model to read words into an object, with no call around it: nothing was
counted of it, so an org's messages, tokens and month's budget never saw it. Its request is written on
the agent's log as `model.spent`, shaped as a summary is for the fold (`turns`, `usage`, `cost.usd`), with
its env in its data as `evals.spent` has: here the fold counts its turns as messages, its LLM rows as
tokens and its cost as the month's spend, and the three triggers fold it with the other metered types.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "000040"
down_revision: str | None = "000039"
branch_labels: Sequence[str] | None = None
depends_on: Sequence[str] | None = None

METERED = "('call.summary', 'call.score', 'evals.spent')"
METERED_NOW = "('call.summary', 'call.score', 'evals.spent', 'model.spent')"

# The env of an entry on an agent's log, whose head has none, is in its data.
ENV_OF_AN_ENTRY = """
CREATE OR REPLACE FUNCTION usage_world(kind text, data jsonb, head_env text) RETURNS text
    LANGUAGE sql IMMUTABLE
    AS $$ SELECT CASE WHEN kind IN ({kinds}) THEN data ->> 'env' ELSE head_env END $$
"""

# 000013's body, with a model's request counted as a written call's turns are: messages, tokens and spend.
ENTRY_USAGE = """
CREATE OR REPLACE FUNCTION entry_usage(
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
           CASE WHEN kind = 'model.spent' THEN used.messages
                WHEN kind <> 'call.summary' OR opened_by IN ('fleet', 'app') THEN 0
                ELSE used.messages END,
           CASE WHEN kind IN ('call.summary', 'model.spent') THEN used.input_tokens ELSE 0 END,
           CASE WHEN kind IN ('call.summary', 'model.spent') THEN used.output_tokens ELSE 0 END,
           CASE WHEN kind = 'call.summary' THEN used.characters ELSE 0 END,
           CASE WHEN kind IN ('call.summary', 'model.spent') OR data -> 'own_key' = 'true'::jsonb THEN 0
                ELSE usage_number(data -> 'evals') END::bigint,
           CASE WHEN kind = 'call.summary' AND data -> 'simulated' = 'true'::jsonb THEN 1
                ELSE 0 END::bigint,
           CASE WHEN kind IN ('call.summary', 'model.spent') THEN used.cost_usd ELSE 0 END
    FROM summary_usage(data) AS used
$$
"""

ENTRY_USAGE_BEFORE = """
CREATE OR REPLACE FUNCTION entry_usage(
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

# 000013's three triggers, word for word but the types they fold.
WRITTEN = """
CREATE OR REPLACE FUNCTION usage_of_summaries_written() RETURNS trigger
    LANGUAGE plpgsql
    AS $$
begin
    if not exists (
        select 1 from summaries where type in {kinds}
    ) then
        return null;
    end if;
    perform usage_counted(coalesce(jsonb_agg(jsonb_build_object(
        'org', head.org, 'env', usage_world(entry.type, entry.data, head.env), 'ts', entry.ts,
        'type', entry.type, 'data', entry.data, 'opened_by', head.opened_by)), '[]'), 1)
    from summaries entry join call_log_head head on head.log = entry.log
    where entry.type in {kinds};
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
    where entry.type in {kinds};
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
    where entry.log = new.log and entry.type in {kinds};
    return null;
end;
$$
"""


def upgrade() -> None:
    """A model's request is folded with the metered types: its turns as messages, its tokens, its spend."""
    op.execute(sa.text(ENV_OF_AN_ENTRY.format(kinds="'evals.spent', 'model.spent'")))
    op.execute(sa.text(ENTRY_USAGE))
    for function in (WRITTEN, ERASED, MOVED):
        op.execute(sa.text(function.format(kinds=METERED_NOW)))


def downgrade() -> None:
    """Undo: the fold counts the three metered types it counted before, and model.spent is read as nothing."""
    op.execute(sa.text(ENV_OF_AN_ENTRY.format(kinds="'evals.spent'")))
    op.execute(sa.text(ENTRY_USAGE_BEFORE))
    for function in (WRITTEN, ERASED, MOVED):
        op.execute(sa.text(function.format(kinds=METERED)))
