"""A sign-in dies a month after its last use.

Revision: 000028
Revises: 000027
Date: 2026-11-15

Every sign-in mints a key for its person, and none of them had a date: production held 314 live
ones for 17 people, 204 of them unused for a month and 81 never used at all, each still opening its
org. A person's key is kept while it is used from now on (`accounts.service.actor.A_SIGN_IN_IS_KEPT`):
minted with a date a month out, and given a month again by each use. The keys there are take the
date their last use gives them, their minting's when they were never used, so the ones nobody came
back to are expired by this and the rest go on. A server's token is not touched: it has the date it
was made with, or none. A revoked key stays as it is.
"""

from collections.abc import Sequence

from alembic import op

revision: str = "000028"
down_revision: str | None = "000027"
branch_labels: Sequence[str] | None = None
depends_on: Sequence[str] | None = None


def upgrade() -> None:
    """Every person's key that is not revoked takes the date of its last use, a month on."""
    op.execute(
        "UPDATE api_keys SET expires_at = COALESCE(last_used_at, created_at) + INTERVAL '30 days' "
        "WHERE subject IS NOT NULL AND revoked_at IS NULL"
    )


def downgrade() -> None:
    """A person's key has no date again, as before; what expired meanwhile opens again."""
    op.execute("UPDATE api_keys SET expires_at = NULL WHERE subject IS NOT NULL AND revoked_at IS NULL")
