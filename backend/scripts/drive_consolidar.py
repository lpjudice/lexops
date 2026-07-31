"""Encontra e mescla pastas duplicadas no Drive (conta master).

Uso (a partir de backend/, com o DATABASE_URL/tokens do ambiente):
    ./.venv/bin/python scripts/drive_consolidar.py --dry-run --max-depth 2
    ./.venv/bin/python scripts/drive_consolidar.py --execute --max-depth 2

Sem --execute, roda em dry-run (não toca no Drive).
"""

import argparse
import sys

import app.main  # noqa: F401 — registra mappers/config
from app.services.drive_manutencao import consolidar


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--execute", action="store_true", help="aplica de fato (default é dry-run)")
    ap.add_argument("--dry-run", action="store_true", help="apenas lista (default)")
    ap.add_argument("--max-depth", type=int, default=2)
    ap.add_argument("--root", default=None, help="folder_id inicial (raiz LexOps se omitido)")
    args = ap.parse_args()

    dry_run = not args.execute
    res = consolidar(root_id=args.root, max_depth=args.max_depth, dry_run=dry_run)

    if res.get("erro"):
        print("ERRO:", res["erro"])
        return 1

    print(f"{'[DRY-RUN] ' if dry_run else '[EXECUTADO] '}"
          f"grupos duplicados: {res['grupos_duplicados']} | pastas mescladas: {res['pastas_mescladas']}")
    print(f"total de ações: {len(res['acoes'])}\n")
    for a in res["acoes"]:
        print(a)
    if dry_run:
        print("\nNada foi alterado. Rode com --execute para aplicar.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
