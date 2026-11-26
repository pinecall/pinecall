"""call_facts.visitor: where a web call's visitor was, kept beside the call's fold.

Revision: 000037
Revises: 000036
Date: 2026-11-26

A web visitor's address, their browser's own name and the country the address is in are what the
gateway saw when it minted the call's ticket. No entry of the call says them: an app reads every
entry of a call it serves, and an SDK released before a field existed refuses the entry that carries
it. So they are a column of the facts row, written when the call opens and said on a list's row to
a reader who asks (`GET /v1/sessions?visitors=true`). NULL for every call before this release, and
for any call that is not a web visitor's.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB

revision: str = "000037"
down_revision: str | None = "000036"
branch_labels: Sequence[str] | None = None
depends_on: Sequence[str] | None = None


def upgrade() -> None:
    """Add the column."""
    op.add_column("call_facts", sa.Column("visitor", JSONB(), nullable=True))


def downgrade() -> None:
    """Drop it: where each visitor was goes with it."""
    op.drop_column("call_facts", "visitor")
