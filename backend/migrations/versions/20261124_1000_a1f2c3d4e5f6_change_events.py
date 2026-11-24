"""change events (Phase 3 · SMPLSGHT-50)

Revision ID: a1f2c3d4e5f6
Revises: c38d50ce38a5
Create Date: 2026-11-24 10:00:00.000000
"""
from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = 'a1f2c3d4e5f6'
down_revision: str | None = 'c38d50ce38a5'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        'change_events',
        sa.Column('id', sa.String(length=36), nullable=False),
        sa.Column('tenant_id', sa.String(length=36), nullable=False),
        sa.Column('investigation_id', sa.String(length=36), nullable=False),
        sa.Column('organization_id', sa.String(length=36), nullable=False),
        sa.Column('change_type', sa.String(length=40), nullable=False),
        sa.Column('entity_type', sa.String(length=20), nullable=False),
        sa.Column('entity_key', sa.String(length=512), nullable=False),
        sa.Column('title', sa.String(length=512), nullable=False),
        sa.Column('severity', sa.String(length=20), nullable=True),
        sa.Column('detail', sa.JSON(), nullable=False),
        sa.Column('run_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('acknowledged_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(['investigation_id'], ['investigations.id'], ),
        sa.ForeignKeyConstraint(['organization_id'], ['organizations.id'], ),
        sa.ForeignKeyConstraint(['tenant_id'], ['tenants.id'], ),
        sa.PrimaryKeyConstraint('id'),
    )
    with op.batch_alter_table('change_events', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_change_events_tenant_id'), ['tenant_id'], unique=False)
        batch_op.create_index(
            batch_op.f('ix_change_events_investigation_id'), ['investigation_id'], unique=False
        )
        batch_op.create_index(
            batch_op.f('ix_change_events_organization_id'), ['organization_id'], unique=False
        )
        batch_op.create_index(
            batch_op.f('ix_change_events_change_type'), ['change_type'], unique=False
        )
        batch_op.create_index(
            batch_op.f('ix_change_events_entity_key'), ['entity_key'], unique=False
        )
        batch_op.create_index(batch_op.f('ix_change_events_run_at'), ['run_at'], unique=False)


def downgrade() -> None:
    with op.batch_alter_table('change_events', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_change_events_run_at'))
        batch_op.drop_index(batch_op.f('ix_change_events_entity_key'))
        batch_op.drop_index(batch_op.f('ix_change_events_change_type'))
        batch_op.drop_index(batch_op.f('ix_change_events_organization_id'))
        batch_op.drop_index(batch_op.f('ix_change_events_investigation_id'))
        batch_op.drop_index(batch_op.f('ix_change_events_tenant_id'))
    op.drop_table('change_events')
