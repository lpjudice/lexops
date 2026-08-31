"""Corrige prazos PENDENTES nascidos do Diário Oficial com a data errada.

Até a v445, o scraping do DJEN gravava a data de DISPONIBILIZAÇÃO no campo
`data_publicacao`. Como o motor conta a partir da publicação (art. 224, §§2º e
3º do CPC), todo prazo vindo desse caminho saiu um dia útil adiantado — e
divergia do mesmo prazo criado pelo Recorte Digital, que já recebe a publicação
pronta.

ESCOPO DELIBERADAMENTE ESTREITO (decisão do Lucas em 31/08/2026):
- só prazos com status `pendente`;
- só publicações de fonte `scraping%`;
- só quando a data atual ainda é a disponibilização (idempotente: rodar duas
  vezes não desloca a data de novo).
Prazos já tratados (cumprido/perdido/ignorado/nada a fazer) NÃO são tocados —
reescrever data de prazo cumprido seria falsear histórico.

Uso:
    python scripts/corrigir_datas_djen.py            # dry-run, não grava nada
    python scripts/corrigir_datas_djen.py --aplicar  # grava
"""
import sys
from datetime import timedelta

sys.path.insert(0, "/app/backend")
sys.path.insert(0, ".")

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
        alvos = (
            db.query(Prazo, Publicacao)
            .join(Publicacao, Publicacao.prazo_id == Prazo.id)
            .filter(Prazo.status == "pendente")
            .filter(Publicacao.fonte.cast(__import__("sqlalchemy").String).like("scraping%"))
            .all()
        )
        print(f"Prazos pendentes vindos de scraping: {len(alvos)}")
        print(f"Modo: {'APLICAR (grava)' if APLICAR else 'DRY-RUN (não grava)'}\n")

        mudados = 0
        for prazo, pub in alvos:
            processo = db.query(Processo).filter(Processo.id == prazo.processo_id).first()
            if not processo:
                print(f"  [pulado] prazo {prazo.id}: processo não encontrado")
                continue

            disponibilizacao = pub.data_disponibilizacao or prazo.data_publicacao
            estado = _estado_do_tribunal(pub.tribunal)
            feriados = _carregar_feriados(db, estado, disponibilizacao.year)
            feriados |= _carregar_feriados(db, estado, disponibilizacao.year + 1)
            publicacao = _proximo_dia_util(disponibilizacao + timedelta(days=1), feriados)

            if prazo.data_publicacao == publicacao:
                print(f"  [ok] {processo.numero_cnj}: já corrigido ({publicacao})")
                continue

            limite_antes = prazo.data_limite
            novo_com, novo_sem = calcular_prazo(
                db=db,
                data_publicacao=publicacao,
                dias=prazo.dias_prazo,
                estado=processo.estado,
                tipo_contagem=prazo.tipo_contagem,
            )

            print(f"  {processo.numero_cnj} ({prazo.peca_necessaria or prazo.tipo})")
            print(f"     disponibilização : {disponibilizacao}")
            print(f"     publicação  {prazo.data_publicacao} -> {publicacao}")
            print(f"     LIMITE      {limite_antes} -> {novo_com}")

            if APLICAR:
                pub.data_disponibilizacao = disponibilizacao
                prazo.data_publicacao = publicacao
                prazo.data_limite = novo_com
                prazo.data_limite_sem_feriado = novo_sem
                # Zera o controle diário pra o lembrete de amanhã já sair com a
                # data nova, em vez de repetir a antiga.
                prazo.ultimo_lembrete_em = None
            mudados += 1

        if APLICAR:
            db.commit()
            print(f"\n{mudados} prazo(s) corrigido(s) e gravado(s).")
            print("Atenção: o evento no Google Calendar NÃO é atualizado por este")
            print("script — abra e salve o prazo na tela para ressincronizar.")
        else:
            print(f"\n{mudados} prazo(s) SERIAM corrigidos. Rode com --aplicar para gravar.")
    finally:
        db.close()


if __name__ == "__main__":
    main()
