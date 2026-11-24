"""An offer says when its call opened.

Revision: 000034
Revises: 000033
Date: 2026-11-24

An offer was deleted the moment a worker opened its call, and the worker's heartbeat says that call
only at its next beat, up to five seconds later: in between, the slot read as free. A queue of
simulated callers waiting for a seat was offered that slot, sent to a worker that was full, and
answered by the overflow's sentence. The row stays now, with when the call opened, and takes the
slot until its worker's next heartbeat.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "000034"
down_revision: str | None = "000033"
branch_labels: Sequence[str] | None = None
depends_on: Sequence[str] | None = None


def upgrade() -> None:
    """The moment a worker opened the room's call; none for a room still waiting."""
    op.add_column("offers", sa.Column("opened_at", sa.Float(), nullable=True))


def downgrade() -> None:
    """Undo: the rooms a worker opened are let go, as they were at once before."""
    op.execute("DELETE FROM offers WHERE opened_at IS NOT NULL")
    op.drop_column("offers", "opened_at")
