"""A person is one row, and a member is their seat in an org.

Revision: 000024
Revises: 000023
Date: 2026-11-12

A person had no row: they were an address repeated on one member row per org, and their password was
whichever of those rows was newest. `people` holds the address once, with its one password, when the
address was proven theirs and whether they run the box; `members.person` names it. No row-level
security: a person is of no org.

The backfill makes one person per address the members hold: the newest password among its rows (the
one that opened the account until now, so nobody is locked out), the earliest proof, the operator if
any row was one. Nothing is dropped: the three columns stay on `members` until the release that
reads them is gone.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "000024"
down_revision: str | None = "000023"
branch_labels: Sequence[str] | None = None
depends_on: Sequence[str] | None = None

# One person an address, whatever its case: the id is the package's own shape, `p_` and twelve hex digits.
PEOPLE = """
INSERT INTO people (id, email, password_hash, verified_at, operator, created_at)
SELECT 'p_' || substr(md5(random()::text || lower(email)), 1, 12),
       lower(email),
       (array_agg(password_hash ORDER BY created_at DESC) FILTER (WHERE password_hash IS NOT NULL))[1],
       min(verified_at),
       bool_or(operator),
       min(created_at)
FROM members
GROUP BY lower(email)
"""
SEATS = "UPDATE members SET person = people.id FROM people WHERE people.email = lower(members.email)"


def upgrade() -> None:
    """The table, the column that names it, and a person for every address there is."""
    op.create_table(
        "people",
        sa.Column("id", sa.Text(), nullable=False),
        sa.Column("email", sa.Text(), nullable=False),
        sa.Column("password_hash", sa.Text(), nullable=True),
        sa.Column("verified_at", sa.TIMESTAMP(timezone=True), nullable=True),
        sa.Column("operator", sa.Boolean(), nullable=False),
        sa.Column("created_at", sa.TIMESTAMP(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("email", name="people_email_key"),
    )
    op.add_column("members", sa.Column("person", sa.Text(), nullable=True))
    op.create_foreign_key("members_person_fkey", "members", "people", ["person"], ["id"])
    op.create_index("members_by_person", "members", ["person"])
    op.execute(sa.text(PEOPLE))
    op.execute(sa.text(SEATS))


def downgrade() -> None:
    """Undo: the members keep their own three columns, as they were."""
    op.drop_index("members_by_person", table_name="members")
    op.drop_constraint("members_person_fkey", "members", type_="foreignkey")
    op.drop_column("members", "person")
    op.drop_table("people")
