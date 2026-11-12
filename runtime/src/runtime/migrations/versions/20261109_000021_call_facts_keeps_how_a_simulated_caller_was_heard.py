"""call_facts keeps how a simulated spoken call was heard, against what its caller really said.

Revision: 000021
Revises: 000020
Date: 2026-11-09

A simulated caller knows what it said and when, which no real call does: the agent's replies cut off
with nobody speaking, the turns it heard that nobody said, the lines it never answered and the words
it got wrong are all measured against that. The measures are kept with the call's facts when the
simulation ends, so a run's row and a comparison's board read them without folding a log. Null for
every call before, for every written one, and for every call nobody simulated.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "000021"
down_revision: str | None = "000020"
branch_labels: Sequence[str] | None = None
depends_on: Sequence[str] | None = None


def upgrade() -> None:
    """The column, empty for every call before it."""
    op.add_column("call_facts", sa.Column("hearing", postgresql.JSONB(astext_type=sa.Text()), nullable=True))


def downgrade() -> None:
    """Undo."""
    op.drop_column("call_facts", "hearing")
