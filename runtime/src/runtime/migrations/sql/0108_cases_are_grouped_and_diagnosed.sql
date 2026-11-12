-- The cases a judge broke on are grouped, one open group per agent and judge: a person reads one
-- cause, not fifty calls (evals/groups.py). A group carries a diagnosis a model wrote, its cause
-- and a proposal — a setting to change, code to change, knowledge to add — which a person applies
-- or hands to their assistant (evals/proposing.py). A simulation a judge broke on is kept too,
-- with the persona that played it. Expanding only.
--
-- Locks and time: case_groups is a new table under the row-level security every org table has;
-- the ALTER of eval_cases adds nullable or defaulted columns (no rewrite) under ACCESS EXCLUSIVE
-- for that instant.

CREATE TABLE case_groups (
    id text PRIMARY KEY,
    org text NOT NULL REFERENCES orgs(id) ON DELETE CASCADE,
    agent text NOT NULL,
    judge text NOT NULL,
    -- One line: what the calls of the group have in common; the first reason until a diagnosis.
    cause text NOT NULL DEFAULT '',
    status text NOT NULL DEFAULT 'pending' CHECK (status IN ('pending', 'approved', 'dismissed')),
    since timestamp with time zone DEFAULT now() NOT NULL,
    proposal jsonb,
    proposed_at timestamp with time zone
);

-- One open group per agent and judge: a case a second seal keeps at the same moment joins it.
CREATE UNIQUE INDEX case_groups_one_open ON case_groups (org, agent, judge)
    WHERE status = 'pending';

ALTER TABLE case_groups ENABLE ROW LEVEL SECURITY;
CREATE POLICY org_scoped ON case_groups
    USING (coalesce(current_setting('pinecall.org', true), '') = ''
           OR org = current_setting('pinecall.org', true))
    WITH CHECK (coalesce(current_setting('pinecall.org', true), '') = ''
                OR org = current_setting('pinecall.org', true));

ALTER TABLE eval_cases
    ADD COLUMN group_id text REFERENCES case_groups(id) ON DELETE SET NULL,
    ADD COLUMN source text NOT NULL DEFAULT 'call' CHECK (source IN ('call', 'simulation')),
    ADD COLUMN persona text;

CREATE INDEX eval_cases_by_group ON eval_cases (group_id) WHERE group_id IS NOT NULL;
