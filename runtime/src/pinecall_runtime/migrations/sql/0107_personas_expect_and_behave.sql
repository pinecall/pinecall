-- A persona says what it expects of the agent, one line each (the expected-outcome judge reads
-- them), carries tags, and how it acts on a spoken line: how often it talks over the agent, how
-- long it pauses, the noise under it. The library's personas (evals/library/personas/) are
-- switched on or off per org and per agent, as its judges are. Expanding only: `accepts_when` and
-- `declines_when` are read no more and dropped by a later release; what they held is carried into
-- `expects` here.
--
-- Locks and time: the ALTER takes ACCESS EXCLUSIVE on agent_personas for the instant of adding
-- defaulted columns (no rewrite); the UPDATE rewrites the rows that held a rule (tens per org);
-- persona_switches is a new table under the row-level security every org table has.

ALTER TABLE agent_personas
    ADD COLUMN expects jsonb NOT NULL DEFAULT '[]'::jsonb,
    ADD COLUMN tags jsonb NOT NULL DEFAULT '[]'::jsonb,
    ADD COLUMN behavior jsonb NOT NULL DEFAULT '{}'::jsonb;

UPDATE agent_personas SET expects = (
    SELECT coalesce(jsonb_agg(line), '[]'::jsonb) FROM (
        SELECT 'The caller is satisfied when ' || accepts_when AS line WHERE accepts_when <> ''
        UNION ALL
        SELECT 'The caller hangs up unsatisfied when ' || declines_when WHERE declines_when <> ''
    ) AS lines
)
WHERE accepts_when <> '' OR declines_when <> '';

-- agent '' is the org's own switch, the default for every agent; an agent's row wins over it.
CREATE TABLE persona_switches (
    org text NOT NULL REFERENCES orgs(id) ON DELETE CASCADE,
    agent text NOT NULL DEFAULT '',
    name text NOT NULL,
    is_on boolean NOT NULL,
    author text NOT NULL DEFAULT '',
    set_at timestamp with time zone DEFAULT now() NOT NULL,
    CONSTRAINT persona_switches_pkey PRIMARY KEY (org, agent, name)
);

ALTER TABLE persona_switches ENABLE ROW LEVEL SECURITY;
CREATE POLICY org_scoped ON persona_switches
    USING (coalesce(current_setting('pinecall.org', true), '') = ''
           OR org = current_setting('pinecall.org', true))
    WITH CHECK (coalesce(current_setting('pinecall.org', true), '') = ''
                OR org = current_setting('pinecall.org', true));
