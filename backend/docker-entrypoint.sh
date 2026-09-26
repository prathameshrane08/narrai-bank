#!/bin/sh
# Apply database migrations, optionally load demo data, then start the API.
set -e
alembic upgrade head
if [ "${NARRAI_SEED_DEMO:-0}" = "1" ]; then
  python -m seed
fi
exec uvicorn main:app --host 0.0.0.0 --port 8000
