#!/usr/bin/env bash
# Pruebas e2e de la UI (Fase 4): reconstruye la base con datos sintéticos, levanta la API (:8001)
# y la UI compilada (:5174), corre Playwright y apaga todo. Uso: scripts/e2e.sh [--no-rebuild]
set -euo pipefail
cd "$(dirname "$0")/.."
export DATABASE_URL="${DATABASE_URL:-postgresql+psycopg://mdm@127.0.0.1:5433/mdm_prototype}"
API_PORT="${E2E_API_PORT:-8001}"
UI_PORT="${E2E_UI_PORT:-5174}"

if [[ "${1:-}" == "--no-rebuild" ]]; then
  shift
else
  (cd backend && python cli.py rebuild --yes --actor e2e)
fi

for port in "$API_PORT" "$UI_PORT"; do
  if (exec 3<>"/dev/tcp/127.0.0.1/$port") 2>/dev/null; then
    echo "El puerto $port ya está en uso; detenga ese proceso antes de correr las pruebas e2e." >&2; exit 2
  fi
done

(cd backend && CORS_ORIGINS="http://127.0.0.1:${UI_PORT},http://localhost:${UI_PORT}" uvicorn app.main:app --port "$API_PORT" --log-level warning) &
API_PID=$!
(cd frontend && VITE_API_BASE="http://127.0.0.1:${API_PORT}/api/v1" npm run build >/dev/null && npx vite preview --host 127.0.0.1 --port "$UI_PORT" --strictPort >/dev/null 2>&1) &
UI_PID=$!
trap 'kill $API_PID $UI_PID 2>/dev/null || true; pkill -f "vite preview --host 127.0.0.1 --port $UI_PORT" 2>/dev/null || true' EXIT

for i in $(seq 1 60); do
  curl -fs "http://127.0.0.1:${API_PORT}/health" >/dev/null 2>&1 && curl -fs "http://127.0.0.1:${UI_PORT}/" >/dev/null 2>&1 && break
  sleep 1
done

cd frontend
E2E_UI_BASE="http://127.0.0.1:${UI_PORT}" E2E_API_BASE="http://127.0.0.1:${API_PORT}/api/v1" npx playwright test "$@"
