"""eval_cases: a case a person wrote names no call, so `source_call` may be null.

Revision: 000012
Revises: 000011
Date: 2026-10-23

One column loosened. A case born at hang-up or kept from a call names the call; one a person wrote by
hand said '' because the column refused null. The rows that said '' say null now. The index on the
column stays, and an erasure by call never matched '' and never matches null.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "000012"
down_revision: str | None = "000011"
branch_labels: Sequence[str] | None = None
depends_on: Sequence[str] | None = None


def upgrade() -> None:
    """Let the column be null, and make the cases a person wrote say so."""
    op.execute(sa.text("ALTER TABLE eval_cases ALTER COLUMN source_call DROP NOT NULL"))
    op.execute(sa.text("UPDATE eval_cases SET source_call = NULL WHERE source_call = ''"))


def downgrade() -> None:
    """Undo: a case with no call says '' again, and the column refuses null."""
    op.execute(sa.text("UPDATE eval_cases SET source_call = '' WHERE source_call IS NULL"))
    op.execute(sa.text("ALTER TABLE eval_cases ALTER COLUMN source_call SET NOT NULL"))
