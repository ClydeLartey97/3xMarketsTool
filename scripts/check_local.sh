#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
ROOT_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
cd "$ROOT_DIR"
mkdir -p "$ROOT_DIR/.local"
PYTHON_CACHE_DIR="$ROOT_DIR/.local/pycache"
mkdir -p "$PYTHON_CACHE_DIR"
LOCAL_DATABASE_URL="${DATABASE_URL:-sqlite:///$ROOT_DIR/.local/threex.dev.db}"

if [ ! -x backend/.venv/bin/python ] || [ ! -x frontend/node_modules/.bin/eslint ]; then
  echo "Dependencies are missing; running one-time local setup..."
  sh scripts/bootstrap_local.sh
fi

DATABASE_URL="$LOCAL_DATABASE_URL" \
DEMO_MODE=true \
EIA_API_KEY= \
RATE_LIMIT_ENABLED=false \
PYTHONPYCACHEPREFIX="$PYTHON_CACHE_DIR" \
PYTHONPATH=backend \
  backend/.venv/bin/python -m alembic -c alembic.ini upgrade head

PYTHONPYCACHEPREFIX="$PYTHON_CACHE_DIR" \
PYTHONPATH=backend \
  backend/.venv/bin/python -m py_compile \
    backend/app/main.py \
    backend/app/api/routes.py \
    backend/app/services/deep_hedger.py \
    backend/app/ingestion/real_data.py

DATABASE_URL="$LOCAL_DATABASE_URL" \
DEMO_MODE=true \
EIA_API_KEY= \
RATE_LIMIT_ENABLED=false \
PYTHONPYCACHEPREFIX="$PYTHON_CACHE_DIR" \
PYTHONPATH=backend \
  backend/.venv/bin/python -c "from app.main import app; print(f'backend import ok: {app.title}')"

cd frontend
export NEXT_TELEMETRY_DISABLED=1
npm run lint:nocache
npm run build
