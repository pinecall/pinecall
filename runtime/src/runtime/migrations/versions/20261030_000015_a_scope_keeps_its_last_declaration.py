"""agents: each scope keeps the last declaration its app made of an agent.

Revision: 000015
Revises: 000014
Date: 2026-10-30

A declaration lived in the registry's memory while a socket held the agent: `fixed` went with the
socket, so a gateway that restarted, and a settings screen opened with nobody holding the agent,
read nothing as the class's. One row per scope and agent keeps the wire's declaration as the app
sent it, merged over one socket's life; the registry still says what is held now, and the row
says what the class fixed last. Under the row-level security every org table has; starts empty.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB

revision: str = "000015"
down_revision: str | None = "000014"
branch_labels: Sequence[str] | None = None
depends_on: Sequence[str] | None = None

SCOPED = "coalesce(current_setting('pinecall.org', true), '') = '' OR org = current_setting('pinecall.org', true)"


def upgrade() -> None:
    """Make the table and its policy."""
    op.create_table(
        "agent_declarations",
        sa.Column("org", sa.Text(), nullable=False),
        sa.Column("env", sa.Text(), nullable=False),
        sa.Column("holder", sa.Text(), nullable=False),
        sa.Column("agent", sa.Text(), nullable=False),
        sa.Column("declared", JSONB(), nullable=False),
        sa.Column("sdk", sa.Text(), nullable=True),
        sa.Column("declared_at", sa.TIMESTAMP(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["org"], ["orgs.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("org", "env", "holder", "agent"),
    )
    op.execute(sa.text("ALTER TABLE agent_declarations ENABLE ROW LEVEL SECURITY"))
    op.execute(sa.text(f"CREATE POLICY org_scoped ON agent_declarations USING ({SCOPED}) WITH CHECK ({SCOPED})"))


def downgrade() -> None:
    """Undo: the declarations kept go with the table."""
    op.drop_table("agent_declarations")
