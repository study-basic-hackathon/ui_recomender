"""add job chaining columns

Revision ID: b2c3d4e5f6g7
Revises: a1b2c3d4e5f6
Create Date: 2026-02-28 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'b2c3d4e5f6g7'
down_revision: Union[str, None] = 'a1b2c3d4e5f6'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Add parent_job_id and parent_proposal_index columns to jobs table."""
    op.add_column('jobs', sa.Column('parent_job_id', sa.Uuid(), nullable=True))
    op.add_column('jobs', sa.Column('parent_proposal_index', sa.Integer(), nullable=True))
    op.create_foreign_key(
        'fk_jobs_parent_job_id',
        'jobs', 'jobs',
        ['parent_job_id'], ['id'],
        ondelete='SET NULL',
    )


def downgrade() -> None:
    """Remove parent_job_id and parent_proposal_index columns from jobs table."""
    op.drop_constraint('fk_jobs_parent_job_id', 'jobs', type_='foreignkey')
    op.drop_column('jobs', 'parent_proposal_index')
    op.drop_column('jobs', 'parent_job_id')
