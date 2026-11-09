"""comparisons: what a comparison was asked for, and how its placing stands.

Revision: 000020
Revises: 000019
Date: 2026-11-09

A comparison was only the calls it had placed, found by its id on call_facts: placed all at once,
ten at most. One that repeats each caller against each setup places more calls than an org may have
on the line, so the rest wait their turn, and a call that waits has no row anywhere. This table
keeps what was asked for (the callers, the setups, the repeats) and what was refused, under the
row-level security every org table has. It starts empty: a comparison made before reads as before.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB

revision: str = "000020"
down_revision: str | None = "000019"
branch_labels: Sequence[str] | None = None
depends_on: Sequence[str] | None = None

SCOPED = "coalesce(current_setting('pinecall.org', true), '') = '' OR org = current_setting('pinecall.org', true)"


def upgrade() -> None:
    """Make the table, its index and its policy."""
    op.create_table(
        "comparisons",
        sa.Column("id", sa.Text(), nullable=False),
        sa.Column("org", sa.Text(), nullable=False),
        sa.Column("env", sa.Text(), nullable=False),
        sa.Column("agent", sa.Text(), nullable=False),
        sa.Column("started_at", sa.Float(), nullable=False),
        sa.Column("document", JSONB(), nullable=False),
        sa.ForeignKeyConstraint(["org"], ["orgs.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("comparisons_by_scope", "comparisons", ["org", "env", sa.text("started_at DESC")])
    op.execute(sa.text("ALTER TABLE comparisons ENABLE ROW LEVEL SECURITY"))
    op.execute(sa.text(f"CREATE POLICY org_scoped ON comparisons USING ({SCOPED}) WITH CHECK ({SCOPED})"))


def downgrade() -> None:
    """Undo: what was asked of each comparison goes with the table; its calls stay."""
    op.drop_index("comparisons_by_scope", table_name="comparisons")
    op.drop_table("comparisons")
