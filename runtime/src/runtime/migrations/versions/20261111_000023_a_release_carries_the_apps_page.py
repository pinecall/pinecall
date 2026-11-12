"""A release carries its app's page: the folder of it inside the sources, and the agent its visitors reach.

Revision: 000023
Revises: 000022
Date: 2026-11-11

An app may have a page of its own, built into a folder of its project and sent with the release. The
gateway serves it at the app's own name from the release that runs, and mints its visitors' tickets
for the agent the app named. Both are null for a release sent with no page, and for every one before.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "000023"
down_revision: str | None = "000022"
branch_labels: Sequence[str] | None = None
depends_on: Sequence[str] | None = None


def upgrade() -> None:
    """The two columns, empty for every release before them."""
    op.add_column("hosted_releases", sa.Column("page_dir", sa.Text(), nullable=True))
    op.add_column("hosted_releases", sa.Column("page_agent", sa.Text(), nullable=True))


def downgrade() -> None:
    """Undo."""
    op.drop_column("hosted_releases", "page_agent")
    op.drop_column("hosted_releases", "page_dir")
