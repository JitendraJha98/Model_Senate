#!/usr/bin/env bash
set -euo pipefail

uv run python -m backend.main &
BACKEND_PID=$!

cd frontend
npm run dev

kill "$BACKEND_PID" >/dev/null 2>&1 || true

