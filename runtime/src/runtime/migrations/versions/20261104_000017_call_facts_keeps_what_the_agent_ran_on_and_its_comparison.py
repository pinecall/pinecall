"""call_facts keeps the voice and models the agent ran on for the call alone, and the comparison it was placed in.

Revision: 000017
Revises: 000016
Date: 2026-11-04

A simulation may run the agent on another voice or model over its settings, as a test room does, and
several placed together on one persona are a comparison: the row keeps what the agent ran on
(`against`) and the comparison's id, so the runs list and the comparison's table read them without
folding a log. Null for every call before them, and for every call that ran the settings as they are.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "000017"
down_revision: str | None = "000016"
branch_labels: Sequence[str] | None = None
depends_on: Sequence[str] | None = None


def upgrade() -> None:
    """The columns, empty for every call before them, and the index a comparison's table reads by."""
    op.add_column("call_facts", sa.Column("against", postgresql.JSONB(astext_type=sa.Text()), nullable=True))
    op.add_column("call_facts", sa.Column("comparison", sa.Text(), nullable=True))
    op.create_index(
        "call_facts_by_comparison",
        "call_facts",
        ["comparison"],
        unique=False,
        postgresql_where=sa.text("comparison IS NOT NULL"),
    )


def downgrade() -> None:
    """Undo."""
    op.drop_index(
        "call_facts_by_comparison", table_name="call_facts", postgresql_where=sa.text("comparison IS NOT NULL")
    )
    op.drop_column("call_facts", "comparison")
    op.drop_column("call_facts", "against")
