"""add quiz_version_id to quiz_attempts

Revision ID: 0004_add_quiz_version_id
Revises: 0003_taxonomical_models
Create Date: 2025-11-02 00:00:00.000000
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision = '0004_add_quiz_version_id'
down_revision = '0003'
branch_labels = None
depends_on = None


def upgrade():
    # Add nullable quiz_version_id column and FK to quiz_versions.id
    op.add_column('quiz_attempts', sa.Column('quiz_version_id', postgresql.UUID(as_uuid=True), nullable=True))
    op.create_foreign_key('fk_quiz_attempts_quiz_version', 'quiz_attempts', 'quiz_versions', ['quiz_version_id'], ['id'])


def downgrade():
    op.drop_constraint('fk_quiz_attempts_quiz_version', 'quiz_attempts', type_='foreignkey')
    op.drop_column('quiz_attempts', 'quiz_version_id')
