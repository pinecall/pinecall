"""A hosted app is code the runner starts, or a Studio agent the gateway holds: `kind` says which.

Revision: 000003
Revises: 000002
Date: 2026-10-19

A Studio agent is built in the console and counts as one hosted app: the same row, the same quota,
the same metered time. Its releases are its definition as JSON, and no process runs it, so it has
no token: the key's two columns stay empty for it.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "000003"
down_revision: str | None = "000002"
branch_labels: Sequence[str] | None = None
depends_on: Sequence[str] | None = None

ADD_THE_CHECK = "ALTER TABLE hosted_apps ADD CONSTRAINT hosted_apps_kind_check CHECK (kind IN ('code', 'studio'))"


def upgrade() -> None:
    """Apply."""
    op.add_column("hosted_apps", sa.Column("kind", sa.Text(), nullable=False, server_default="code"))
    op.execute(sa.text(ADD_THE_CHECK))


def downgrade() -> None:
    """Undo: every Studio agent goes with the column."""
    op.execute(sa.text("DELETE FROM hosted_apps WHERE kind = 'studio'"))
    op.drop_column("hosted_apps", "kind")
