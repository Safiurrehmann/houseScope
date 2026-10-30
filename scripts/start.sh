#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
if [[ ! -d .venv ]]; then python3 -m venv .venv; fi
.venv/bin/pip install -q -r backend/requirements.txt
if [[ ! -d frontend/node_modules ]]; then (cd frontend && npm install --no-audit --no-fund); fi
.venv/bin/uvicorn backend.main:app --host 127.0.0.1 --port 8000 &
backend_pid=$!
(cd frontend && npm run dev) &
frontend_pid=$!
trap 'kill "$backend_pid" "$frontend_pid" 2>/dev/null || true' EXIT INT TERM
wait
