"""exposure snapshots (Phase 5 · SMPLSGHT-65)

Revision ID: d4e5f6a7b8c9
Revises: c3d4e5f6a7b8
Create Date: 2026-11-25 12:00:00.000000
"""
from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = 'd4e5f6a7b8c9'
down_revision: str | None = 'c3d4e5f6a7b8'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        'exposure_snapshots',
        sa.Column('id', sa.String(length=36), nullable=False),
        sa.Column('tenant_id', sa.String(length=36), nullable=False),
        sa.Column('investigation_id', sa.String(length=36), nullable=False),
        sa.Column('organization_id', sa.String(length=36), nullable=False),
        sa.Column('score', sa.Integer(), nullable=False),
        sa.Column('grade', sa.String(length=2), nullable=False),
        sa.Column('label', sa.String(length=20), nullable=False),
        sa.Column('scored_findings', sa.Integer(), nullable=False),
        sa.Column('run_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(['tenant_id'], ['tenants.id'], ),
        sa.ForeignKeyConstraint(['investigation_id'], ['investigations.id'], ),
        sa.ForeignKeyConstraint(['organization_id'], ['organizations.id'], ),
        sa.PrimaryKeyConstraint('id'),
    )
    with op.batch_alter_table('exposure_snapshots', schema=None) as batch_op:
        batch_op.create_index(
            batch_op.f('ix_exposure_snapshots_tenant_id'), ['tenant_id'], unique=False
        )
        batch_op.create_index(
            batch_op.f('ix_exposure_snapshots_investigation_id'),
            ['investigation_id'], unique=False,
        )
        batch_op.create_index(
            batch_op.f('ix_exposure_snapshots_organization_id'),
            ['organization_id'], unique=False,
        )
        batch_op.create_index(
            batch_op.f('ix_exposure_snapshots_run_at'), ['run_at'], unique=False
        )


def downgrade() -> None:
    with op.batch_alter_table('exposure_snapshots', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_exposure_snapshots_run_at'))
        batch_op.drop_index(batch_op.f('ix_exposure_snapshots_organization_id'))
        batch_op.drop_index(batch_op.f('ix_exposure_snapshots_investigation_id'))
        batch_op.drop_index(batch_op.f('ix_exposure_snapshots_tenant_id'))
    op.drop_table('exposure_snapshots')
