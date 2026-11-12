"""An alert says when it was posted to the org's webhooks.

Revision: 000025
Revises: 000024
Date: 2026-11-12

An alert was posted as it was raised, inside the transaction of whatever raised it. It is a row
first now, posted afterwards by a loop: `posted_at` is null while it waits. The release before this
one knows nothing of the column and posts as it raises, so the column defaults to now: a row that
release writes is born posted, as every row kept until today is, and no gateway posts it again.
This package writes null by name. The default goes when that release does.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "000025"
down_revision: str | None = "000024"
branch_labels: Sequence[str] | None = None
depends_on: Sequence[str] | None = None


def upgrade() -> None:
    """The column, every alert there is posted already, and the index the posting loop reads."""
    posted_at = sa.Column("posted_at", sa.TIMESTAMP(timezone=True), nullable=True, server_default=sa.func.now())
    op.add_column("alerts", posted_at)
    op.create_index("alerts_unposted", "alerts", ["at"], postgresql_where=sa.text("posted_at IS NULL"))


def downgrade() -> None:
    """Undo."""
    op.drop_index("alerts_unposted", table_name="alerts")
    op.drop_column("alerts", "posted_at")
