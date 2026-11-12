"""A base speaks a language: its chunks' words are indexed with that language's stemmer, one partial BM25 index each.

Revision: 000007
Revises: 000006
Date: 2026-10-21
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "000007"
down_revision: str | None = "000006"
branch_labels: Sequence[str] | None = None
depends_on: Sequence[str] | None = None

# knowledge/service/language.py names the same ones; `simple` stems nothing.
LANGUAGES = ("english", "spanish", "portuguese", "french", "german", "italian", "dutch", "simple")


def upgrade() -> None:
    """The column on the base and on each chunk, every row so far Spanish (what the one index was), then the indexes."""
    op.add_column("knowledge_bases", sa.Column("language", sa.Text(), nullable=False, server_default="spanish"))
    op.add_column("knowledge_chunks", sa.Column("language", sa.Text(), nullable=False, server_default="spanish"))
    op.alter_column("knowledge_bases", "language", server_default=None)
    op.alter_column("knowledge_chunks", "language", server_default=None)
    op.execute("DROP INDEX IF EXISTS knowledge_chunks_text_bm25")
    for language in LANGUAGES:
        op.execute(
            f"CREATE INDEX knowledge_chunks_{language}_bm25 ON knowledge_chunks USING bm25 (text) "
            f"WITH (text_config={language}) WHERE language = '{language}'"
        )


def downgrade() -> None:
    """Undo: the one Spanish index over every chunk, and the columns gone."""
    for language in LANGUAGES:
        op.execute(f"DROP INDEX IF EXISTS knowledge_chunks_{language}_bm25")
    op.execute(
        "CREATE INDEX knowledge_chunks_text_bm25 ON knowledge_chunks USING bm25 (text) WITH (text_config=spanish)"
    )
    op.drop_column("knowledge_chunks", "language")
    op.drop_column("knowledge_bases", "language")
