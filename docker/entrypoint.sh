#!/bin/sh
set -e

# Placeholder: `alembic.ini` lands in slice 1a (feature/auth-foundation) with
# the first migration. Until then, this is a no-op so the image boots clean.
if [ -f /app/alembic.ini ]; then
    alembic upgrade head
fi

exec uvicorn app.main:app --host 0.0.0.0 --port 8000
