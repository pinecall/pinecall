"""An agent answers email.

Revision: 000032
Revises: 000031
Date: 2026-11-18

An org brings a mailbox of its own (IMAP to read it, SMTP to answer from it) as an account of kind
`email`, and an address of it is routed to an agent on the channel `email`. Two tables: where the
reading of each inbox stands (its newest message read, and which gateway reads it now), and the HTML
the org sets its agents' emails in.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "000032"
down_revision: str | None = "000031"
branch_labels: Sequence[str] | None = None
depends_on: Sequence[str] | None = None


# The kinds an account may be: the database says it as well as the code.
DROP_THE_CHECK = "ALTER TABLE carriers DROP CONSTRAINT carriers_kind_check"
ADD_THE_CHECK = "ALTER TABLE carriers ADD CONSTRAINT carriers_kind_check CHECK (kind = ANY (ARRAY[{kinds}]))"


def _kinds(*kinds: str) -> str:
    return ", ".join(f"'{kind}'::text" for kind in kinds)


def upgrade() -> None:
    """A mailbox is a kind of account, and the two tables, empty: nothing is read until an address is routed."""
    op.execute(DROP_THE_CHECK)
    op.execute(ADD_THE_CHECK.format(kinds=_kinds("twilio", "sip", "whatsapp", "email")))
    op.create_table(
        "email_inboxes",
        sa.Column("org", sa.Text(), nullable=False),
        sa.Column("account", sa.Text(), nullable=False),
        sa.Column("uid_validity", sa.BigInteger(), nullable=True),
        sa.Column("last_uid", sa.BigInteger(), nullable=True),
        sa.Column("leased_by", sa.Text(), nullable=True),
        sa.Column("leased_until", sa.TIMESTAMP(timezone=True), nullable=True),
        sa.Column("read_at", sa.TIMESTAMP(timezone=True), nullable=True),
        sa.Column("last_error", sa.Text(), nullable=True),
        sa.ForeignKeyConstraint(
            ["org", "account"],
            ["carriers.org", "carriers.account"],
            name="email_inboxes_org_account_fkey",
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("org", "account", name="email_inboxes_pkey"),
    )
    op.create_table(
        "email_layouts",
        sa.Column("org", sa.Text(), nullable=False),
        sa.Column("html", sa.Text(), nullable=False),
        sa.Column("set_by", sa.Text(), nullable=True),
        sa.Column("set_at", sa.TIMESTAMP(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["org"], ["orgs.id"], name="email_layouts_org_fkey", ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("org", name="email_layouts_pkey"),
    )


def downgrade() -> None:
    """Undo: the mailboxes forgotten first, which no older release reads."""
    op.drop_table("email_layouts")
    op.drop_table("email_inboxes")
    op.execute("DELETE FROM routes WHERE channel = 'email'")
    op.execute("DELETE FROM carriers WHERE kind = 'email'")
    op.execute(DROP_THE_CHECK)
    op.execute(ADD_THE_CHECK.format(kinds=_kinds("twilio", "sip", "whatsapp")))
