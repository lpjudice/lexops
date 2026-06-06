# ── Stage 1: Build React frontend ─────────────────────────────────────────────
FROM node:20-alpine AS frontend-build
WORKDIR /app
COPY frontend/package*.json ./
RUN npm ci
COPY frontend/ ./
ARG VITE_API_URL=/api
ENV VITE_API_URL=$VITE_API_URL
RUN npm run build

# ── Stage 2: Final image ───────────────────────────────────────────────────────
FROM python:3.11-slim

RUN apt-get update && apt-get install -y --no-install-recommends \
    nginx curl \
    gcc pkg-config zlib1g-dev libxml2-dev libxslt1-dev libxmlsec1-dev libxmlsec1-openssl \
    && rm -rf /var/lib/apt/lists/*

# Python deps
WORKDIR /app/backend
COPY backend/requirements.txt .
# lxml e xmlsec precisam ser compilados do fonte contra o MESMO libxml2 do sistema,
# senão dá "lxml & xmlsec libxml2 library version mismatch" no import.
# CFLAGS: GCC 14 trata incompatible-pointer-types como erro; xmlsec vs headers do
# lxml 5.x dispara isso. Rebaixamos para warning para o build do xmlsec passar.
RUN CFLAGS="-Wno-incompatible-pointer-types" \
    pip install --no-cache-dir --no-binary lxml --no-binary xmlsec lxml==5.2.1 xmlsec==1.3.14 \
    && pip install --no-cache-dir -r requirements.txt

# Backend source
COPY backend/ .

# Frontend static files
COPY --from=frontend-build /app/dist /app/frontend/dist

# nginx config
COPY nginx.conf /etc/nginx/nginx.conf

# Uploads volume mount point
RUN mkdir -p /app/backend/uploads

# Entrypoint
COPY start_prod.sh /start_prod.sh
RUN chmod +x /start_prod.sh

EXPOSE 8080

CMD ["/start_prod.sh"]
