import json
import re
import uuid
from collections import defaultdict
from datetime import date, datetime, timedelta
from typing import Any

import httpx
from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel
from sqlalchemy.orm import Session, joinedload

from app.database import get_db
from app.models.cliente import Cliente
from app.models.prazo import Prazo
from app.models.processo import Processo
from app.models.publicacao import Publicacao
from app.services.gmail_diario import sincronizar_gmail
from app.services.google_master_tokens import load_master_google_tokens, save_master_google_tokens
from app.services.ia_diario import analisar_publicacao
from app.services.prazo_calc import calcular_prazo

router = APIRouter(prefix="/diario2", tags=["diario2"])

LUCAS_GMAIL = "lucasjudice@gmail.com"


class SyncDiario2Result(BaseModel):
    inseridas: int
    duplicatas: int
    erros: int
    sem_publicacoes: int
    mensagem: str


class Diario2PrazoRequest(BaseModel):
    processo_id: uuid.UUID | None = None
    tipo: str = "manifestacao"
    descricao: str | None = None
    peca_necessaria: str | None = None
    responsavel: str | None = None
    dias_prazo: int = 5
    tipo_contagem: str = "uteis"


class Diario2StatusPrazoRequest(BaseModel):
    status: str


def _normalizar_cnj(numero: str | None) -> str:
    return re.sub(r"\D", "", numero or "")


def _limpar_texto(texto: str | None) -> str:
    texto = re.sub(r"<[^>]+>", " ", texto or "")
    texto = re.sub(r"\s+", " ", texto)
    return texto.strip()


def _quebrar_linhas_publicacao(texto: str) -> str:
    texto = _limpar_texto(texto)
    marcadores = [
        "Data de Disponibilização:", "Data de Publicação:", "Jornal:", "Caderno:",
        "Local:", "Página:", "Tribunal de Justiça", "PROCESSO:", "PROCESSO Nº",
        "Classe judicial:", "Orgao Julgador colegiado:", "Órgão Julgador colegiado:",
        "Relator:", "AGRAVANTE:", "AGRAVADO:", "APELANTE:", "APELADO:",
        "IMPETRANTE:", "IMPETRADO:", "EXECUTADO :", "EXECUTADO:", "ADVOGADO",
        "Representante:", "DESPACHO", "DECISAO", "DECISÃO", "INTIME-SE",
        "NOTIFIQUE-SE", "CIENTIFIQUE-SE", "REMETAM-SE", "Acesso ao documento:",
        "Identificador do documento:",
    ]
    for marcador in marcadores:
        texto = re.sub(rf"\s+({re.escape(marcador)})", r"\n\1", texto, flags=re.IGNORECASE)
    texto = re.sub(r"\s+(Publica(?:ç|c)[aã]o:\s*\d+\s*\.)", r"\n\1", texto, flags=re.IGNORECASE)
    texto = re.sub(r"\s+(\d+\s*-\s*\d{7}-\d{2}\.\d{4}\.\d\.\d{2}\.\d{4})", r"\n\1", texto)
    return re.sub(r"\n{3,}", "\n\n", texto).strip()


def _conteudo_relevante(texto: str | None) -> str:
    texto = _limpar_texto(texto)
    if not texto or "Sem publicações" in texto:
        return texto
    texto = re.sub(r"^.*?\bPublica(?:ç|c)[aã]o:\s*\d+\s*\.", "", texto, flags=re.IGNORECASE).strip()
    texto = re.sub(
        r"^(?:Data de Disponibiliza(?:ç|c)[aã]o:.*?)(?=(?:\d+\s*-\s*)?\d{7}-\d{2}\.\d{4}\.\d\.\d{2}\.\d{4}|PROCESSO:|PROCESSO Nº|Classe judicial:|Intima(?:ç|c)[aã]o|DESPACHO|DECIS|Tribunal de Justiça)",
        "",
        texto,
        flags=re.IGNORECASE,
    ).strip()
    cnj_match = re.search(r"(?:\d+\s*-\s*)?\d{7}-\d{2}\.\d{4}\.\d\.\d{2}\.\d{4}", texto)
    processo_match = re.search(r"\bPROCESSO(?: Nº|:)", texto, flags=re.IGNORECASE)
    starts = [m.start() for m in (cnj_match, processo_match) if m]
    if starts:
        texto = texto[min(starts):]
    return texto.strip()


def _linhas_publicacao(texto: str | None) -> list[str]:
    return [
        linha.strip()
        for linha in _quebrar_linhas_publicacao(texto or "").splitlines()
        if linha.strip()
    ]


def _extrair_campo(texto: str, rotulo: str) -> str | None:
    for linha in _linhas_publicacao(texto):
        match = re.match(rf"^(?:{rotulo})\s*:?\s*(.+)$", linha, flags=re.IGNORECASE)
        if match:
            return _limpar_texto(match.group(1))[:280]
    return None


def _partes_por_papel(texto: str | None) -> list[dict[str, Any]]:
    papeis = {
        "APELANTE", "APELADO", "AGRAVANTE", "AGRAVADO", "IMPETRANTE", "IMPETRADO",
        "EXECUTADO", "EXEQUENTE", "AUTOR", "RÉU", "REU", "RECORRENTE", "RECORRIDO",
        "POLO PASSIVO", "POLO ATIVO",
    }
    partes: list[dict[str, Any]] = []
    atual: dict[str, Any] | None = None
    for linha in _linhas_publicacao(texto):
        papel_match = re.match(r"^([A-ZÁÀÂÃÉÊÍÓÔÕÚÇ ]{3,24})\s*:\s*(.+)$", linha)
        if papel_match:
            papel = papel_match.group(1).strip().upper()
            nome = _limpar_texto(papel_match.group(2))
            if papel in papeis and nome:
                atual = {"papel": papel, "nome": nome[:240], "advogados": []}
                partes.append(atual)
                continue
        adv_match = re.match(r"^(?:Representante|ADVOGADO(?:\s*\(A\))?)\s*:?\s*(.+)$", linha, flags=re.IGNORECASE)
        if adv_match and atual is not None:
            advogado = _limpar_texto(adv_match.group(1))
            if advogado:
                atual["advogados"].append(advogado[:220])
    return partes


def _extrair_detalhes_publicacao(texto: str | None) -> dict[str, Any]:
    texto_limpo = _limpar_texto(texto)
    detalhes: dict[str, Any] = {}
    campos = {
        "data_disponibilizacao": r"Data de Disponibiliza(?:ç|c)[aã]o",
        "data_publicacao": r"Data de Publica(?:ç|c)[aã]o",
        "jornal": r"Jornal",
        "caderno": r"Caderno",
        "local": r"Local",
        "classe": r"Classe judicial",
        "orgao": r"Orgao Julgador colegiado|Órgão Julgador colegiado",
        "relator": r"Relator",
    }
    for key, rotulo in campos.items():
        valor = _extrair_campo(texto_limpo, rotulo)
        if valor:
            detalhes[key] = valor
    partes = _partes_por_papel(texto_limpo)
    if partes:
        detalhes["partes"] = [
            f"{parte['papel']}: {parte['nome']}"
            for parte in partes[:8]
        ]
        detalhes["partes_estruturadas"] = partes[:8]
    return detalhes


def _cliente_sugerido(texto: str | None) -> str | None:
    partes = _partes_por_papel(texto)
    for parte in partes:
        advogados = " ".join(parte.get("advogados") or []).upper()
        nome = str(parte.get("nome") or "")
        if "LUCAS PIMENTA JUDICE" in advogados and "LUCAS PIMENTA JUDICE" not in nome.upper():
            return nome[:160]
    for parte in partes:
        nome = str(parte.get("nome") or "")
        if nome and "LUCAS PIMENTA JUDICE" not in nome.upper():
            return nome[:160]
    return None


def _split_blocos_publicacao(texto: str | None) -> list[str]:
    texto_limpo = _limpar_texto(texto)
    if not texto_limpo:
        return []
    matches = list(re.finditer(r"\bPublica(?:ç|c)[aã]o:\s*\d+\s*\.", texto_limpo, flags=re.IGNORECASE))
    if not matches:
        return [texto_limpo]
    blocos: list[str] = []
    prefixo = texto_limpo[:matches[0].start()].strip()
    if re.search(r"\d{7}-\d{2}\.\d{4}\.\d\.\d{2}\.\d{4}", prefixo):
        blocos.append(prefixo)
    for idx, match in enumerate(matches):
        start = match.start()
        end = matches[idx + 1].start() if idx + 1 < len(matches) else len(texto_limpo)
        bloco = texto_limpo[start:end].strip()
        bloco = re.sub(r"\s*Total de Publica(?:ç|c)[õo]es:.*$", "", bloco, flags=re.IGNORECASE).strip()
        if bloco:
            blocos.append(bloco)
    return blocos


def _cnj_principal_do_bloco(bloco: str) -> str | None:
    linhas = _linhas_publicacao(bloco)
    for linha in linhas:
        if re.search(r"^(?:\d+\s*-\s*)?\d{7}-\d{2}\.\d{4}\.\d\.\d{2}\.\d{4}", linha):
            match = re.search(r"\d{7}-\d{2}\.\d{4}\.\d\.\d{2}\.\d{4}", linha)
            if match:
                return match.group(0)
        if re.match(r"^PROCESSO(?: Nº|:)", linha, flags=re.IGNORECASE):
            match = re.search(r"\d{7}-\d{2}\.\d{4}\.\d\.\d{2}\.\d{4}", linha)
            if match:
                return match.group(0)
    match = re.search(r"\d{7}-\d{2}\.\d{4}\.\d\.\d{2}\.\d{4}", bloco)
    return match.group(0) if match else None


def _email_base_id(email_message_id: str | None) -> str | None:
    if not email_message_id:
        return None
    return re.sub(r"_(?:sem|pub|pub\d+|[0-9]{7}-\d{2}\.\d{4}\.\d\.\d{2}\.\d{4}).*$", "", email_message_id)


def _email_id_tem_contador_publicacao(email_message_id: str | None) -> bool:
    return bool(email_message_id and re.search(r"_pub\d+_", email_message_id))


def _expandir_itens_por_contador(itens: list[dict[str, Any]]) -> list[dict[str, Any]]:
    grupos: dict[str, dict[str, Any]] = {}
    avulsos: list[dict[str, Any]] = []
    for item in itens:
        if "Sem publicações nesta edição." in (item.get("texto_resumo") or ""):
            avulsos.append(item)
            continue
        base_id = _email_base_id(item.get("email_message_id"))
        texto = item.get("texto_completo") or item.get("texto_resumo") or ""
        if not base_id or not texto:
            avulsos.append(item)
            continue
        grupos.setdefault(base_id, item)

    expandidos = list(avulsos)
    for base_id, item in grupos.items():
        blocos = _split_blocos_publicacao(item.get("texto_completo") or item.get("texto_resumo"))
        if not blocos:
            expandidos.append(item)
            continue
        for idx, bloco in enumerate(blocos, start=1):
            cnj = _cnj_principal_do_bloco(bloco)
            expandidos.append({
                **item,
                "numero_cnj": cnj,
                "texto_resumo": bloco[:600],
                "texto_completo": bloco,
                "email_message_id": f"{base_id}_pub{idx}_{cnj or 'sem-cnj'}",
                "_email_base_id": base_id,
                "_publicacao_idx": idx,
            })
    return expandidos


def _bloco_para_item(item: dict[str, Any]) -> str:
    texto = item.get("texto_completo") or item.get("texto_resumo") or ""
    blocos = _split_blocos_publicacao(texto)
    cnj = _normalizar_cnj(item.get("numero_cnj"))
    if cnj:
        for bloco in blocos:
            if cnj in _normalizar_cnj(bloco):
                return bloco
    return blocos[0] if len(blocos) == 1 else _limpar_texto(texto)


def _url_do_bloco(bloco: str, fallback: str | None) -> str | None:
    match = re.search(r"https?://\S+", bloco)
    if not match:
        return fallback
    return match.group(0).rstrip(").,")


def _tribunal_do_bloco(bloco: str, fallback: str | None) -> str | None:
    texto = bloco.upper()
    if "TRF2" in texto:
        return "TRF2"
    if "TJSP" in texto or "SÃO PAULO" in texto or "SAO PAULO" in texto:
        return "TJSP"
    if "TJES" in texto or "ESPIRITO SANTO" in texto or "ESPÍRITO SANTO" in texto:
        return "TJES"
    if "TJRJ" in texto or "RIO DE JANEIRO" in texto:
        return "TJRJ"
    return fallback


def _preparar_item_gmail(item: dict[str, Any]) -> dict[str, Any]:
    bloco = _bloco_para_item(item)
    if "Sem publicações nesta edição." in (item.get("texto_resumo") or ""):
        return {
            **item,
            "texto_resumo": "Sem publicações nesta edição.",
            "texto_completo": "Sem publicações nesta edição.",
        }
    resumo = _conteudo_relevante(bloco)[:600].strip()
    return {
        **item,
        "texto_resumo": resumo,
        "texto_completo": _quebrar_linhas_publicacao(bloco),
        "url_fonte": _url_do_bloco(bloco, item.get("url_fonte")),
        "tribunal": _tribunal_do_bloco(bloco, item.get("tribunal")),
    }


def _resumo_dez_palavras(texto: str | None) -> str:
    relevante = _conteudo_relevante(texto)
    comandos = re.search(
        r"((?:DEFIRO|INDEFIRO|INTIME-SE|Intimem-se|NOTIFIQUE-SE|CIENTIFIQUE-SE|REMETAM-SE|pauta de julgamento|sess[aã]o virtual|prazo de \d+)[^.]{0,180})",
        relevante,
        flags=re.IGNORECASE,
    )
    base = comandos.group(1) if comandos else relevante
    palavras = re.findall(r"[A-Za-zÀ-ÿ0-9ºª-]+", _limpar_texto(base))
    if not palavras:
        return "Sem resumo disponível"
    return " ".join(palavras[:10])


def _extrair_data_publicacao(item: dict[str, Any]) -> date:
    texto = f"{item.get('texto_completo') or ''} {item.get('texto_resumo') or ''}"
    padroes = [
        r"Data de Publica(?:ç|c)[aã]o[:\s]+(\d{2}/\d{2}/\d{4})",
        r"Data de Disponibiliza(?:ç|c)[aã]o[:\s]+(\d{2}/\d{2}/\d{4})",
        r"\b(?:DJES|DJSP|DJRJ|DJU)\s+(\d{2}/\d{2}/\d{2,4})",
    ]
    for padrao in padroes:
        match = re.search(padrao, texto, re.IGNORECASE)
        if not match:
            continue
        raw = match.group(1)
        try:
            fmt = "%d/%m/%y" if len(raw.rsplit("/", 1)[-1]) == 2 else "%d/%m/%Y"
            return datetime.strptime(raw, fmt).date()
        except ValueError:
            continue
    data = item.get("data_publicacao")
    if isinstance(data, date):
        return data
    if isinstance(data, str):
        try:
            return date.fromisoformat(data)
        except ValueError:
            pass
    return date.today()


def _publicacao_tem_conteudo(pub: Publicacao) -> bool:
    return bool(pub.numero_cnj or (pub.texto_resumo and "Sem publicações" not in pub.texto_resumo))


def _bloco_visivel_publicacao(pub: Publicacao) -> str:
    texto = pub.texto_completo or pub.texto_resumo or ""
    if _email_id_tem_contador_publicacao(pub.email_message_id):
        return texto
    if not pub.numero_cnj:
        return texto
    bloco = _bloco_para_item({
        "texto_completo": texto,
        "texto_resumo": pub.texto_resumo,
        "numero_cnj": pub.numero_cnj,
    })
    principal = _normalizar_cnj(_cnj_principal_do_bloco(bloco))
    if principal and principal == _normalizar_cnj(pub.numero_cnj):
        return _quebrar_linhas_publicacao(bloco)
    return texto


def _filtrar_publicacoes_visiveis(publicacoes: list[Publicacao]) -> list[Publicacao]:
    bases_com_contador = {
        _email_base_id(pub.email_message_id)
        for pub in publicacoes
        if _email_id_tem_contador_publicacao(pub.email_message_id)
    }
    bases_com_contador.discard(None)
    datas_com_publicacao = {
        pub.data_publicacao
        for pub in publicacoes
        if _publicacao_tem_conteudo(pub)
    }
    vistos_sem_publicacao: set[date] = set()
    visiveis: list[Publicacao] = []
    for pub in publicacoes:
        base_id = _email_base_id(pub.email_message_id)
        if base_id in bases_com_contador and not _email_id_tem_contador_publicacao(pub.email_message_id):
            continue
        if not _publicacao_tem_conteudo(pub):
            if pub.data_publicacao in datas_com_publicacao:
                continue
            if pub.data_publicacao in vistos_sem_publicacao:
                continue
            vistos_sem_publicacao.add(pub.data_publicacao)
        if pub.numero_cnj and not _email_id_tem_contador_publicacao(pub.email_message_id):
            bloco = _bloco_visivel_publicacao(pub)
            principal = _normalizar_cnj(_cnj_principal_do_bloco(bloco))
            if principal and principal != _normalizar_cnj(pub.numero_cnj):
                continue
        visiveis.append(pub)
    return visiveis


def _processo_por_cnj(db: Session, numero_cnj: str | None) -> Processo | None:
    cnj = _normalizar_cnj(numero_cnj)
    if not cnj:
        return None
    return next(
        (
            processo
            for processo in db.query(Processo).options(joinedload(Processo.cliente)).all()
            if _normalizar_cnj(processo.numero_cnj) == cnj
        ),
        None,
    )


def _vincular_processo(db: Session, item: dict[str, Any]) -> uuid.UUID | None:
    processo = _processo_por_cnj(db, item.get("numero_cnj"))
    return processo.id if processo else None


def _inserir_publicacoes_gmail(itens: list[dict[str, Any]], db: Session) -> tuple[int, int, int, int]:
    inseridas = duplicatas = erros = sem_publicacoes = 0
    itens_expandidos = _expandir_itens_por_contador(itens)
    bases_processadas = {
        item.get("_email_base_id")
        for item in itens_expandidos
        if item.get("_email_base_id")
    }
    cnjs_por_base: dict[str, set[str]] = defaultdict(set)
    for item in itens_expandidos:
        base_id = item.get("_email_base_id")
        cnj_norm = _normalizar_cnj(item.get("numero_cnj"))
        if base_id and cnj_norm:
            cnjs_por_base[base_id].add(cnj_norm)

    for base_id in bases_processadas:
        antigos = (
            db.query(Publicacao)
            .filter(Publicacao.fonte == "gmail")
            .filter(Publicacao.email_message_id.like(f"{base_id}_%"))
            .all()
        )
        for antigo in antigos:
            email_id = antigo.email_message_id or ""
            is_novo_formato = re.search(r"_pub\d+_", email_id) is not None
            cnj_norm = _normalizar_cnj(antigo.numero_cnj)
            if not is_novo_formato and cnj_norm and cnj_norm not in cnjs_por_base.get(base_id, set()) and not antigo.prazo_id:
                db.delete(antigo)

    for raw_item in itens_expandidos:
        try:
            item = _preparar_item_gmail(raw_item)
            email_id = item.get("email_message_id")
            existe = None
            if email_id:
                existe = db.query(Publicacao).filter(Publicacao.email_message_id == email_id).first()
                if not existe and item.get("_email_base_id") and item.get("numero_cnj"):
                    legacy_id = f"{item['_email_base_id']}_{item['numero_cnj']}"
                    existe = db.query(Publicacao).filter(Publicacao.email_message_id == legacy_id).first()
                    if existe:
                        existe.email_message_id = email_id
            if existe:
                texto_resumo = _limpar_texto(item.get("texto_resumo"))
                texto_completo = _limpar_texto(item.get("texto_completo"))
                texto_mudou = False
                for attr, valor in (
                    ("texto_resumo", texto_resumo),
                    ("texto_completo", texto_completo),
                    ("tribunal", item.get("tribunal")),
                    ("url_fonte", item.get("url_fonte")),
                    ("data_publicacao", _extrair_data_publicacao(item)),
                ):
                    if valor and getattr(existe, attr) != valor:
                        setattr(existe, attr, valor)
                        texto_mudou = texto_mudou or attr in {"texto_resumo", "texto_completo"}
                processo_id = item.get("processo_id") or _vincular_processo(db, item)
                if processo_id and existe.processo_id != processo_id:
                    existe.processo_id = processo_id
                if texto_mudou:
                    existe.analise_ia = None
                db.add(existe)
                duplicatas += 1
                continue

            texto_resumo = _limpar_texto(item.get("texto_resumo"))
            texto_completo = _limpar_texto(item.get("texto_completo"))
            if texto_resumo == "Sem publicações nesta edição.":
                sem_publicacoes += 1

            processo_id = item.get("processo_id") or _vincular_processo(db, item)
            pub = Publicacao(
                fonte="gmail",
                data_publicacao=_extrair_data_publicacao(item),
                numero_cnj=item.get("numero_cnj"),
                tipo_ato=item.get("tipo_ato") or "outro",
                tribunal=item.get("tribunal"),
                texto_resumo=texto_resumo,
                texto_completo=texto_completo,
                email_message_id=email_id,
                processo_id=processo_id,
                url_fonte=item.get("url_fonte"),
            )
            db.add(pub)
            inseridas += 1
        except Exception:
            erros += 1
    db.commit()
    return inseridas, duplicatas, erros, sem_publicacoes


def _prazo_payload(pub: Publicacao, prazo: Prazo | None) -> dict[str, Any] | None:
    if not prazo:
        return None
    return {
        "id": str(prazo.id),
        "tipo": prazo.tipo,
        "descricao": prazo.descricao,
        "peca_necessaria": prazo.peca_necessaria,
        "data_limite": prazo.data_limite.isoformat() if prazo.data_limite else None,
        "status": prazo.status,
        "dias_prazo": prazo.dias_prazo,
        "tipo_contagem": prazo.tipo_contagem,
    }


def _publicacao_payload(pub: Publicacao) -> dict[str, Any]:
    processo = pub.processo
    cliente = processo.cliente if processo else None
    texto_visivel = _bloco_visivel_publicacao(pub)
    analise: dict[str, Any] = {}
    if pub.analise_ia:
        try:
            analise = json.loads(pub.analise_ia)
        except Exception:
            analise = {}
    resumo_visivel = _conteudo_relevante(texto_visivel) or pub.texto_resumo
    resumo_fonte = analise.get("resumo") or resumo_visivel
    detalhes = _extrair_detalhes_publicacao(texto_visivel or pub.texto_resumo)
    return {
        "id": str(pub.id),
        "data_publicacao": pub.data_publicacao.isoformat(),
        "numero_cnj": pub.numero_cnj,
        "cliente": cliente.nome if cliente else None,
        "cliente_sugerido": None if cliente else _cliente_sugerido(texto_visivel or pub.texto_resumo),
        "processo_id": str(pub.processo_id) if pub.processo_id else None,
        "tribunal": pub.tribunal,
        "publicado_em_nome_de": LUCAS_GMAIL,
        "resumo_curto": _resumo_dez_palavras(resumo_fonte),
        "texto_resumo": resumo_visivel,
        "texto_completo": texto_visivel,
        "texto_relevante": _quebrar_linhas_publicacao(_conteudo_relevante(texto_visivel or pub.texto_resumo)),
        "detalhes": detalhes,
        "tem_publicacao": _publicacao_tem_conteudo(pub),
        "url_fonte": pub.url_fonte,
        "analise_ia": analise or None,
        "prazo": _prazo_payload(pub, pub.prazo),
        "created_at": pub.created_at.isoformat() if pub.created_at else None,
    }


def _query_publicacoes(db: Session, data_inicio: date | None = None, data_fim: date | None = None):
    q = (
        db.query(Publicacao)
        .options(
            joinedload(Publicacao.processo).joinedload(Processo.cliente),
            joinedload(Publicacao.prazo),
        )
        .filter(Publicacao.fonte == "gmail")
        .filter(Publicacao.email_message_id.isnot(None))
    )
    if data_inicio:
        q = q.filter(Publicacao.data_publicacao >= data_inicio)
    if data_fim:
        q = q.filter(Publicacao.data_publicacao <= data_fim)
    return q.order_by(Publicacao.data_publicacao.desc(), Publicacao.created_at.desc())


def _refresh_google_tokens(tokens: dict) -> dict:
    import os

    resp = httpx.post(
        "https://oauth2.googleapis.com/token",
        data={
            "refresh_token": tokens.get("refresh_token", ""),
            "client_id": os.getenv("GOOGLE_CLIENT_ID", ""),
            "client_secret": os.getenv("GOOGLE_CLIENT_SECRET", ""),
            "grant_type": "refresh_token",
        },
        timeout=15,
    )
    if resp.is_success:
        refreshed = {**tokens, **resp.json()}
        save_master_google_tokens(refreshed)
        return refreshed
    return tokens


@router.get("/gmail/status")
def gmail_status():
    tokens = load_master_google_tokens()
    if not tokens:
        return {"conectado": False, "email": None, "email_esperado": LUCAS_GMAIL, "ok": False}
    email = tokens.get("email")
    try:
        headers = {"Authorization": f"Bearer {tokens.get('access_token', '')}"}
        resp = httpx.get("https://gmail.googleapis.com/gmail/v1/users/me/profile", headers=headers, timeout=10)
        if resp.status_code == 401 and tokens.get("refresh_token"):
            tokens = _refresh_google_tokens(tokens)
            headers = {"Authorization": f"Bearer {tokens.get('access_token', '')}"}
            resp = httpx.get("https://gmail.googleapis.com/gmail/v1/users/me/profile", headers=headers, timeout=10)
        if resp.is_success:
            email = resp.json().get("emailAddress")
            if email:
                tokens["email"] = email
                save_master_google_tokens(tokens)
    except Exception:
        pass
    return {
        "conectado": bool(tokens),
        "email": email,
        "email_esperado": LUCAS_GMAIL,
        "ok": (email or "").lower() == LUCAS_GMAIL,
    }


@router.post("/gmail/sync", response_model=SyncDiario2Result)
def sync_gmail_diario2(days_back: int = Query(7, ge=1, le=60), db: Session = Depends(get_db)):
    status_info = gmail_status()
    if not status_info.get("conectado"):
        raise HTTPException(status_code=400, detail="Conecte o Gmail do Lucas antes de importar.")
    if not status_info.get("ok"):
        raise HTTPException(
            status_code=400,
            detail=f"Conta conectada: {status_info.get('email') or 'desconhecida'}. Conecte {LUCAS_GMAIL}.",
        )
    itens = sincronizar_gmail(days_back=days_back)
    ins, dup, err, sem = _inserir_publicacoes_gmail(itens, db)
    return SyncDiario2Result(
        inseridas=ins,
        duplicatas=dup,
        erros=err,
        sem_publicacoes=sem,
        mensagem=f"Diário 2: {ins} nova(s), {dup} já existentes, {sem} aviso(s) sem publicação.",
    )


@router.get("/")
def listar_diario2(
    days_back: int = Query(30, ge=1, le=180),
    db: Session = Depends(get_db),
):
    inicio = date.today() - timedelta(days=days_back)
    publicacoes = _filtrar_publicacoes_visiveis(_query_publicacoes(db, data_inicio=inicio).all())
    grupos: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for pub in publicacoes:
        grupos[pub.data_publicacao.isoformat()].append(_publicacao_payload(pub))
    return {
        "dias": [
            {"data": data_pub, "publicacoes": itens}
            for data_pub, itens in sorted(grupos.items(), reverse=True)
        ]
    }


@router.post("/{pub_id}/analisar")
def analisar_diario2(pub_id: uuid.UUID, db: Session = Depends(get_db)):
    pub = db.query(Publicacao).filter(Publicacao.id == pub_id).first()
    if not pub:
        raise HTTPException(status_code=404, detail="Publicação não encontrada")
    texto = pub.texto_completo or pub.texto_resumo or ""
    if not texto or "Sem publicações" in texto:
        raise HTTPException(status_code=400, detail="Não há texto de publicação para analisar.")
    analise = analisar_publicacao(texto)
    pub.analise_ia = json.dumps(analise, ensure_ascii=False)
    if analise.get("numero_cnj") and not pub.numero_cnj:
        pub.numero_cnj = analise["numero_cnj"]
    if not pub.processo_id:
        processo = _processo_por_cnj(db, pub.numero_cnj or analise.get("numero_cnj"))
        if processo:
            pub.processo_id = processo.id
    db.commit()
    db.refresh(pub)
    return _publicacao_payload(pub)


@router.post("/{pub_id}/criar-prazo", status_code=status.HTTP_201_CREATED)
def criar_prazo_diario2(pub_id: uuid.UUID, payload: Diario2PrazoRequest, db: Session = Depends(get_db)):
    pub = db.query(Publicacao).filter(Publicacao.id == pub_id).first()
    if not pub:
        raise HTTPException(status_code=404, detail="Publicação não encontrada")
    processo_id = payload.processo_id or pub.processo_id
    if not processo_id:
        raise HTTPException(status_code=400, detail="Vincule a publicação a um processo antes de criar prazo.")
    processo = db.query(Processo).filter(Processo.id == processo_id).first()
    if not processo:
        raise HTTPException(status_code=404, detail="Processo não encontrado")
    data_limite, data_limite_sf = calcular_prazo(
        db=db,
        data_publicacao=pub.data_publicacao,
        dias=payload.dias_prazo,
        estado=processo.estado if processo.estado != "outro" else "SP",
        tipo_contagem=payload.tipo_contagem,
    )
    prazo = Prazo(
        processo_id=processo.id,
        tipo=payload.tipo,
        descricao=payload.descricao or pub.texto_resumo or "",
        peca_necessaria=payload.peca_necessaria,
        responsavel=payload.responsavel,
        data_publicacao=pub.data_publicacao,
        dias_prazo=payload.dias_prazo,
        tipo_contagem=payload.tipo_contagem,
        data_limite=data_limite,
        data_limite_sem_feriado=data_limite_sf,
        status="pendente",
    )
    db.add(prazo)
    db.flush()
    pub.processo_id = processo.id
    pub.prazo_id = prazo.id
    pub.gera_prazo = True
    db.commit()
    db.refresh(pub)
    return _publicacao_payload(pub)


@router.patch("/{pub_id}/prazo-status")
def atualizar_status_prazo_diario2(pub_id: uuid.UUID, payload: Diario2StatusPrazoRequest, db: Session = Depends(get_db)):
    pub = db.query(Publicacao).filter(Publicacao.id == pub_id).first()
    if not pub or not pub.prazo_id:
        raise HTTPException(status_code=404, detail="Prazo da publicação não encontrado")
    if payload.status not in {"pendente", "cumprido", "perdido"}:
        raise HTTPException(status_code=400, detail="Status inválido")
    prazo = db.query(Prazo).filter(Prazo.id == pub.prazo_id).first()
    if not prazo:
        raise HTTPException(status_code=404, detail="Prazo não encontrado")
    prazo.status = payload.status
    db.commit()
    db.refresh(pub)
    return _publicacao_payload(pub)


@router.get("/relembre")
def relembre_diario2(days_back: int = Query(7, ge=1, le=60), db: Session = Depends(get_db)):
    inicio = date.today() - timedelta(days=days_back)
    publicacoes = [
        pub
        for pub in _filtrar_publicacoes_visiveis(_query_publicacoes(db, data_inicio=inicio).all())
        if _publicacao_tem_conteudo(pub)
    ]
    itens = []
    for pub in publicacoes:
        if not pub.analise_ia:
            try:
                analise = analisar_publicacao(pub.texto_completo or pub.texto_resumo or "")
                pub.analise_ia = json.dumps(analise, ensure_ascii=False)
            except Exception:
                pass
        payload = _publicacao_payload(pub)
        itens.append({
            "data_publicacao": payload["data_publicacao"],
            "numero_cnj": payload["numero_cnj"],
            "cliente": payload["cliente"],
            "tribunal": payload["tribunal"],
            "resumo_curto": payload["resumo_curto"],
            "tem_prazo": bool(payload["prazo"]),
            "prazo": payload["prazo"],
        })
    db.commit()
    return {"days_back": days_back, "total": len(itens), "itens": itens}


def sync_diario2_job(days_back: int = 7) -> SyncDiario2Result:
    from app.database import SessionLocal

    db = SessionLocal()
    try:
        itens = sincronizar_gmail(days_back=days_back)
        ins, dup, err, sem = _inserir_publicacoes_gmail(itens, db)
        return SyncDiario2Result(
            inseridas=ins,
            duplicatas=dup,
            erros=err,
            sem_publicacoes=sem,
            mensagem=f"Diário 2 automático: {ins} nova(s), {dup} já existentes, {sem} aviso(s) sem publicação.",
        )
    finally:
        db.close()
