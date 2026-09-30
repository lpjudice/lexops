#!/usr/bin/env bash
# Checagem antes de qualquer deploy (rode em TODO chat/clone antes de `flyctl deploy`):
#   bash scripts/pre-deploy-check.sh
#
# Barra os dois problemas que derrubaram deploys: (1) deployar de uma linhagem que não
# contém o que já está no main (perde alterações de outros chats) e (2) cadeia do Alembic
# com mais de um head ou com migração faltando (o app crasha no startup).
# Só lê — não altera nada. Sai com código != 0 se algo estiver errado.
set -uo pipefail
cd "$(dirname "$0")/.."

erro=0
falha() { echo "❌ $1"; erro=1; }
ok() { echo "✅ $1"; }

git fetch origin main --quiet 2>/dev/null || { echo "⚠️  não consegui dar fetch no origin/main"; erro=1; }

# 1) working tree limpo (deploy manda o diretório, não o commit)
if [ -n "$(git status --porcelain --untracked-files=no)" ]; then
  falha "há alterações não commitadas — o deploy levaria código que não está no git"
  git status --short --untracked-files=no | head -8
else
  ok "working tree limpo"
fi

# 2) HEAD contém tudo que está no origin/main
if git merge-base --is-ancestor origin/main HEAD 2>/dev/null; then
  ok "HEAD contém origin/main ($(git rev-parse --short origin/main))"
else
  falta=$(git rev-list --count HEAD..origin/main 2>/dev/null || echo "?")
  falha "HEAD NÃO contém origin/main (faltam $falta commit(s)). Faça: git merge origin/main"
fi

# 3) Alembic: exatamente 1 head, e todo down_revision existe
python3 - <<'EOF' || erro=1
import re, sys, pathlib
revs, downs = {}, {}
for f in pathlib.Path("backend/alembic/versions").glob("*.py"):
    t = f.read_text(encoding="utf-8")
    r = re.search(r"^revision(?:: str)?\s*=\s*['\"]([^'\"]+)['\"]", t, re.M)
    if not r:
        continue
    d = re.search(r"^down_revision[^=]*=\s*(.+)$", t, re.M)
    refs = re.findall(r"['\"]([0-9a-zA-Z_]+)['\"]", d.group(1)) if d else []
    revs[r.group(1)] = f.name
    downs[r.group(1)] = refs
heads = [r for r in revs if not any(r in ds for ds in downs.values())]
faltando = sorted({d for ds in downs.values() for d in ds if d not in revs})
bad = False
if len(heads) != 1:
    print(f"❌ Alembic tem {len(heads)} head(s): {sorted(heads)} (precisa ser 1)"); bad = True
if faltando:
    print(f"❌ Alembic referencia migração inexistente: {faltando}"); bad = True
if not bad:
    print(f"✅ Alembic: 1 head ({heads[0]}), {len(revs)} migrações, cadeia completa")
sys.exit(1 if bad else 0)
EOF

echo
if [ "$erro" -ne 0 ]; then
  echo "⛔ NÃO FAÇA DEPLOY. Corrija acima e rode de novo."
  exit 1
fi
echo "✅ Pode fazer deploy:  flyctl deploy --remote-only --depot=false -a lexops"
echo "   (--depot=false: o builder Depot não é alcançável em sessões na nuvem)"
