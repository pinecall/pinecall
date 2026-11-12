"""hold_audio: the hash of the clip as it was uploaded, before conversion.

Revision: 000016
Revises: 000015
Date: 2026-10-31

A class that declares its hold melody names the file it ships by its sha256; the gateway keeps
that hash beside the converted clip's, so the class's process knows whether its file is already
there and the upload door knows the file is the class's own. Null for every clip uploaded before.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "000016"
down_revision: str | None = "000015"
branch_labels: Sequence[str] | None = None
depends_on: Sequence[str] | None = None


def upgrade() -> None:
    """Add the column."""
    op.add_column("hold_audio", sa.Column("source_sha256", sa.Text(), nullable=True))


def downgrade() -> None:
    """Drop the column."""
    op.drop_column("hold_audio", "source_sha256")
