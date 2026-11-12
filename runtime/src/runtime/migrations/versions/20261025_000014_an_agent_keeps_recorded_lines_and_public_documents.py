"""agents: the lines an agent's app has recorded in its voice, and the documents it publishes.

Revision: 000014
Revises: 000013
Date: 2026-10-25

Two new tables under the row-level security every org table has. A line is recorded once in the
agent's voice and kept by a hash of the voice, the lexicon and its text, so a page plays it with no
call; a document is JSON an app publishes under a name for any page to read with no key. Both
start empty.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB

revision: str = "000014"
down_revision: str | None = "000013"
branch_labels: Sequence[str] | None = None
depends_on: Sequence[str] | None = None

SCOPED = "coalesce(current_setting('pinecall.org', true), '') = '' OR org = current_setting('pinecall.org', true)"


def upgrade() -> None:
    """Make the tables, the lines' index and both policies."""
    op.create_table(
        "agent_documents",
        sa.Column("org", sa.Text(), nullable=False),
        sa.Column("env", sa.Text(), nullable=False),
        sa.Column("agent", sa.Text(), nullable=False),
        sa.Column("name", sa.Text(), nullable=False),
        sa.Column("body", JSONB(), nullable=False),
        sa.Column("set_at", sa.TIMESTAMP(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["org"], ["orgs.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("org", "env", "agent", "name"),
    )
    op.create_table(
        "agent_lines",
        sa.Column("org", sa.Text(), nullable=False),
        sa.Column("env", sa.Text(), nullable=False),
        sa.Column("agent", sa.Text(), nullable=False),
        sa.Column("id", sa.Text(), nullable=False),
        sa.Column("text", sa.Text(), nullable=False),
        sa.Column("voice", sa.Text(), nullable=False),
        sa.Column("audio", sa.LargeBinary(), nullable=False),
        sa.Column("duration_ms", sa.Integer(), nullable=False),
        sa.Column("words", JSONB(), nullable=False),
        sa.Column("timed", sa.Boolean(), nullable=False),
        sa.Column("recorded_at", sa.TIMESTAMP(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["org"], ["orgs.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("org", "env", "agent", "id"),
    )
    op.create_index("agent_lines_by_id", "agent_lines", ["id"])
    for table in ("agent_documents", "agent_lines"):
        op.execute(sa.text(f"ALTER TABLE {table} ENABLE ROW LEVEL SECURITY"))
        op.execute(sa.text(f"CREATE POLICY org_scoped ON {table} USING ({SCOPED}) WITH CHECK ({SCOPED})"))


def downgrade() -> None:
    """Undo: the lines recorded and the documents published go with their tables."""
    op.drop_index("agent_lines_by_id", table_name="agent_lines")
    op.drop_table("agent_lines")
    op.drop_table("agent_documents")
