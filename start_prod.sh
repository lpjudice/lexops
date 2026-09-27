#!/bin/sh
set -e

echo "[START] Starting Gestor Juridico..."

cd /app/backend
echo "[START] Applying database migrations..."
alembic upgrade head

# Start FastAPI, capturing output
echo "[START] Launching uvicorn..."
uvicorn app.main:app --host 127.0.0.1 --port 8000 --workers 1 2>&1 &
UVICORN_PID=$!

echo "[START] Waiting for API to be ready (PID=$UVICORN_PID)..."
TRIES=0
until curl -sf http://127.0.0.1:8000/health > /dev/null 2>&1; do
  TRIES=$((TRIES+1))
  if [ $TRIES -ge 60 ]; then
    echo "[START] ERROR: API did not start after 60s"
    # `wait $UVICORN_PID` aqui travava para sempre se o uvicorn tivesse
    # ficado pronto DEPOIS do timeout (ex: startup lento por instabilidade
    # do Postgres) — o processo continuava rodando de verdade, então `wait`
    # nunca retornava, o script nunca chegava no `exit`, o nginx nunca subia
    # e a máquina ficava presa em "started" sem nunca servir nada na 8080,
    # sem nunca reiniciar (reproduzido de verdade na madrugada de 27/set).
    kill $UVICORN_PID 2>/dev/null || true
    exit 1
  fi
  # Check if uvicorn died
  if ! kill -0 $UVICORN_PID 2>/dev/null; then
    echo "[START] ERROR: uvicorn process died"
    exit 1
  fi
  sleep 1
done

echo "[START] API is ready. Starting nginx..."
nginx -g 'daemon off;'
