"""add_explanation_column_to_questions

Revision ID: e32ab8063a90
Revises: 0004_add_quiz_version_id
Create Date: 2025-11-23 14:47:02.887492

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'e32ab8063a90'
down_revision: Union[str, Sequence[str], None] = '0004_add_quiz_version_id'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column('questions', sa.Column('explanation', sa.dialects.postgresql.JSONB(), nullable=True))


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_column('questions', 'explanation')
