#!/usr/bin/env bash
# Wait for a TCP port to be available (host, port, timeout seconds)
set -euo pipefail

HOST=${1:-127.0.0.1}
PORT=${2:-5432}
TIMEOUT=${3:-60}

echo "Waiting for database at ${HOST}:${PORT} (timeout: ${TIMEOUT}s)"

i=0
while [ $i -lt ${TIMEOUT} ]; do
  if (echo > /dev/tcp/${HOST}/${PORT}) >/dev/null 2>&1; then
    echo "Database is available"
    exit 0
  fi
  i=$((i+1))
  sleep 1
done

echo "Timed out after ${TIMEOUT}s waiting for ${HOST}:${PORT}" >&2
exit 1
