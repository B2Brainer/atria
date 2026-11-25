"""Initial schema: interaction_records.

Revision ID: 0001
Revises:
Create Date: 2026-11-24
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0001"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "interaction_records",
        sa.Column("id", sa.String, primary_key=True),
        sa.Column("cycle_id", sa.String, nullable=False),
        sa.Column("sequence", sa.Integer, nullable=False),
        sa.Column("payload", sa.String, nullable=False),
        sa.UniqueConstraint("cycle_id", "sequence", name="uq_interaction_records_cycle_sequence"),
    )
    op.create_index(
        "ix_interaction_records_cycle_id", "interaction_records", ["cycle_id"]
    )


def downgrade() -> None:
    op.drop_index("ix_interaction_records_cycle_id", table_name="interaction_records")
    op.drop_table("interaction_records")
