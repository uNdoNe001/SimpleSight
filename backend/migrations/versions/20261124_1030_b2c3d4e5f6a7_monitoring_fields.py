"""monitoring fields on investigations (Phase 3 · SMPLSGHT-52)

Revision ID: b2c3d4e5f6a7
Revises: a1f2c3d4e5f6
Create Date: 2026-11-24 10:30:00.000000
"""
from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = 'b2c3d4e5f6a7'
down_revision: str | None = 'a1f2c3d4e5f6'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    with op.batch_alter_table('investigations', schema=None) as batch_op:
        batch_op.add_column(
            sa.Column(
                'monitoring_enabled', sa.Boolean(), nullable=False, server_default=sa.false()
            )
        )
        batch_op.add_column(sa.Column('monitoring_interval', sa.String(length=20), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table('investigations', schema=None) as batch_op:
        batch_op.drop_column('monitoring_interval')
        batch_op.drop_column('monitoring_enabled')
