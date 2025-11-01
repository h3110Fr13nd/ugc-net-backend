import os
import sys
from logging.config import fileConfig

from sqlalchemy import engine_from_config
from sqlalchemy import pool

from alembic import context

# this is the Alembic Config object, which provides
# access to the values within the .ini file in use.
config = context.config

# Interpret the config file for Python logging.
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

# Ensure project package is importable when alembic runs from the backend/ dir
# Insert the backend project root (parent of alembic/) into sys.path.
project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if project_root not in sys.path:
    sys.path.insert(0, project_root)

# add your model's MetaData object here for 'autogenerate' support
# Import the application's Base so autogenerate has access to MetaData.
try:
    # Prefer explicit import so failures are visible during development
    from app.db.models import Base
except Exception as exc:  # pragma: no cover - allow import errors during tooling
    # If import fails, surface a helpful message and set Base to None so alembic gives a clear error
    # (this will still cause autogenerate to fail but with visible exception info earlier in logs)
    Base = None
    # Optionally log to stderr for visibility during CI or local runs
    import logging

    logging.getLogger("alembic.env").exception("Failed to import app.db.models.Base: %s", exc)

target_metadata = getattr(Base, "metadata", None)


def _get_database_url() -> str:
    # prefer DATABASE_URL env var, fall back to alembic.ini sqlalchemy.url
    env_url = os.getenv("DATABASE_URL")
    if env_url:
        # Alembic's autogenerate does not work with async drivers; use sync URL for migrations
        return env_url.replace("+asyncpg", "")
    return config.get_main_option("sqlalchemy.url")


def run_migrations_offline() -> None:
    """Run migrations in 'offline' mode.

    This configures the context with just a URL
    and not an Engine, though an Engine is acceptable
    here as well.  By skipping the Engine creation
    we don't even need a DBAPI to be available.

    Calls to context.execute() here emit the given string to the
    script output.
    """
    url = _get_database_url()
    context.configure(url=url, target_metadata=target_metadata, literal_binds=True)

    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    """Run migrations in 'online' mode.

    In this scenario we need to create an Engine
    and associate a connection with the context.
    """
    configuration = config.get_section(config.config_ini_section)
    configuration["sqlalchemy.url"] = _get_database_url()
    connectable = engine_from_config(
        configuration,
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )

    with connectable.connect() as connection:
        context.configure(connection=connection, target_metadata=target_metadata)

        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
