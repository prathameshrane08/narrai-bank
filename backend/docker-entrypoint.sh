#!/bin/sh
# Apply database migrations, optionally load demo data, then start the API.
set -e
if [ -z "${NARRAI_TOKEN_SECRET:-}" ]; then
  # Demo convenience only: a fresh random secret per start (sessions end on restart).
  # Production must set NARRAI_TOKEN_SECRET from a secret manager.
  echo "WARNING: NARRAI_TOKEN_SECRET not set; generating a temporary one" >&2
  NARRAI_TOKEN_SECRET=$(python -c "import secrets; print(secrets.token_urlsafe(48))")
  export NARRAI_TOKEN_SECRET
fi
alembic upgrade head
if [ "${NARRAI_SEED_DEMO:-0}" = "1" ]; then
  python -m seed
fi
exec uvicorn main:app --host 0.0.0.0 --port "${PORT:-8000}"
