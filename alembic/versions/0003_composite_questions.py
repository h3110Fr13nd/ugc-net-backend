"""Add relationships for composite questions

Revision ID: 0003_composite_questions
Revises: 0002_rename_metadata
Create Date: 2025-10-31

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '0003_composite_questions'
down_revision = '0002_rename_metadata'
branch_labels = None
depends_on = None


def upgrade() -> None:
    # No schema changes needed - just adding relationships in SQLAlchemy models
    # The tables already exist from initial migration
    pass


def downgrade() -> None:
    # No changes to revert
    pass
