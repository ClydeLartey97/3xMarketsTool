#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
ROOT_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
cd "$ROOT_DIR"
mkdir -p "$ROOT_DIR/.local"
PYTHON_CACHE_DIR="$ROOT_DIR/.local/pycache"
mkdir -p "$PYTHON_CACHE_DIR"

if [ ! -x backend/.venv/bin/python ] || [ ! -x frontend/node_modules/.bin/next ]; then
  echo "Dependencies are missing; running one-time local setup..."
  bash scripts/bootstrap_local.sh
fi

BACKEND_PORT="${BACKEND_PORT:-8000}"
FRONTEND_PORT="${FRONTEND_PORT:-3000}"
DATABASE_URL="${DATABASE_URL:-sqlite:///$ROOT_DIR/.local/threex.dev.db}"
DEMO_MODE="${DEMO_MODE:-true}"
EIA_API_KEY="${EIA_API_KEY:-}"
RATE_LIMIT_ENABLED="${RATE_LIMIT_ENABLED:-false}"

stop_port() {
  port="$1"
  pids="$(lsof -tiTCP:"$port" -sTCP:LISTEN 2>/dev/null || true)"
  if [ -n "$pids" ]; then
    echo "Stopping stale process on port $port: $pids"
    kill $pids 2>/dev/null || true
    sleep 1
  fi
}

if [ "${STOP_EXISTING_LOCAL_SERVERS:-1}" = "1" ]; then
  stop_port "$BACKEND_PORT"
  stop_port "$FRONTEND_PORT"
fi

DATABASE_URL="$DATABASE_URL" \
DEMO_MODE="$DEMO_MODE" \
EIA_API_KEY="$EIA_API_KEY" \
RATE_LIMIT_ENABLED="$RATE_LIMIT_ENABLED" \
PYTHONPYCACHEPREFIX="$PYTHON_CACHE_DIR" \
PYTHONPATH=backend \
  backend/.venv/bin/python -m alembic -c alembic.ini upgrade head

(
  cd frontend
  API_INTERNAL_BASE_URL="${API_INTERNAL_BASE_URL:-http://127.0.0.1:${BACKEND_PORT}/api}" \
  NEXT_PUBLIC_API_BASE_URL="${NEXT_PUBLIC_API_BASE_URL:-/api/backend}" \
  NEXT_PUBLIC_WS_BASE_URL="${NEXT_PUBLIC_WS_BASE_URL:-ws://127.0.0.1:${BACKEND_PORT}}" \
  SERVER_AUTO_LOGIN="${SERVER_AUTO_LOGIN:-true}" \
  DEMO_USER_EMAIL="${DEMO_USER_EMAIL:-demo@3x.local}" \
  DEMO_USER_PASSWORD="${DEMO_USER_PASSWORD:-demo-password}" \
  NEXT_TELEMETRY_DISABLED=1 \
    npm run build
)

cleanup() {
  kill "$BACKEND_PID" "$FRONTEND_PID" 2>/dev/null || true
}
trap cleanup EXIT INT TERM

(
  cd backend
  DATABASE_URL="$DATABASE_URL" \
  DEMO_MODE="$DEMO_MODE" \
  EIA_API_KEY="$EIA_API_KEY" \
  RATE_LIMIT_ENABLED="$RATE_LIMIT_ENABLED" \
  PYTHONPATH=. \
    .venv/bin/python -m uvicorn app.main:app --host 127.0.0.1 --port "$BACKEND_PORT"
) &
BACKEND_PID=$!

(
  cd frontend
  API_INTERNAL_BASE_URL="${API_INTERNAL_BASE_URL:-http://127.0.0.1:${BACKEND_PORT}/api}" \
  NEXT_PUBLIC_API_BASE_URL="${NEXT_PUBLIC_API_BASE_URL:-/api/backend}" \
  NEXT_PUBLIC_WS_BASE_URL="${NEXT_PUBLIC_WS_BASE_URL:-ws://127.0.0.1:${BACKEND_PORT}}" \
  SERVER_AUTO_LOGIN="${SERVER_AUTO_LOGIN:-true}" \
  DEMO_USER_EMAIL="${DEMO_USER_EMAIL:-demo@3x.local}" \
  DEMO_USER_PASSWORD="${DEMO_USER_PASSWORD:-demo-password}" \
  NEXT_TELEMETRY_DISABLED=1 \
    ./node_modules/.bin/next start --hostname 127.0.0.1 -p "$FRONTEND_PORT"
) &
FRONTEND_PID=$!

echo "Backend:  http://127.0.0.1:${BACKEND_PORT}/api/health"
echo "Frontend: http://127.0.0.1:${FRONTEND_PORT}"
echo "Press Ctrl-C to stop both."

while kill -0 "$BACKEND_PID" 2>/dev/null && kill -0 "$FRONTEND_PID" 2>/dev/null; do
  sleep 2
done

wait "$BACKEND_PID" "$FRONTEND_PID"
