"""A case kept before 0.10.1 holds its caller's lines as `input`; a golden is turns since: rewritten.

Revision: 000002
Revises: 000001
Date: 2026-10-16

Every case's golden is read as the wire's Golden, which refuses a field it does not know: a row
written by the runtime before goldens became turns answered every list of cases with a 500.
`input`, a list of the caller's lines, becomes `turns`, one `{say}` each, in order.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "000002"
down_revision: str | None = "000001"
branch_labels: Sequence[str] | None = None
depends_on: Sequence[str] | None = None

TURNS_FROM_INPUT = """
UPDATE eval_cases
SET golden = (golden - 'input') || jsonb_build_object(
    'turns',
    coalesce(
        (SELECT jsonb_agg(jsonb_build_object('say', line) ORDER BY ordinality)
         FROM jsonb_array_elements(golden->'input') WITH ORDINALITY AS lines(line, ordinality)),
        '[]'::jsonb
    )
)
WHERE golden ? 'input' AND NOT golden ? 'turns'
"""

INPUT_FROM_TURNS = """
UPDATE eval_cases
SET golden = (golden - 'turns') || jsonb_build_object(
    'input',
    coalesce(
        (SELECT jsonb_agg(turn->'say' ORDER BY ordinality)
         FROM jsonb_array_elements(golden->'turns') WITH ORDINALITY AS turns(turn, ordinality)
         WHERE turn ? 'say'),
        '[]'::jsonb
    )
)
WHERE golden ? 'turns' AND NOT golden ? 'input'
"""


def upgrade() -> None:
    """Apply."""
    op.execute(sa.text(TURNS_FROM_INPUT))


def downgrade() -> None:
    """Undo: the lines back as `input`; a turn that was an event, or what followed a line, is lost."""
    op.execute(sa.text(INPUT_FROM_TURNS))
