"""call_facts keeps who played a simulated caller: the model of its lines, its voice's vendor and model, the voice.

Revision: 000006
Revises: 000005
Date: 2026-10-21
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "000006"
down_revision: str | None = "000005"
branch_labels: Sequence[str] | None = None
depends_on: Sequence[str] | None = None


def upgrade() -> None:
    """The columns, empty for every call before them: who played a caller was never kept."""
    op.add_column("call_facts", sa.Column("caller_llm", sa.Text(), nullable=True))
    op.add_column("call_facts", sa.Column("caller_tts", sa.Text(), nullable=True))
    op.add_column("call_facts", sa.Column("caller_voice", sa.Text(), nullable=True))


def downgrade() -> None:
    """Undo."""
    op.drop_column("call_facts", "caller_voice")
    op.drop_column("call_facts", "caller_tts")
    op.drop_column("call_facts", "caller_llm")
