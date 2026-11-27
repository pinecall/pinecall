"""call_facts.in_room: a call lives in a room; spoken is somebody talked on it.

Revision: 000039
Revises: 000038
Date: 2026-11-27

Until now `spoken` meant a room opened for the call, and every web visit opens one: a website's chat,
whose caller joins on a `chat` seat with no microphone, was listed as a web call, filtered under "Web
call", and drawn as a call among a contact's messages. `in_room` keeps what `spoken` meant, for the
reaper, which ends a quiet call in a room and takes a written one up again after a restart; `spoken`
is now a phone call, or a web visit whose caller joined to talk. Both are folded from the log, and so
is what this migration writes for the calls before it.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "000039"
down_revision: str | None = "000038"
branch_labels: Sequence[str] | None = None
depends_on: Sequence[str] | None = None

# A caller who joined a room on any seat but a chat's talked on it (`wire/room.py`, SCOPE_ATTRIBUTE).
SPOKEN_AGAIN = """
update call_facts f
set spoken = coalesce(f.channel, '') = 'phone' or exists (
    select 1 from call_log joined
    where joined.log = f.call
      and joined.type = 'participant.joined'
      and joined.data ->> 'kind' = 'caller'
      and coalesce(joined.data -> 'attributes' ->> 'pinecall.scope', '') <> 'chat'
)
where f.in_room
"""


def upgrade() -> None:
    """Every call that was spoken is in a room; spoken again, from who joined it."""
    op.add_column("call_facts", sa.Column("in_room", sa.Boolean(), nullable=False, server_default=sa.false()))
    op.execute("update call_facts set in_room = true where spoken")
    op.execute(SPOKEN_AGAIN)
    op.alter_column("call_facts", "in_room", server_default=None)


def downgrade() -> None:
    """Undo: a call in a room is spoken again, as the release before reads it."""
    op.execute("update call_facts set spoken = true where in_room")
    op.drop_column("call_facts", "in_room")
