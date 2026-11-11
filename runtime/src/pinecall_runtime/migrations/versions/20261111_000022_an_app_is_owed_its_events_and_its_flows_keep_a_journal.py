"""An app is owed its events, and its flows keep a journal.

Revision: 000022
Revises: 000021
Date: 2026-11-11

A voice app's own process runs its handlers and its flows, and it may be down, restarted or
deployed anew while a flow sleeps for a day. What it is owed is kept here: `app_events`, each until
the process says it heard it; `flow_runs`, one per start of a flow, with what it waits for (a clock,
an event, the call it placed); and `flow_steps`, the run's journal, which the process reads to go on
from where it was. All three are an org's, read and written under its own policy.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB

revision: str = "000022"
down_revision: str | None = "000021"
branch_labels: Sequence[str] | None = None
depends_on: Sequence[str] | None = None

SCOPED = "coalesce(current_setting('pinecall.org', true), '') = '' OR org = current_setting('pinecall.org', true)"
TABLES = ("app_events", "flow_runs", "flow_steps")


def upgrade() -> None:
    """Make the three tables, their indexes and their policies."""
    op.create_table(
        "app_events",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("org", sa.Text(), nullable=False),
        sa.Column("env", sa.Text(), nullable=False),
        sa.Column("app", sa.Text(), nullable=False),
        sa.Column("name", sa.Text(), nullable=False),
        sa.Column("data", JSONB(), nullable=False),
        sa.Column("sent_at", sa.TIMESTAMP(timezone=True), nullable=False),
        sa.Column("leased_until", sa.TIMESTAMP(timezone=True), nullable=True),
        sa.Column("heard_at", sa.TIMESTAMP(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["org"], ["orgs.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "app_events_owed", "app_events", ["org", "env", "app", "id"], postgresql_where=sa.text("heard_at IS NULL")
    )
    op.create_table(
        "flow_runs",
        sa.Column("id", sa.Text(), nullable=False),
        sa.Column("org", sa.Text(), nullable=False),
        sa.Column("env", sa.Text(), nullable=False),
        sa.Column("app", sa.Text(), nullable=False),
        sa.Column("flow", sa.Text(), nullable=False),
        sa.Column("key", sa.Text(), nullable=False),
        sa.Column("input", JSONB(), nullable=False),
        sa.Column("status", sa.Text(), nullable=False),
        sa.Column("wake_at", sa.TIMESTAMP(timezone=True), nullable=True),
        sa.Column("waits_for", sa.Text(), nullable=True),
        sa.Column("waits_match", JSONB(), nullable=True),
        sa.Column("call", sa.Text(), nullable=True),
        sa.Column("error", sa.Text(), nullable=True),
        sa.Column("leased_until", sa.TIMESTAMP(timezone=True), nullable=True),
        sa.Column("started_at", sa.TIMESTAMP(timezone=True), nullable=False),
        sa.Column("moved_at", sa.TIMESTAMP(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["org"], ["orgs.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("flow_runs_by_app", "flow_runs", ["org", "env", "app", "started_at"])
    op.create_index("flow_runs_started_once", "flow_runs", ["org", "env", "app", "flow", "key"], unique=True)
    op.create_index(
        "flow_runs_waiting",
        "flow_runs",
        ["status", "wake_at"],
        postgresql_where=sa.text("status IN ('sleeping', 'waiting', 'calling')"),
    )
    op.create_table(
        "flow_steps",
        sa.Column("run", sa.Text(), nullable=False),
        sa.Column("seq", sa.Integer(), nullable=False),
        sa.Column("org", sa.Text(), nullable=False),
        sa.Column("kind", sa.Text(), nullable=False),
        sa.Column("asked", JSONB(), nullable=False),
        sa.Column("result", JSONB(), nullable=True),
        sa.Column("at", sa.TIMESTAMP(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["org"], ["orgs.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["run"], ["flow_runs.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("run", "seq"),
    )
    for table in TABLES:
        op.execute(sa.text(f"ALTER TABLE {table} ENABLE ROW LEVEL SECURITY"))
        op.execute(sa.text(f"CREATE POLICY org_scoped ON {table} USING ({SCOPED}) WITH CHECK ({SCOPED})"))


def downgrade() -> None:
    """Undo: the events owed and every run go with the tables."""
    for table in reversed(TABLES):
        op.drop_table(table)
