"""A chunk is a piece of text or a question that piece answers: `kind`, text for every row so far.

Revision: 000008
Revises: 000007
Date: 2026-10-21
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "000008"
down_revision: str | None = "000007"
branch_labels: Sequence[str] | None = None
depends_on: Sequence[str] | None = None


def upgrade() -> None:
    """The column, `text` on every chunk written before it."""
    op.add_column("knowledge_chunks", sa.Column("kind", sa.Text(), nullable=False, server_default="text"))
    op.alter_column("knowledge_chunks", "kind", server_default=None)


def downgrade() -> None:
    """Undo: the questions go with the column."""
    op.execute("DELETE FROM knowledge_chunks WHERE kind = 'ask'")
    op.drop_column("knowledge_chunks", "kind")
