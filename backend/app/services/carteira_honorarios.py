from collections import defaultdict

from sqlalchemy.orm import Session

from app.models.carteira import (
    CarteiraCliente,
    CarteiraDebenturePosicao,
    CarteiraFundoPosicao,
    CarteiraFundoReferencia,
    CarteiraImobiliarioPosicao,
)


def calcular_expectativa_exito_carteira(db: Session) -> dict:
    """Espelha o cálculo de 'Expectativa Êxito' da Carteira (honorariosPorCliente,
    em CarteiraSimple.tsx): só entram posições com faz_parte_honorarios=True,
    usando o % próprio da posição ou, na falta dele, o % padrão do cliente por
    tipo de ativo (fin -> percentual_sucesso_fin, imob -> percentual_sucesso_imob),
    caindo para percentual_sucesso_geral quando nenhum dos dois estiver definido.
    Fundos com percentual_credito_recuperavel aplicam a queda antes do % de êxito.
    """
    clientes = db.query(CarteiraCliente).filter(CarteiraCliente.ativo == True).all()
    if not clientes:
        return {"total": 0.0, "por_cliente": []}

    cliente_ids = [c.id for c in clientes]

    debs_por_cliente: dict[int, list] = defaultdict(list)
    for d in db.query(CarteiraDebenturePosicao).filter(
        CarteiraDebenturePosicao.cliente_id.in_(cliente_ids),
        CarteiraDebenturePosicao.faz_parte_honorarios == True,
    ).all():
        debs_por_cliente[d.cliente_id].append(d)

    imobs_por_cliente: dict[int, list] = defaultdict(list)
    for i in db.query(CarteiraImobiliarioPosicao).filter(
        CarteiraImobiliarioPosicao.cliente_id.in_(cliente_ids),
        CarteiraImobiliarioPosicao.faz_parte_honorarios == True,
    ).all():
        imobs_por_cliente[i.cliente_id].append(i)

    fnds_por_cliente: dict[int, list] = defaultdict(list)
    for f in db.query(CarteiraFundoPosicao).filter(
        CarteiraFundoPosicao.cliente_id.in_(cliente_ids),
        CarteiraFundoPosicao.faz_parte_honorarios == True,
    ).all():
        fnds_por_cliente[f.cliente_id].append(f)

    queda_por_fundo = {
        r.id: r.percentual_credito_recuperavel
        for r in db.query(CarteiraFundoReferencia).all()
    }

    por_cliente = []
    for c in clientes:
        pct_fin_padrao = c.percentual_sucesso_fin if c.percentual_sucesso_fin is not None else (c.percentual_sucesso_geral or 0.0)
        pct_imob_padrao = c.percentual_sucesso_imob if c.percentual_sucesso_imob is not None else (c.percentual_sucesso_geral or 0.0)

        exito = 0.0
        for d in debs_por_cliente.get(c.id, []):
            pct = d.percentual_sucesso_honor if d.percentual_sucesso_honor is not None else pct_fin_padrao
            exito += (d.valor_aplicado or 0.0) * (pct / 100)
        for f in fnds_por_cliente.get(c.id, []):
            queda = queda_por_fundo.get(f.fundo_id)
            base = (f.valor_aplicado or 0.0) * (1 - queda / 100) if queda is not None else (f.valor_aplicado or 0.0)
            pct = f.percentual_sucesso_honor if f.percentual_sucesso_honor is not None else pct_fin_padrao
            exito += base * (pct / 100)
        for i in imobs_por_cliente.get(c.id, []):
            pct = i.percentual_sucesso_honorario if i.percentual_sucesso_honorario is not None else pct_imob_padrao
            exito += (i.valor_total_compromissado or 0.0) * (pct / 100)

        if exito > 0:
            por_cliente.append({"nome": c.nome or "—", "valor": exito})

    por_cliente.sort(key=lambda x: x["valor"], reverse=True)
    total = sum(x["valor"] for x in por_cliente)
    return {"total": total, "por_cliente": por_cliente}
