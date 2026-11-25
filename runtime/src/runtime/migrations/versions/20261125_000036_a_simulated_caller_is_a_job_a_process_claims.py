"""caller_jobs: each simulated caller of a spoken call as a job one process claims; call_facts keeps how its line ran.

Revision: 000036
Revises: 000035
Date: 2026-11-25

A simulated caller was a coroutine of the gateway that took its request. Nineteen of them on that one
loop were late with their frames: the room heard twenty to a hundred milliseconds of silence inside
the caller's words, thirty-six to fifty-five times a minute, in 101 of 140 calls of a run that was
then thrown away; and a release of the gateway ended every one on the line. A caller is a row now,
written by the gateway that places its call and claimed by the one process that plays it (a gateway,
or a callers process beside them), which says it still has it every few seconds. The table is under
the row-level security every org table has; a process claims across orgs as the box. It starts
empty: a gateway of the release before this one plays its own callers and writes no row.

`call_facts.caller_line` is what the caller's leg measured of itself: the frames it carried and how
many left late against the clock. NULL for any call but a spoken simulation played since this release.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB

revision: str = "000036"
down_revision: str | None = "000035"
branch_labels: Sequence[str] | None = None
depends_on: Sequence[str] | None = None

SCOPED = "coalesce(current_setting('pinecall.org', true), '') = '' OR org = current_setting('pinecall.org', true)"


def upgrade() -> None:
    """Make the table, its indexes and its policy, and the column."""
    op.create_table(
        "caller_jobs",
        sa.Column("call", sa.Text(), nullable=False),
        sa.Column("org", sa.Text(), nullable=False),
        sa.Column("env", sa.Text(), nullable=False),
        sa.Column("agent", sa.Text(), nullable=False),
        sa.Column("comparison", sa.Text(), nullable=True),
        sa.Column("document", JSONB(), nullable=True),
        sa.Column("placed_at", sa.Float(), nullable=False),
        sa.Column("claimed_by", sa.Text(), nullable=True),
        sa.Column("heard_at", sa.Float(), nullable=True),
        sa.Column("played", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("broke", sa.Text(), nullable=True),
        sa.Column("ended_at", sa.Float(), nullable=True),
        sa.Column("lost", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.ForeignKeyConstraint(["org"], ["orgs.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("call"),
    )
    op.create_index("caller_jobs_by_scope", "caller_jobs", ["org", "env"])
    op.create_index("caller_jobs_by_age", "caller_jobs", ["placed_at"])
    op.execute(sa.text("ALTER TABLE caller_jobs ENABLE ROW LEVEL SECURITY"))
    op.execute(sa.text(f"CREATE POLICY org_scoped ON caller_jobs USING ({SCOPED}) WITH CHECK ({SCOPED})"))
    op.add_column("call_facts", sa.Column("caller_line", JSONB(), nullable=True))


def downgrade() -> None:
    """Undo: the callers still to play go with the table, and what each line measured with the column."""
    op.drop_column("call_facts", "caller_line")
    op.drop_index("caller_jobs_by_age", table_name="caller_jobs")
    op.drop_index("caller_jobs_by_scope", table_name="caller_jobs")
    op.drop_table("caller_jobs")
