"""A person writes a case by hand: `person` among where a case may come from.

Revision: 000010
Revises: 000009
Date: 2026-10-23
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "000010"
down_revision: str | None = "000009"
branch_labels: Sequence[str] | None = None
depends_on: Sequence[str] | None = None


# Raw, as the schema named it: the check was written inline with its column (0108), so Postgres named it.
DROP_THE_CHECK = "ALTER TABLE eval_cases DROP CONSTRAINT eval_cases_source_check"
ADD_THE_CHECK = "ALTER TABLE eval_cases ADD CONSTRAINT eval_cases_source_check CHECK (source IN ({sources}))"


def upgrade() -> None:
    """`person` among a case's sources."""
    op.execute(sa.text(DROP_THE_CHECK))
    op.execute(sa.text(ADD_THE_CHECK.format(sources="'call', 'simulation', 'person'")))


def downgrade() -> None:
    """Undo: the cases people wrote go, since no call or simulation made them."""
    op.execute(sa.text("DELETE FROM eval_cases WHERE source = 'person'"))
    op.execute(sa.text(DROP_THE_CHECK))
    op.execute(sa.text(ADD_THE_CHECK.format(sources="'call', 'simulation'")))
