"""A Facebook Page is an account: its Messenger, and the Instagram account linked to it.

Revision: 000038
Revises: 000037
Date: 2026-11-27

An org brings a Page of its own at Meta (its id, its access token, the secret of the org's own Meta app,
and the Instagram account linked to the Page) as an account of kind `messenger`; the Page's id is routed
to an agent on the channel `messenger`, and the Instagram account's on `instagram`. Both are Meta's
Messenger Platform, signed and delivered as WhatsApp is. No table: a Page is read as it writes.
"""

from collections.abc import Sequence

from alembic import op

revision: str = "000038"
down_revision: str | None = "000037"
branch_labels: Sequence[str] | None = None
depends_on: Sequence[str] | None = None


# The kinds an account may be: the database says it as well as the code.
DROP_THE_CHECK = "ALTER TABLE carriers DROP CONSTRAINT carriers_kind_check"
ADD_THE_CHECK = "ALTER TABLE carriers ADD CONSTRAINT carriers_kind_check CHECK (kind = ANY (ARRAY[{kinds}]))"


def _kinds(*kinds: str) -> str:
    return ", ".join(f"'{kind}'::text" for kind in kinds)


def upgrade() -> None:
    """A Page is a kind of account."""
    op.execute(DROP_THE_CHECK)
    op.execute(ADD_THE_CHECK.format(kinds=_kinds("twilio", "sip", "whatsapp", "email", "messenger")))


def downgrade() -> None:
    """Undo: the Pages forgotten first, with their routes, which no older release reads."""
    op.execute("DELETE FROM routes WHERE channel IN ('messenger', 'instagram')")
    op.execute("DELETE FROM carriers WHERE kind = 'messenger'")
    op.execute(DROP_THE_CHECK)
    op.execute(ADD_THE_CHECK.format(kinds=_kinds("twilio", "sip", "whatsapp", "email")))
