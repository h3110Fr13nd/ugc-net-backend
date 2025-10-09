#!/usr/bin/env bash
# Run alembic migrations using DATABASE_URL from env
set -euo pipefail

if [ -z "${DATABASE_URL+x}" ]; then
  echo "ERROR: DATABASE_URL is not set. Example: export DATABASE_URL=postgresql+asyncpg://postgres:postgres@127.0.0.1:5432/ugc"
  exit 2
fi

echo "Using DATABASE_URL=${DATABASE_URL}"

# Ensure alembic is on PATH; prefer the alembic CLI
if command -v alembic >/dev/null 2>&1; then
  alembic upgrade head
else
  # Fall back to python -m alembic
  python -m alembic upgrade head
fi
