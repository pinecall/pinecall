"""quotas: how an org's simulations are shaped, the calls at once and the calls a comparison places.

Revision: 000019
Revises: 000018
Date: 2026-11-09

Ten simulated calls on the line at once and ten calls a comparison were the platform's own numbers,
the same for every org. Each is a column of the org's quotas row now, per env: null is still the
platform's own, so nothing changes for an org nobody gave more.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "000019"
down_revision: str | None = "000018"
branch_labels: Sequence[str] | None = None
depends_on: Sequence[str] | None = None


def upgrade() -> None:
    """The two columns, null for every org."""
    op.add_column("quotas", sa.Column("simulations_at_once", sa.Integer(), nullable=True))
    op.add_column("quotas", sa.Column("comparison_calls", sa.Integer(), nullable=True))


def downgrade() -> None:
    """Undo."""
    op.drop_column("quotas", "comparison_calls")
    op.drop_column("quotas", "simulations_at_once")
