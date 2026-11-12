"""alerts: every alert an org was raised, kept, and whether it was mailed.

Revision: 000011
Revises: 000010
Date: 2026-10-23

One new table under the row-level security every org table has. An alert used to reach the agent's
log and the org's webhook only; an app that went down reached nothing when the org named no URL.
Empty until the next alert; the nightly retention forgets a row past 90 days.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB

revision: str = "000011"
down_revision: str | None = "000010"
branch_labels: Sequence[str] | None = None
depends_on: Sequence[str] | None = None

SCOPED = "coalesce(current_setting('pinecall.org', true), '') = '' OR org = current_setting('pinecall.org', true)"


def upgrade() -> None:
    """Make the table, its index and its policy."""
    op.create_table(
        "alerts",
        sa.Column("id", sa.Text(), nullable=False),
        sa.Column("org", sa.Text(), nullable=False),
        sa.Column("env", sa.Text(), nullable=False),
        sa.Column("agent", sa.Text(), nullable=True),
        sa.Column("kind", sa.Text(), nullable=False),
        sa.Column("subject", sa.Text(), nullable=False),
        sa.Column("data", JSONB(), nullable=False),
        sa.Column("mailed", sa.Boolean(), nullable=False),
        sa.Column("at", sa.TIMESTAMP(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["org"], ["orgs.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("alerts_by_org", "alerts", ["org", "env", "at"])
    op.execute(sa.text("ALTER TABLE alerts ENABLE ROW LEVEL SECURITY"))
    op.execute(sa.text(f"CREATE POLICY org_scoped ON alerts USING ({SCOPED}) WITH CHECK ({SCOPED})"))


def downgrade() -> None:
    """Undo: the alerts kept go with the table; the agents' logs still hold theirs."""
    op.drop_index("alerts_by_org", table_name="alerts")
    op.drop_table("alerts")
