#!/usr/bin/env bash
# Setup script for the LexOps Mac auth service.
# Run once from the repo root: bash backend/mac_service/setup.sh
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
MAC_SERVICE="$REPO_ROOT/backend/mac_service"
PLIST_SRC="$MAC_SERVICE/com.lexops.auth.plist"
PLIST_DST="$HOME/Library/LaunchAgents/com.lexops.auth.plist"

echo "=== LexOps Mac Auth Service Setup ==="
echo "Repo: $REPO_ROOT"

# 1. Python — use the venv if it exists, otherwise system python3
if [[ -f "$REPO_ROOT/backend/.venv/bin/python" ]]; then
  PYTHON="$REPO_ROOT/backend/.venv/bin/python"
elif [[ -f "$REPO_ROOT/.venv/bin/python" ]]; then
  PYTHON="$REPO_ROOT/.venv/bin/python"
else
  PYTHON="$(which python3)"
fi
echo "Python: $PYTHON"

# 2. Install dependencies into the same venv
echo ""
echo "--- Instalando dependências ---"
"$PYTHON" -m pip install -r "$MAC_SERVICE/requirements.txt" --quiet

# 3. Install Playwright Chromium
echo "--- Instalando Chromium (Playwright) ---"
"$PYTHON" -m playwright install chromium

# 4. Check cloudflared
if ! command -v cloudflared &>/dev/null; then
  echo ""
  echo "--- Instalando cloudflared ---"
  if command -v brew &>/dev/null; then
    brew install cloudflared
  else
    echo "⚠️  brew não encontrado. Instale cloudflared manualmente:"
    echo "    https://developers.cloudflare.com/cloudflare-one/connections/connect-networks/downloads/"
    echo "    (não precisa de conta — o quick tunnel é gratuito)"
  fi
fi

# 5. Read secrets
echo ""
echo "--- Configuração dos secrets ---"

read -rp "Token do bot Telegram (@jusbr_andamentos_bot): " BOT_TOKEN
if [[ -z "$BOT_TOKEN" ]]; then
  echo "❌ Token não pode ser vazio."
  exit 1
fi

AUTH_SECRET="$("$PYTHON" -c "import secrets; print(secrets.token_hex(32))")"
echo "AUTH_SECRET gerado: $AUTH_SECRET"

# 6. Install plist
echo ""
echo "--- Instalando launchd agent ---"
sed \
  -e "s|__PYTHON_PATH__|$PYTHON|g" \
  -e "s|__MAC_SERVICE_DIR__|$MAC_SERVICE|g" \
  -e "s|__TELEGRAM_BOT_TOKEN__|$BOT_TOKEN|g" \
  -e "s|__AUTH_SECRET__|$AUTH_SECRET|g" \
  "$PLIST_SRC" > "$PLIST_DST"

echo "Plist instalado em: $PLIST_DST"

# Unload if already loaded
launchctl unload "$PLIST_DST" 2>/dev/null || true
launchctl load "$PLIST_DST"

echo ""
echo "✅ Serviço iniciado!"
echo ""
echo "Comandos úteis:"
echo "  Ver logs:   tail -f /tmp/lexops-auth.log"
echo "  Parar:      launchctl unload ~/Library/LaunchAgents/com.lexops.auth.plist"
echo "  Reiniciar:  launchctl unload ~/Library/LaunchAgents/com.lexops.auth.plist && launchctl load ~/Library/LaunchAgents/com.lexops.auth.plist"
echo ""
echo "Aguarde ~15s e verifique: curl http://localhost:8765/health"
