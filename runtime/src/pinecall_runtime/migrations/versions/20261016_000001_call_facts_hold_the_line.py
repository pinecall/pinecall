"""call_facts holds the line a list shows of a sealed call, so a list folds no log.

Revision: 000001
Revises: 000000
Date: 2026-10-16
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB

revision: str = "000001"
down_revision: str | None = "000000"
branch_labels: Sequence[str] | None = None
depends_on: Sequence[str] | None = None


def upgrade() -> None:
    """The column; `pinecall-runtime facts rebuild` fills it for the calls sealed before this."""
    op.add_column("call_facts", sa.Column("line", JSONB(), nullable=True))


def downgrade() -> None:
    """Undo."""
    op.drop_column("call_facts", "line")
