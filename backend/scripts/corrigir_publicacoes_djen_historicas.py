"""Converte disponibilização -> publicação nas publicações ANTIGAS do scraping.

Por que isso é necessário mesmo já tendo a correção na inserção (v445):
a correção só age quando a publicação ENTRA no banco. Publicações capturadas
antes dela continuaram com `data_publicacao` = disponibilização, e **cada vez
que uma delas é tratada, nasce um prazo um dia útil adiantado**. Foi o que
aconteceu com o 5000972-24.2026.8.08.0017: publicação de 28/08 (anterior ao
deploy), prazo criado em 31/08 já errado (limite 18/09 em vez de 21/09).

Enquanto essas publicações existirem com a data errada, o bug se repete a cada
tratamento novo — não basta corrigir daqui pra frente.

O que faz:
- publicações de fonte `scraping%` onde `data_publicacao == data_disponibilizacao`
  (marca de não convertida) recebem a publicação correta;
- prazos PENDENTES ligados a elas são recalculados junto;
- prazos já tratados (cumprido/perdido/ignorado/nada a fazer) NÃO são tocados —
  a publicação é corrigida, o prazo histórico fica como está.

Uso:
    python scripts/corrigir_publicacoes_djen_historicas.py            # dry-run
    python scripts/corrigir_publicacoes_djen_historicas.py --aplicar
"""
import sys
from datetime import timedelta

sys.path.insert(0, "/app/backend")
sys.path.insert(0, ".")


def _registrar_todos_os_models() -> None:
    """Sem todos os models importados o ORM falha ao resolver relacionamentos."""
    import importlib
    import pkgutil

    import app.models as pacote

    for mod in pkgutil.iter_modules(pacote.__path__):
        importlib.import_module(f"app.models.{mod.name}")


_registrar_todos_os_models()

from app.database import SessionLocal  # noqa: E402
from app.models.prazo import Prazo  # noqa: E402
from app.models.processo import Processo  # noqa: E402
from app.models.publicacao import Publicacao  # noqa: E402
from app.routers.diario import _estado_do_tribunal  # noqa: E402
from app.services.prazo_calc import (  # noqa: E402
    _carregar_feriados,
    _proximo_dia_util,
    calcular_prazo,
)

APLICAR = "--aplicar" in sys.argv


def main() -> None:
    db = SessionLocal()
    try:
        print(f"Modo: {'APLICAR (grava)' if APLICAR else 'DRY-RUN (não grava)'}\n")

        pubs = (
            db.query(Publicacao)
            .filter(Publicacao.fonte.cast(__import__("sqlalchemy").String).like("scraping%"))
            .filter(Publicacao.data_disponibilizacao.isnot(None))
            .filter(Publicacao.data_publicacao == Publicacao.data_disponibilizacao)
            .order_by(Publicacao.data_publicacao.desc())
            .all()
        )
        print(f"Publicações de scraping ainda com a disponibilização como publicação: {len(pubs)}\n")

        cache_feriados: dict[tuple[str, int], set] = {}

        def feriados_de(estado: str, ano: int) -> set:
            chave = (estado, ano)
            if chave not in cache_feriados:
                cache_feriados[chave] = (
                    _carregar_feriados(db, estado, ano) | _carregar_feriados(db, estado, ano + 1)
                )
            return cache_feriados[chave]

        pubs_mudadas = 0
        prazos_mudados = 0
        prazos_preservados = 0

        for pub in pubs:
            disp = pub.data_disponibilizacao
            estado = _estado_do_tribunal(pub.tribunal)
            publicacao = _proximo_dia_util(disp + timedelta(days=1), feriados_de(estado, disp.year))
            if publicacao == pub.data_publicacao:
                continue

            prazo = db.query(Prazo).filter(Prazo.id == pub.prazo_id).first() if pub.prazo_id else None
            marca = ""
            if prazo is not None and prazo.status != "pendente":
                marca = f"  [prazo {prazo.status} preservado]"
                prazos_preservados += 1

            print(f"  pub {str(pub.id)[:8]} {pub.tribunal or '?':6} disp {disp} -> pub {publicacao}{marca}")

            if APLICAR:
                pub.data_publicacao = publicacao
            pubs_mudadas += 1

            if prazo is not None and prazo.status == "pendente":
                processo = db.query(Processo).filter(Processo.id == prazo.processo_id).first()
                if not processo:
                    continue
                novo_com, novo_sem = calcular_prazo(
                    db=db,
                    data_publicacao=publicacao,
                    dias=prazo.dias_prazo,
                    estado=processo.estado,
                    tipo_contagem=prazo.tipo_contagem,
                )
                print(f"        prazo {processo.numero_cnj}: limite {prazo.data_limite} -> {novo_com}")
                if APLICAR:
                    prazo.data_publicacao = publicacao
                    prazo.data_limite = novo_com
                    prazo.data_limite_sem_feriado = novo_sem
                    prazo.ultimo_lembrete_em = None
                prazos_mudados += 1

        print(f"\n{pubs_mudadas} publicação(ões), {prazos_mudados} prazo(s) pendente(s) recalculado(s), "
              f"{prazos_preservados} prazo(s) já tratado(s) preservado(s).")
        if APLICAR:
            db.commit()
            print("Gravado. Eventos do Google Calendar NÃO são atualizados aqui.")
        else:
            print("Nada gravado. Rode com --aplicar.")
    finally:
        db.close()


if __name__ == "__main__":
    main()
