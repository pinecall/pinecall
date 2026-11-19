"""An org may send its emails as text alone.

Revision: 000033
Revises: 000032
Date: 2026-11-19

An org that wants no template had its agents' emails set in a plain HTML page all the same. It may
now say its emails go as text alone: one `text/plain` part, no HTML beside it. The flag lives on the
org's layout row, false for every row there is.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "000033"
down_revision: str | None = "000032"
branch_labels: Sequence[str] | None = None
depends_on: Sequence[str] | None = None


def upgrade() -> None:
    """The flag, false for the layouts kept so far: they are HTML, as they were."""
    op.add_column("email_layouts", sa.Column("text_only", sa.Boolean(), server_default=sa.false(), nullable=False))


def downgrade() -> None:
    """Undo: an org that sent text alone has no layout of its own again, which is the plain HTML one."""
    op.execute("DELETE FROM email_layouts WHERE text_only")
    op.drop_column("email_layouts", "text_only")
