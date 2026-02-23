"""add pr fields to proposals

Revision ID: a1b2c3d4e5f6
Revises: 199f015d6e7d
Create Date: 2026-02-24 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'a1b2c3d4e5f6'
down_revision: Union[str, None] = '199f015d6e7d'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Add pr_url and pr_status columns to proposals table."""
    op.add_column('proposals', sa.Column('pr_url', sa.String(length=500), nullable=True))
    op.add_column('proposals', sa.Column('pr_status', sa.String(length=20), nullable=True))


def downgrade() -> None:
    """Remove pr_url and pr_status columns from proposals table."""
    op.drop_column('proposals', 'pr_status')
    op.drop_column('proposals', 'pr_url')
