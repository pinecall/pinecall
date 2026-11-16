"""A call's head counts the workers that took it up.

Revision: 000029
Revises: 000028
Date: 2026-11-16

A call whose worker goes away is taken up by another (2026-11-16), and the worker it was taken from
may still be alive: lost to its room for a while, or cut from its gateway. Its seal must be refused,
or it ends a call another worker runs. The count of take-ups was kept in the memory of the gateway
that answered the take-up, and production runs two behind a Service that sends each request to
either: on 2026-11-16 a call's stream was cut on one gateway and its take-up was answered by the
other. The head says it now, so every gateway reads the same count, and a take-up is one statement
that moves it from the value its asker read: two workers offered one call cannot both take it.
Every call there is was taken up by nobody.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "000029"
down_revision: str | None = "000028"
branch_labels: Sequence[str] | None = None
depends_on: Sequence[str] | None = None


def upgrade() -> None:
    """The column, zero for every call there is."""
    op.add_column("call_log_head", sa.Column("taken_up", sa.Integer(), nullable=False, server_default="0"))


def downgrade() -> None:
    """Undo."""
    op.drop_column("call_log_head", "taken_up")
