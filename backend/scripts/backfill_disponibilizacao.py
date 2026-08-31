"""Preenche `data_disponibilizacao` no histórico e alinha as publicações do DJEN.

Faz duas coisas, ambas idempotentes:

1. **Recorte Digital (gmail)** — lê a disponibilização do corpo do e-mail e
   grava na coluna. Sem isso, o card de um prazo vindo do Recorte não mostra
   "Disp.:", enquanto o do Diário Oficial mostra — a mesma informação aparecendo
   só em metade dos casos.

2. **Publicações do DJEN cujo prazo já foi corrigido** — o script
   `corrigir_datas_djen.py` ajustou `prazos.data_publicacao` mas deixou
   `publicacoes.data_publicacao` com a disponibilização. Resultado: o chip da
   origem no card mostrava um dia e a linha de datas mostrava outro. Aqui a
   publicação passa a guardar publicação em `data_publicacao` e disponibilização
   na coluna própria, que é a semântica correta das duas colunas.
   Efeito colateral desejado: no menu Diário Oficial a publicação passa a
   aparecer no mesmo dia da equivalente do Recorte, deixando as duplicatas
   lado a lado em vez de espalhadas em dias diferentes.

Uso:
    python scripts/backfill_disponibilizacao.py            # dry-run
    python scripts/backfill_disponibilizacao.py --aplicar  # grava
"""
import sys

sys.path.insert(0, "/app/backend")
sys.path.insert(0, ".")


def _registrar_todos_os_models() -> None:
    """Ver nota em corrigir_datas_djen.py: falta um model e o ORM inteiro quebra."""
    import importlib
    import pkgutil

    import app.models as pacote

    for mod in pkgutil.iter_modules(pacote.__path__):
        importlib.import_module(f"app.models.{mod.name}")


_registrar_todos_os_models()

from app.database import SessionLocal  # noqa: E402
from app.models.prazo import Prazo  # noqa: E402
from app.models.publicacao import Publicacao  # noqa: E402
from app.services.datas_publicacao import extrair_datas  # noqa: E402

APLICAR = "--aplicar" in sys.argv


def main() -> None:
    db = SessionLocal()
    try:
        print(f"Modo: {'APLICAR (grava)' if APLICAR else 'DRY-RUN (não grava)'}\n")

        # ── 1. Recorte Digital: disponibilização vem no texto ────────────────
        pubs = (
            db.query(Publicacao)
            .filter(Publicacao.fonte == "gmail")
            .filter(Publicacao.data_disponibilizacao.is_(None))
            .all()
        )
        achou = 0
        for pub in pubs:
            disp, _ = extrair_datas(pub.texto_completo or pub.texto_resumo)
            if not disp:
                continue
            if APLICAR:
                pub.data_disponibilizacao = disp
            achou += 1
        print(f"1) Recorte Digital: {len(pubs)} sem disponibilização; "
              f"{achou} com a data legível no texto.")

        # ── 2. Alinha publicações do DJEN cujo prazo já foi corrigido ────────
        # Critério estreito: só onde o prazo vinculado JÁ tem a data certa e a
        # publicação ficou para trás. Não recalcula nada nem toca em quem não
        # passou pelo corrigir_datas_djen.py.
        # Dois filtros extras, ambos aprendidos no dry-run:
        #
        # - `Prazo.status == 'pendente'`: sem isso o script alcançava prazos já
        #   cumpridos, contra a decisão de não reescrever histórico.
        # - `Prazo.data_publicacao > data_disponibilizacao`: a correção do
        #   art. 224, §2º sempre empurra a data para FRENTE. Apareceu um prazo
        #   cumprido com data ANTERIOR à disponibilização (ajuste manual antigo);
        #   alinhar por ele gravaria uma publicação anterior à própria
        #   disponibilização, que é impossível.
        desalinhadas = (
            db.query(Publicacao, Prazo)
            .join(Prazo, Publicacao.prazo_id == Prazo.id)
            .filter(Prazo.status == "pendente")
            .filter(Publicacao.data_disponibilizacao.isnot(None))
            .filter(Publicacao.data_publicacao == Publicacao.data_disponibilizacao)
            .filter(Prazo.data_publicacao > Publicacao.data_disponibilizacao)
            .all()
        )
        print(f"\n2) Publicações do DJEN desalinhadas do próprio prazo: {len(desalinhadas)}")
        for pub, prazo in desalinhadas:
            print(f"   pub {str(pub.id)[:8]} | data_publicacao {pub.data_publicacao} "
                  f"-> {prazo.data_publicacao} (disp. {pub.data_disponibilizacao} preservada)")
            if APLICAR:
                pub.data_publicacao = prazo.data_publicacao

        if APLICAR:
            db.commit()
            print("\nGravado.")
        else:
            print("\nNada gravado. Rode com --aplicar.")
    finally:
        db.close()


if __name__ == "__main__":
    main()
