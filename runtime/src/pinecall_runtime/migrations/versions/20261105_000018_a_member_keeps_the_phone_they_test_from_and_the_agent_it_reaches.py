"""members keeps the phone a person tests from and the agent a call from it reaches.

Revision: 000018
Revises: 000017
Date: 2026-11-05

The phone a person said was theirs lived in the gateways' memory alone, said again by every
`pinecall start`: a person with no terminal, whose agent Studio holds, lost it at the gateway's
next start. It is a row's now, one phone to one person on the whole box, with the agent the box's
test line sends a call from it to (null: the one agent the org holds).
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "000018"
down_revision: str | None = "000017"
branch_labels: Sequence[str] | None = None
depends_on: Sequence[str] | None = None


def upgrade() -> None:
    """The two columns, null for everyone, and the index a ring is looked up by."""
    op.add_column("members", sa.Column("test_phone", sa.Text(), nullable=True))
    op.add_column("members", sa.Column("test_agent", sa.Text(), nullable=True))
    op.create_index(
        "members_by_test_phone",
        "members",
        ["test_phone"],
        unique=True,
        postgresql_where=sa.text("test_phone IS NOT NULL"),
    )


def downgrade() -> None:
    """Undo."""
    op.drop_index("members_by_test_phone", table_name="members")
    op.drop_column("members", "test_agent")
    op.drop_column("members", "test_phone")
