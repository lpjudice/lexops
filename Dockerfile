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
    # Chromium system deps (replaces playwright install --with-deps which fails on slim)
    libnss3 libnspr4 libatk1.0-0 libatk-bridge2.0-0 libcups2 libdrm2 \
    libxkbcommon0 libxcomposite1 libxdamage1 libxfixes3 libxrandr2 \
    libgbm1 libasound2 libpangocairo-1.0-0 libpango-1.0-0 libcairo2 \
    fonts-liberation fonts-freefont-ttf \
    && rm -rf /var/lib/apt/lists/*

# Python deps
WORKDIR /app/backend
COPY backend/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Playwright Chromium binary (system deps already installed above)
RUN playwright install chromium

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
