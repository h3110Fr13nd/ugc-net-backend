"""rename metadata columns to meta_data

Revision ID: 0002_rename_metadata
Revises: 0001_initial
Create Date: 2025-10-31 00:58:04.344350

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '0002_rename_metadata'
down_revision: Union[str, Sequence[str], None] = '0001_initial'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema - rename metadata columns to meta_data."""
    tables_with_metadata = [
        'users',
        'roles',
        'oauth_providers',
        'jwt_revocations',
        'refresh_tokens',
        'media',
        'quizzes',
        'questions',
        'question_parts',
        'options',
        'quiz_attempts',
        'question_attempts',
        'subjects',
        'chapters',
        'topics',
        'topic_associations',
        'entity_relationships',
    ]
    
    for table_name in tables_with_metadata:
        op.alter_column(table_name, 'metadata', new_column_name='meta_data')


def downgrade() -> None:
    """Downgrade schema - rename meta_data columns back to metadata."""
    tables_with_metadata = [
        'users',
        'roles',
        'oauth_providers',
        'jwt_revocations',
        'refresh_tokens',
        'media',
        'quizzes',
        'questions',
        'question_parts',
        'options',
        'quiz_attempts',
        'question_attempts',
        'subjects',
        'chapters',
        'topics',
        'topic_associations',
        'entity_relationships',
    ]
    
    for table_name in tables_with_metadata:
        op.alter_column(table_name, 'meta_data', new_column_name='metadata')
