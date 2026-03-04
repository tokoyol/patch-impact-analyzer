#!/usr/bin/env sh
set -eu

PORT="${PORT:-10000}"

# Ensure schema is up to date before serving requests.
cd /workspace/backend
alembic upgrade head

# Bootstrap bundled patch data only when the DB is empty.
python - <<'PY'
import glob
import os
import sys
from pathlib import Path

from sqlalchemy import text

from app.db import SessionLocal
from app.services.ingest_patch import ingest_patch_payload, load_payload_from_file

bootstrap_enabled = os.getenv("AUTO_BOOTSTRAP_PATCH_DATA", "true").strip().lower() in {"1", "true", "yes"}
if not bootstrap_enabled:
    sys.exit(0)

db = SessionLocal()
try:
    existing_versions = {
        row[0] for row in db.execute(text("SELECT version FROM patches")).all()
    }

    files = sorted(glob.glob("/workspace/backend/data/raw/*.json"))
    for file_path in files:
        payload = load_payload_from_file(Path(file_path))
        if payload.get("version") not in existing_versions:
            summary = ingest_patch_payload(db, payload)
            print(f"Bootstrapped patch {summary.version}: entities={summary.entities}, changes={summary.changes}")
    db.commit()
except Exception:
    db.rollback()
    raise
finally:
    db.close()
PY

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
