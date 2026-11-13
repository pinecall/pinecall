"""A call's head says the test run it belongs to.

Revision: 000026
Revises: 000025
Date: 2026-11-13

A golden opens a call like any other, as a visitor of a page, and a list of calls showed it as
one: nothing a row is built from said it was a run's. The run is on `call.started`, inside each
call's log, which a list of fifty rows does not fold. The head says it now, claimed with the call.
Every call before this has none, which is true of all of them a list still shows as people's.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "000026"
down_revision: str | None = "000025"
branch_labels: Sequence[str] | None = None
depends_on: Sequence[str] | None = None


def upgrade() -> None:
    """The column, empty for every call there is."""
    op.add_column("call_log_head", sa.Column("run", sa.Text(), nullable=True))


def downgrade() -> None:
    """Undo."""
    op.drop_column("call_log_head", "run")
