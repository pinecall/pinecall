"""The live schema as the previous runtime left it: 110 numbered migrations, applied.

Revision: 000000
Revises: none
Date: 2026-10-15

This revision creates nothing. A database the previous runtime migrated already holds every
table `models/` declares; `alembic stamp 000000` marks it as here. A new database is made by
`pinecall-runtime migrate up`, which runs the previous runtime's SQL files once (kept under
`migrations/legacy/`) and then stamps this revision, so one path makes both.
"""

from collections.abc import Sequence

revision: str = "000000"
down_revision: str | None = None
branch_labels: Sequence[str] | None = None
depends_on: Sequence[str] | None = None


def upgrade() -> None:
    """Nothing: the schema is already there."""


def downgrade() -> None:
    """Nothing: there is nothing before the baseline."""
