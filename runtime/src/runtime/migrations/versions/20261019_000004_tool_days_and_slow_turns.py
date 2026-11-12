"""tool_days and slow_turns: each tool's day and each call's slowest turns, folded at the seal.

Revision: 000004
Revises: 000003
Date: 2026-10-19

Two new tables, under the row-level security every org table has (0096_row_level_security.sql
made its policy for the tables that existed then; a table made since carries its own). They are
empty until a call is sealed or `pinecall-runtime drift rebuild` folds the sealed ones again.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import ARRAY

revision: str = "000004"
down_revision: str | None = "000003"
branch_labels: Sequence[str] | None = None
depends_on: Sequence[str] | None = None

TABLES = ("tool_days", "slow_turns")
SCOPED = "coalesce(current_setting('pinecall.org', true), '') = '' OR org = current_setting('pinecall.org', true)"


def upgrade() -> None:
    """Make the tables, their index and their policy."""
    op.create_table(
        "tool_days",
        sa.Column("org", sa.Text(), nullable=False),
        sa.Column("env", sa.Text(), nullable=False),
        sa.Column("holder", sa.Text(), nullable=False),
        sa.Column("day", sa.Date(), nullable=False),
        sa.Column("agent", sa.Text(), nullable=False),
        sa.Column("tool", sa.Text(), nullable=False),
        sa.Column("ran", sa.Integer(), nullable=False),
        sa.Column("failed", sa.Integer(), nullable=False),
        sa.Column("buckets", ARRAY(sa.Integer()), nullable=False),
        sa.Column("last_error_call", sa.Text(), nullable=True),
        sa.Column("last_error_at", sa.Float(), nullable=True),
        sa.Column("last_error_text", sa.Text(), nullable=True),
        sa.ForeignKeyConstraint(["org"], ["orgs.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("org", "env", "holder", "day", "agent", "tool"),
    )
    op.create_table(
        "slow_turns",
        sa.Column("call", sa.Text(), nullable=False),
        sa.Column("seq", sa.Integer(), nullable=False),
        sa.Column("org", sa.Text(), nullable=False),
        sa.Column("env", sa.Text(), nullable=False),
        sa.Column("holder", sa.Text(), nullable=False),
        sa.Column("agent", sa.Text(), nullable=False),
        sa.Column("day", sa.Date(), nullable=False),
        sa.Column("at", sa.Float(), nullable=False),
        sa.Column("name", sa.Text(), nullable=True),
        sa.Column("e2e_s", sa.Float(), nullable=False),
        sa.Column("hears_s", sa.Float(), nullable=True),
        sa.Column("thinks_s", sa.Float(), nullable=True),
        sa.Column("tools_s", sa.Float(), nullable=True),
        sa.Column("speaks_s", sa.Float(), nullable=True),
        sa.ForeignKeyConstraint(["org"], ["orgs.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("call", "seq"),
    )
    op.create_index("slow_turns_by_day", "slow_turns", ["org", "env", "day"])
    for table in TABLES:
        op.execute(sa.text(f"ALTER TABLE {table} ENABLE ROW LEVEL SECURITY"))
        op.execute(sa.text(f"CREATE POLICY org_scoped ON {table} USING ({SCOPED}) WITH CHECK ({SCOPED})"))


def downgrade() -> None:
    """Undo: the days and turns folded go with the tables; `drift rebuild` makes them again."""
    op.drop_index("slow_turns_by_day", table_name="slow_turns")
    op.drop_table("slow_turns")
    op.drop_table("tool_days")
