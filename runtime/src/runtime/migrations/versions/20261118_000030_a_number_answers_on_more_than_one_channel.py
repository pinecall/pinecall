"""A number answers on more than one channel.

Revision: 000030
Revises: 000029
Date: 2026-11-18

A number was one row: an agent, an env and ONE channel. A number that answers the phone could not
also answer WhatsApp, and importing it as WhatsApp replaced its phone route (a tenant asked for both
on its main line, 2026-11-18). A route is a number on a channel now: the key gains the channel, and
the index that said a number is held once says it is held once a channel. That one org holds a
number, whatever its channels, is said where a number is imported (`is_held_elsewhere`), as it was.
Every row there is stays as it is: no number has two.

The release before reads a number's first row and writes by org and number, so a rollback is safe
until a number has two channels: importing that number again on it would then find two rows.
"""

from collections.abc import Sequence

from alembic import op

revision: str = "000030"
down_revision: str | None = "000029"
branch_labels: Sequence[str] | None = None
depends_on: Sequence[str] | None = None


def upgrade() -> None:
    """The key by channel, and one row a number a channel across the box."""
    op.drop_constraint("routes_pkey", "routes", type_="primary")
    op.create_primary_key("routes_pkey", "routes", ["org", "number", "channel"])
    op.drop_index("routes_number_held_once", table_name="routes")
    op.create_index("routes_number_held_once_a_channel", "routes", ["number", "channel"], unique=True)


# Refused by Postgres while a number has two channels: one of them is let go first.
def downgrade() -> None:
    """Undo."""
    op.drop_index("routes_number_held_once_a_channel", table_name="routes")
    op.create_index("routes_number_held_once", "routes", ["number"], unique=True)
    op.drop_constraint("routes_pkey", "routes", type_="primary")
    op.create_primary_key("routes_pkey", "routes", ["org", "number"])
