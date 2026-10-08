#!/bin/sh
set -e

# `alembic.ini` and the first migration (0001_users) landed in slice 1a
# (feature/auth-foundation); this now always brings the schema to head
# before the API process starts, safe for the single-replica compose stack.
alembic upgrade head

exec uvicorn app.main:app --host 0.0.0.0 --port 8000
