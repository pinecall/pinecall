"""routes.app: an address whose emails go to an app's flows as an event, and open no conversation.

Revision: 000041
Revises: 000040
Date: 2026-11-27

Every email to a routed address opened a conversation its agent answered. A notice a machine sends (a
portal's lead, an order, a form) is no conversation: an app's flow reads it, asks a model what it says, and
decides whom to write to. An address that names an app here is read the same way, and each email is that
app's event `mail.received`; NULL keeps the agent answering, as every route before this one does.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "000041"
down_revision: str | None = "000040"
branch_labels: Sequence[str] | None = None
depends_on: Sequence[str] | None = None


def upgrade() -> None:
    """An address may name the app whose flows read its emails."""
    op.add_column("routes", sa.Column("app", sa.Text(), nullable=True))


def downgrade() -> None:
    """Undo: every address is answered by its agent again."""
    op.drop_column("routes", "app")
