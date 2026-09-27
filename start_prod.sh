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
# 180s, não 60s: reproduzido de verdade em 27/set que sob throttling de CPU
# da VM (vCPU compartilhada, load average do próprio convidado baixo — não é
# CPU-bound no app, é a VM sendo sub-alocada pelo host) o simples import do
# app.main (FastAPI + SQLAlchemy + pypdf + anthropic + google clients + ...)
# pode levar 45-55s sozinho. Com 60s de orçamento total, o boot batia bem na
# borda e era matado quase sempre bem na hora de ficar pronto — queimando o
# contador de restart da máquina (limite de 10) num loop que nunca deixava
# nenhuma tentativa terminar.
until curl -sf http://127.0.0.1:8000/health > /dev/null 2>&1; do
  TRIES=$((TRIES+1))
  if [ $TRIES -ge 180 ]; then
    echo "[START] ERROR: API did not start after 180s"
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
nginx -g 'daemon off;' &
NGINX_PID=$!

# Watchdog: sem isso, se o uvicorn morrer DEPOIS do boot (ex.: OOM no meio
# de uma sincronização pesada — reproduzido de verdade em 27/set) o nginx
# ficava de pé pra sempre encaminhando pra um backend morto (connect()
# failed, connection refused), e como o nginx em si nunca cai, a máquina
# continuava "started"/saudável pro flyd — nunca reiniciava sozinha.
while kill -0 "$UVICORN_PID" 2>/dev/null && kill -0 "$NGINX_PID" 2>/dev/null; do
  sleep 2
done
if ! kill -0 "$UVICORN_PID" 2>/dev/null; then
  echo "[START] ERRO: uvicorn morreu depois do boot (ver logs acima, ex. OOM) — derrubando nginx pra forçar reinício da máquina"
  kill "$NGINX_PID" 2>/dev/null || true
fi
wait "$NGINX_PID"
