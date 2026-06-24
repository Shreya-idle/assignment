#!/bin/bash
set -e

echo "Waiting for PostgreSQL..."
while ! python -c "
import psycopg2, os, sys
try:
    psycopg2.connect(os.environ['DATABASE_URL'])
except Exception:
    sys.exit(1)
" 2>/dev/null; do
  sleep 2
done
echo "PostgreSQL is ready."

exec "$@"
