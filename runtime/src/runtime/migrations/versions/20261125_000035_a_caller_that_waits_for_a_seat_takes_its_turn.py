"""seat_turns: the callers that wait for a seat of a fleet, and the ones that took theirs.

Revision: 000035
Revises: 000034
Date: 2026-11-25

A simulated caller that found no seat asked again every two seconds, and the seat that freed went to
whichever asked first: one org's comparison of sixty calls held every seat a waiting caller may take,
and another org's call waited behind all of them. The line is kept now, a row a caller from its first
ask until its call ends, with the org it is of and when it took its seat, so a seat that frees goes
to the org that holds the fewest. No row-level security: the line is read across orgs on purpose. It
starts empty, and a caller of the release before this one asks as it did and is seated in no turn.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "000035"
down_revision: str | None = "000034"
branch_labels: Sequence[str] | None = None
depends_on: Sequence[str] | None = None


def upgrade() -> None:
    """Make the table and its index."""
    op.create_table(
        "seat_turns",
        sa.Column("room", sa.Text(), nullable=False),
        sa.Column("fleet", sa.Text(), nullable=False),
        sa.Column("org", sa.Text(), nullable=False),
        sa.Column("asked_at", sa.Float(), nullable=False),
        sa.Column("heard_at", sa.Float(), nullable=False),
        sa.Column("seated_at", sa.Float(), nullable=True),
        sa.PrimaryKeyConstraint("room", name="seat_turns_pkey"),
    )
    op.create_index("seat_turns_by_fleet", "seat_turns", ["fleet"])


def downgrade() -> None:
    """Undo: the line goes with the table, and seats go to whoever asks first again."""
    op.drop_index("seat_turns_by_fleet", table_name="seat_turns")
    op.drop_table("seat_turns")
