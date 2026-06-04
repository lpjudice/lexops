#!/usr/bin/env bash
# Ativa os git hooks versionados deste repo (.githooks/).
# Rode uma vez por clone:  bash scripts/setup-hooks.sh
set -euo pipefail
cd "$(dirname "$0")/.."
git config core.hooksPath .githooks
chmod +x .githooks/* 2>/dev/null || true
echo "✅ core.hooksPath = .githooks (semi-trava jus.br ativa)"
