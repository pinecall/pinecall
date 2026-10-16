-- An org's evals and simulations are counted and may be limited, a month at a time, like its
-- minutes: `quotas` gains the two limits and `usage_totals` the two counts. The fold at write now
-- reads three types, as `usage_row` in pinecall/log/reduce.py does: a call.summary is a call (a
-- simulated one is one simulation and no minutes, an eval run's no minutes), a call.score and a
-- evals.spent are their evals (none when the judge ran on the org's own key). A evals.spent is on
-- the agent's log, which both worlds share, so it is counted in the world it names. A judge's
-- model calls and their cost are not counted here: an eval is what an org pays for. Expanding only.
--
-- Locks and time: the ALTERs take ACCESS EXCLUSIVE on quotas and usage_totals for the instant of
-- adding a nullable or defaulted column (no rewrite); the functions are replaced in place, so the
-- triggers on call_log (0027's) call the new bodies from the next statement. The backfill reads
-- the scores written since 0.1.45 counted evals (a few hours of production) through
-- call_log_metered and sets each month's evals and simulations; minutes already counted for a
-- simulation stay as they were until `pinecall-runtime usage rebuild` refolds the table.

ALTER TABLE quotas
    ADD COLUMN evals integer,
    ADD COLUMN simulations integer;

ALTER TABLE usage_totals
    ADD COLUMN evals bigint NOT NULL DEFAULT 0,
    ADD COLUMN simulations bigint NOT NULL DEFAULT 0;

-- The world an entry is counted in: its log's, but a try's own (the agent's log is both worlds').
CREATE FUNCTION usage_world(kind text, data jsonb, head_env text) RETURNS text
    LANGUAGE sql IMMUTABLE
    AS $$ SELECT CASE WHEN kind = 'evals.spent' THEN data ->> 'env' ELSE head_env END $$;

-- One metered entry's usage, as `usage_row` counts it for the totals.
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
$$;

-- Added to, or taken from with sign -1, by the metered entries of logs as their heads name them.
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
    CROSS JOIN LATERAL entry_usage(one ->> 'type', one -> 'data') AS used
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
$$;

-- Most statements write no metered entry: they leave after one look at their rows.
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
        'type', entry.type, 'data', entry.data)), '[]'), 1)
    from summaries entry join call_log_head head on head.log = entry.log
    where entry.type in ('call.summary', 'call.score', 'evals.spent');
    return null;
end;
$$;

CREATE OR REPLACE FUNCTION usage_of_summaries_erased() RETURNS trigger
    LANGUAGE plpgsql
    AS $$
begin
    perform usage_counted(coalesce(jsonb_agg(jsonb_build_object(
        'org', head.org, 'env', usage_world(entry.type, entry.data, head.env), 'ts', entry.ts,
        'type', entry.type, 'data', entry.data)), '[]'), -1)
    from summaries entry join call_log_head head on head.log = entry.log
    where entry.type in ('call.summary', 'call.score', 'evals.spent');
    return null;
end;
$$;

CREATE OR REPLACE FUNCTION usage_of_a_log_moved() RETURNS trigger
    LANGUAGE plpgsql
    AS $$
begin
    perform usage_counted(coalesce(jsonb_agg(jsonb_build_object(
        'org', old.org, 'env', usage_world(entry.type, entry.data, old.env), 'ts', entry.ts,
        'type', entry.type, 'data', entry.data)), '[]'), -1),
            usage_counted(coalesce(jsonb_agg(jsonb_build_object(
        'org', new.org, 'env', usage_world(entry.type, entry.data, new.env), 'ts', entry.ts,
        'type', entry.type, 'data', entry.data)), '[]'), 1)
    from call_log entry
    where entry.log = new.log and entry.type in ('call.summary', 'call.score', 'evals.spent');
    return null;
end;
$$;

-- The backfill: each month's evals and simulations, from the scores and summaries already written.
INSERT INTO usage_totals AS total (org, env, period, evals, simulations)
SELECT head.org, head.env, usage_period(entry.ts), sum(used.evals), sum(used.simulations)
FROM call_log entry
JOIN call_log_head head ON head.log = entry.log
CROSS JOIN LATERAL entry_usage(entry.type, entry.data) AS used
WHERE entry.type IN ('call.summary', 'call.score') AND head.org IS NOT NULL
  AND head.env IS NOT NULL
GROUP BY 1, 2, 3
ON CONFLICT (org, env, period) DO UPDATE SET
    evals = excluded.evals, simulations = excluded.simulations;
