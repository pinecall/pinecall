"""call_facts keeps what a simulated caller's own model and voice cost, beside the agent's side.

Revision: 000005
Revises: 000004
Date: 2026-10-20
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "000005"
down_revision: str | None = "000004"
branch_labels: Sequence[str] | None = None
depends_on: Sequence[str] | None = None


def upgrade() -> None:
    """The column, nothing for every call before it: a caller's cost was never kept."""
    op.add_column(
        "call_facts",
        sa.Column("caller_cost_usd", sa.Float(), nullable=False, server_default=sa.text("0")),
    )


def downgrade() -> None:
    """Undo."""
    op.drop_column("call_facts", "caller_cost_usd")
