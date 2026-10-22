"""The hold melody waits as long as the org says: `after_s`, and the runtime's melody kept as a row of its own.

Revision: 000009
Revises: 000008
Date: 2026-10-22
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "000009"
down_revision: str | None = "000008"
branch_labels: Sequence[str] | None = None
depends_on: Sequence[str] | None = None


# Raw, as the schema named it: the metadata's naming convention would rename a check it is handed.
DROP_THE_CHECK = "ALTER TABLE hold_audio DROP CONSTRAINT hold_audio_played_check"
ADD_THE_CHECK = "ALTER TABLE hold_audio ADD CONSTRAINT hold_audio_played_check CHECK (played IN ({played}))"


def upgrade() -> None:
    """The wait's column, and `default` among what a row may say it plays."""
    op.add_column("hold_audio", sa.Column("after_s", sa.Float(), nullable=True))
    op.execute(sa.text(DROP_THE_CHECK))
    op.execute(sa.text(ADD_THE_CHECK.format(played="'default', 'off', 'custom'")))


def downgrade() -> None:
    """Undo: a row that plays the runtime's melody goes, as having none meant it, and the column with it."""
    op.execute(sa.text("DELETE FROM hold_audio WHERE played = 'default'"))
    op.execute(sa.text(DROP_THE_CHECK))
    op.execute(sa.text(ADD_THE_CHECK.format(played="'off', 'custom'")))
    op.drop_column("hold_audio", "after_s")
