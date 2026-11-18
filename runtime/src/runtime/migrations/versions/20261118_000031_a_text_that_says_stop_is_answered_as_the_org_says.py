"""A text that says STOP is answered as the org says.

Revision: 000031
Revises: 000030
Date: 2026-11-18

A contact who texts STOP is put on the org's do-not-call list and written to no more (2026-11-18).
What they are told is the carrier's own confirmation unless the org wrote one; what HELP answers is
the carrier's too unless the org wrote one; and an org that writes to people in another language
adds the words they stop with. Three settings of the org's policy, each empty until it is set.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "000031"
down_revision: str | None = "000030"
branch_labels: Sequence[str] | None = None
depends_on: Sequence[str] | None = None


def upgrade() -> None:
    """The three columns: no sentence of the org's own, and no word beside the standard ones."""
    op.add_column("org_policy", sa.Column("sms_stop_reply", sa.Text(), nullable=True))
    op.add_column("org_policy", sa.Column("sms_help_reply", sa.Text(), nullable=True))
    op.add_column(
        "org_policy",
        sa.Column("sms_stop_words", postgresql.ARRAY(sa.Text()), nullable=False, server_default="{}"),
    )


def downgrade() -> None:
    """Undo."""
    op.drop_column("org_policy", "sms_stop_words")
    op.drop_column("org_policy", "sms_help_reply")
    op.drop_column("org_policy", "sms_stop_reply")
