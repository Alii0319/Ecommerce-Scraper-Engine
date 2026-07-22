#!/bin/sh
set -e

DB_HOST="${DB_HOST:-db}"
DB_PORT="${DB_PORT:-5432}"
: "${DB_NAME:?DB_NAME is required}"
: "${DB_USER:?DB_USER is required}"
: "${DB_PASSWORD:?DB_PASSWORD is required}"

echo "Waiting for PostgreSQL at ${DB_HOST}:${DB_PORT}..."
for attempt in $(seq 1 30); do
  python - <<'PY'
import os
import sys
import psycopg2

try:
    conn = psycopg2.connect(
        dbname=os.environ['DB_NAME'],
        user=os.environ['DB_USER'],
        password=os.environ['DB_PASSWORD'],
        host=os.getenv('DB_HOST', 'db'),
        port=os.getenv('DB_PORT', '5432'),
    )
    conn.close()
    sys.exit(0)
except Exception as exc:
    print(f"Database connection attempt failed: {exc}", file=sys.stderr)
    sys.exit(1)
PY
  if [ $? -eq 0 ]; then
    break
  fi
  sleep 2
done

if [ $? -ne 0 ]; then
  echo "PostgreSQL did not become ready in time." >&2
  exit 1
fi

exec "$@"
