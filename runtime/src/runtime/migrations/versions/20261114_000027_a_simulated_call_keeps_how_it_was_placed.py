"""A simulated call keeps how it was placed.

Revision: 000027
Revises: 000026
Date: 2026-11-14

A simulation that broke could not be placed again as it was: the line (spoken or written), its
turns, the room behind the caller and how loud, who played it and what it phoned about were the
request's, and nothing kept them once the call was on. They are kept with the call's facts now,
so a call can be run again from its id alone. Every simulated call before this has none, and is
placed again from its caller's page.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "000027"
down_revision: str | None = "000026"
branch_labels: Sequence[str] | None = None
depends_on: Sequence[str] | None = None


def upgrade() -> None:
    """The column, empty for every call there is."""
    op.add_column("call_facts", sa.Column("placed", postgresql.JSONB(), nullable=True))


def downgrade() -> None:
    """Undo."""
    op.drop_column("call_facts", "placed")
