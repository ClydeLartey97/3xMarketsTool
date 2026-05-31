#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
ROOT_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
cd "$ROOT_DIR"
mkdir -p "$ROOT_DIR/.local"
PYTHON_CACHE_DIR="$ROOT_DIR/.local/pycache"
mkdir -p "$PYTHON_CACHE_DIR"
LOCAL_DATABASE_URL="${DATABASE_URL:-sqlite:///$ROOT_DIR/.local/threex.dev.db}"

if [ "${RESET_DEPS:-0}" = "1" ]; then
  stamp="$(date +%s)"
  if [ -e backend/.venv ]; then
    mv backend/.venv "backend/.venv_broken_${stamp}"
  fi
  if [ -e frontend/node_modules ]; then
    mv frontend/node_modules "frontend/node_modules_broken_${stamp}"
  fi
fi

PYTHON_BIN="${PYTHON_BIN:-python3.12}"
if ! command -v "$PYTHON_BIN" >/dev/null 2>&1; then
  PYTHON_BIN="python3"
fi

if ! command -v "$PYTHON_BIN" >/dev/null 2>&1; then
  echo "Python 3.12+ is required, but python3.12/python3 was not found." >&2
  exit 1
fi

if [ ! -x backend/.venv/bin/python ]; then
  "$PYTHON_BIN" -m venv backend/.venv
fi

PYTHON="backend/.venv/bin/python"
"$PYTHON" -m pip install --upgrade pip setuptools wheel
"$PYTHON" -m pip install -r backend/requirements.txt

if [ "${INSTALL_OPTIONAL_AI:-0}" = "1" ]; then
  "$PYTHON" -m pip install -r backend/requirements-optional-ai.txt
fi

if [ ! -f .env ]; then
  {
    echo "DATABASE_URL=\"$LOCAL_DATABASE_URL\""
    echo "CORS_ORIGINS=[\"http://localhost:3000\"]"
    echo "API_INTERNAL_BASE_URL=http://127.0.0.1:8000/api"
    echo "NEXT_PUBLIC_API_BASE_URL=/api/backend"
    echo "NEXT_PUBLIC_WS_BASE_URL=ws://127.0.0.1:8000"
    echo "SERVER_AUTO_LOGIN=true"
    echo "LLM_SCORER_PROVIDER=heuristic"
    echo "JWT_SECRET=dev-local-change-me-dev-local-change-me"
    echo "DEMO_USER_EMAIL=demo@3x.local"
    echo "DEMO_USER_PASSWORD=demo-password"
    echo "DEMO_MODE=true"
    echo "EIA_API_KEY="
    echo "RATE_LIMIT_ENABLED=false"
  } > .env
fi

DATABASE_URL="$LOCAL_DATABASE_URL" \
DEMO_MODE=true \
EIA_API_KEY= \
RATE_LIMIT_ENABLED=false \
PYTHONPYCACHEPREFIX="$PYTHON_CACHE_DIR" \
PYTHONPATH=backend \
  "$PYTHON" -m alembic -c alembic.ini upgrade head

DATABASE_URL="$LOCAL_DATABASE_URL" \
DEMO_MODE=true \
EIA_API_KEY= \
RATE_LIMIT_ENABLED=false \
PYTHONPYCACHEPREFIX="$PYTHON_CACHE_DIR" \
PYTHONPATH=backend \
  "$PYTHON" - <<'PY'
from sqlalchemy import func, select

from app.db.session import SessionLocal
from app.ingestion.seeds import seed_database
from app.models import Market, PricePoint

with SessionLocal() as db:
    market_count = db.scalar(select(func.count()).select_from(Market)) or 0
    price_count = db.scalar(select(func.count()).select_from(PricePoint)) or 0
    if market_count == 0 or price_count < 48:
        seed_database(db)
PY

cd frontend
if [ -f package-lock.json ]; then
  npm ci
else
  npm install
fi

echo "Local setup complete."
