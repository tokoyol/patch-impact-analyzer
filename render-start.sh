#!/usr/bin/env sh
set -eu

PORT="${PORT:-10000}"

# Ensure schema is up to date before serving requests.
cd /workspace/backend
alembic upgrade head

# Start FastAPI on localhost; Next.js proxies /api/* to this port.
cd /workspace/backend
uvicorn app.main:app --host 127.0.0.1 --port 8000 &
BACKEND_PID=$!

cleanup() {
  kill "$BACKEND_PID" 2>/dev/null || true
}

trap cleanup INT TERM EXIT

cd /workspace/frontend
exec npm run start -- --hostname 0.0.0.0 --port "$PORT"
