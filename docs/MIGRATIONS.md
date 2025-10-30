# Database Migrations Guide

This document explains how to create, manage, and apply database schema changes using Alembic.

## Overview

- **Alembic** is the migration tool for SQLAlchemy
- **Models** are defined in `app/db/models.py`
- **Migrations** are stored in `alembic/versions/`
- **Sequential numbering** (0001, 0002, etc.) is used for easy tracking

## Quick Start

### 1. Make Model Changes

Edit `app/db/models.py` to add/modify tables or columns:

```python
class User(Base):
    __tablename__ = "users"
    id = Column(UUID(as_uuid=True), primary_key=True, ...)
    email = Column(String, unique=True, nullable=False)
    new_field = Column(String, nullable=True)  # NEW: add this field
```

### 2. Generate Migration (Local Dev)

If you have alembic installed locally:

```bash
source .venv/bin/activate
export DATABASE_URL="postgresql://postgres:postgres@127.0.0.1:5432/ugc"

# Auto-generate based on model changes
alembic revision --autogenerate -m "add new_field to users"
```

This creates a migration file like `alembic/versions/0003_add_new_field_to_users.py`

**Note:** The auto-generated migration attempts to detect changes. Always **review** the generated migration file before applying it.

### 3. Apply Migrations

**Option A: Using Make (Recommended for Docker)**

```bash
make up        # Start DB and web service
make migrate   # Run migrations inside web container
```

Or in one command:
```bash
make recreate  # Tear down, rebuild, and run migrations
```

**Option B: Manual (Local Dev)**

```bash
source .venv/bin/activate
export DATABASE_URL="postgresql://postgres:postgres@127.0.0.1:5432/ugc"
alembic upgrade head
```

**Option C: Inside Docker Container**

```bash
docker compose exec web bash
export DATABASE_URL="postgresql+asyncpg://postgres:postgres@db:5432/ugc"
alembic upgrade head
```

## Migration File Structure

A typical migration file looks like:

```python
"""add new_field to users

Revision ID: 0003_add_new_field_to_users
Revises: 0002_rename_metadata
Create Date: 2025-10-31 01:00:00.000000

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = '0003_add_new_field_to_users'
down_revision = '0002_rename_metadata'
branch_labels = None
depends_on = None

def upgrade() -> None:
    """Add new_field column to users table."""
    op.add_column('users', sa.Column('new_field', sa.String(), nullable=True))

def downgrade() -> None:
    """Remove new_field column from users table."""
    op.drop_column('users', 'new_field')
```

### Key Components

- **Revision ID**: Unique identifier (should match filename, kept under 32 chars)
- **down_revision**: Previous migration ID (creates the chain)
- **upgrade()**: SQL operations to apply changes
- **downgrade()**: Reverse operations (optional but recommended)

## Common Migration Operations

### Add a Column

```python
op.add_column('table_name', sa.Column('column_name', sa.String(), nullable=True))
```

### Drop a Column

```python
op.drop_column('table_name', 'column_name')
```

### Rename a Column

```python
op.alter_column('table_name', 'old_name', new_column_name='new_name')
```

### Modify Column Type

```python
op.alter_column('table_name', 'column_name', existing_type=sa.String(), type_=sa.Integer())
```

### Create an Index

```python
op.create_index('ix_table_column', 'table_name', ['column_name'])
```

### Drop an Index

```python
op.drop_index('ix_table_column', table_name='table_name')
```

### Create a New Table

```python
op.create_table(
    'new_table',
    sa.Column('id', sa.Integer(), primary_key=True),
    sa.Column('name', sa.String(), nullable=False),
)
```

### Drop a Table

```python
op.drop_table('table_name')
```

## Naming Conventions

To avoid issues, follow these conventions:

| Item | Format | Example |
|------|--------|---------|
| Migration file | `NNNN_short_description.py` | `0003_add_user_roles.py` |
| Revision ID | `NNNN_short_description` | `0003_add_user_roles` |
| Keep Revision ID under 32 characters (DB constraint) |
| Commit message | `migration: description` | `migration: add user_roles table` |

## Workflow: Making a Schema Change

### Step 1: Define the Change in Models

```bash
# Edit app/db/models.py
vim app/db/models.py
```

### Step 2: Generate Migration

```bash
source .venv/bin/activate

# Start DB if needed (docker compose up db -d)

export DATABASE_URL="postgresql://postgres:postgres@127.0.0.1:5432/ugc"
alembic revision --autogenerate -m "brief change description"
```

### Step 3: Review the Generated Migration

```bash
# Check the file that was created
cat alembic/versions/NNNN_*.py
```

Verify:
- Upgrade operations are correct
- Downgrade operations are present and correct
- No data loss will occur

### Step 4: Apply the Migration

**Locally:**
```bash
alembic upgrade head
```

**Or with Docker:**
```bash
make migrate
```

### Step 5: Test

```bash
# Run tests to ensure nothing broke
pytest tests/ -v

# Or test just database tests
pytest tests/test_database.py -v
```

### Step 6: Commit

```bash
git add app/db/models.py alembic/versions/NNNN_*.py
git commit -m "migration: your description"
```

## Troubleshooting

### Migration fails: "Can't proceed with --autogenerate"

**Cause:** Alembic can't find the database or models.

**Solution:**
```bash
# Ensure DATABASE_URL is set
export DATABASE_URL="postgresql://postgres:postgres@127.0.0.1:5432/ugc"

# Or start the DB first
docker compose up db -d && sleep 3
```

### "Column X already exists"

**Cause:** Migration was partially applied or run twice.

**Solution:**
```bash
# Check current migration status
alembic current

# View migration history
alembic history --verbose
```

### "Data too long for column"

**Cause:** Data type change or constraint is too strict.

**Solution:** Edit the migration to use a compatible type or add a pre-migration data cleanup step.

### Rollback a Migration

```bash
# Downgrade to previous migration
alembic downgrade -1

# Or downgrade to specific revision
alembic downgrade 0001_initial
```

## Best Practices

1. **Always review** auto-generated migrations before applying
2. **Write descriptive names** for migrations (max 32 chars for Revision ID)
3. **Include downgrade functions** to make rollbacks possible
4. **Test locally first** before committing
5. **One change per migration** - keep them focused and reviewable
6. **Never edit applied migrations** - create a new one to fix issues
7. **Commit migrations** with your code changes
8. **Use sequential IDs** (0001, 0002, etc.) for clarity

## Important: Alembic Configuration

The file `alembic.ini` contains:

```ini
[alembic]
script_location = alembic
file_template = %%(rev)s_%%(slug)s  # Ensures sequential numbering
sqlalchemy.url = postgresql://postgres:postgres@127.0.0.1:5432/ugc
```

The `file_template` setting ensures new migrations use the format `NNNN_description.py` instead of random UUIDs.

## Related Files

- `app/db/models.py` - Model definitions (source of truth)
- `app/db/base.py` - Database connection setup
- `alembic/env.py` - Alembic environment configuration
- `alembic.ini` - Alembic settings
- `Makefile` - Convenient targets for common tasks
