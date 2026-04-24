#!/bin/sh
set -e

# Start FastAPI in background
cd /app/backend
uvicorn app.main:app --host 127.0.0.1 --port 8000 --workers 2 &

# Wait for API to be ready
echo "Waiting for API..."
for i in $(seq 1 30); do
  curl -sf http://127.0.0.1:8000/health && break
  sleep 1
done

# Start nginx in foreground
nginx -g 'daemon off;'
