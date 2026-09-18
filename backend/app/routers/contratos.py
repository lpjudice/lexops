import uuid
from pathlib import Path

from fastapi import APIRouter, Depends, File, HTTPException, Request, UploadFile, status
from sqlalchemy.orm import Session

from app.database import get_db
from app.dependencies import get_current_user
from app.models.contrato import Contrato, PoderesTemplate, Signatario
from app.schemas.contrato import (
    AplicarContratantesRequest, ContratoCreate, ContratoOut, ContratoUpdate,
    GerarPdfRequest, GerarProcuracaoRequest, PoderesTemplateCreate, PoderesTemplateOut,
    SignatarioCreate, SignatarioOut,
)
from app.services import clicksign

UPLOADS_DIR = Path("/app/uploads/contratos")
UPLOADS_DIR.mkdir(parents=True, exist_ok=True)

router = APIRouter(prefix="/contratos", tags=["contratos"],
                   dependencies=[Depends(get_current_user)])

# Router SEM autenticação — só pro webhook do ClickSign, que não manda nosso token.
# (O router principal acima aplica get_current_user a tudo; esse callback externo
# precisa ficar fora dele. Se CLICKSIGN_WEBHOOK_SECRET estiver setado, exige
# ?secret=... na URL configurada no painel do ClickSign.)
router_publico = APIRouter(prefix="/contratos", tags=["contratos"])


def _pasta_drive(tipo_documento: str) -> str:
    """Nome da pasta no Drive (cliente e mestra) conforme o tipo de documento."""
    return "Procurações" if tipo_documento == "procuracao" else "Contratos"


def _duplicar_para_drive(
    db: Session, contrato: Contrato, conteudo: bytes, nome_arquivo: str,
    mimetype: str = "application/pdf", converter_html_para_google_docs: bool = False,
) -> tuple[str | None, str | None]:
    """
    Sobe um arquivo (PDF final assinado, ou o PDF/versão editável gerados em
    rascunho) tanto pra pasta do cliente (LexOps/{cliente}/Contratos ou
    /Procurações) quanto pra pasta mestra correspondente (LexOps/Contratos/
    {cliente} ou LexOps/Procurações/{cliente}), que reúne todos os documentos
    daquele tipo. Retorna (link_cliente, link_master); qualquer um pode vir
    None se o Drive não estiver conectado ou o upload falhar.
    """
    from app.models.cliente import Cliente
    from app.services.google_drive import upload_arquivo, upload_arquivo_raiz

    cliente = db.query(Cliente).filter(Cliente.id == contrato.cliente_id).first()
    if not cliente:
        return None, None

    pasta = _pasta_drive(contrato.tipo_documento)
    link_cliente = None
    link_master = None
    try:
        link_cliente = upload_arquivo(
            conteudo, nome_arquivo, cliente.nome, pasta,
            mimetype=mimetype, converter_html_para_google_docs=converter_html_para_google_docs,
        )
    except Exception:
        pass
    try:
        link_master = upload_arquivo_raiz(
            conteudo, nome_arquivo, subpath=[pasta, cliente.nome],
            mimetype=mimetype, converter_html_para_google_docs=converter_html_para_google_docs,
        )
    except Exception:
        pass
    return link_cliente, link_master


def _parse_iso(ts: str | None):
    """Converte um timestamp ISO do ClickSign em datetime (tolerante ao sufixo 'Z')."""
    if not ts:
        return None
    from datetime import datetime
    try:
        return datetime.fromisoformat(ts.replace("Z", "+00:00"))
    except Exception:
        return None


def _extrair_assinados(doc: dict) -> tuple[dict, dict]:
    """
    A partir da resposta do GET documento do ClickSign, retorna dois mapas
    (por signer_key e por email minúsculo) apontando para o timestamp de
    assinatura (ISO string) — a presença da chave já indica que assinou.

    Combina dois sinais para robustez: o objeto ``signature`` presente em cada
    signer que já assinou e os eventos ``name == "sign"``.
    """
    por_key: dict[str, str | None] = {}
    por_email: dict[str, str | None] = {}

    for s in doc.get("signers") or []:
        if s.get("signature"):
            sig_obj = s.get("signature") or {}
            ts = sig_obj.get("signed_at") or sig_obj.get("created_at")
            if s.get("key"):
                por_key[s["key"]] = ts
            if s.get("email"):
                por_email[s["email"].lower()] = ts

    for ev in doc.get("events") or []:
        if (ev.get("name") or "").lower() != "sign":
            continue
        ts = ev.get("occurred_at")
        data = ev.get("data") or {}
        candidatos = []
        if isinstance(data.get("signer"), dict):
            candidatos.append(data["signer"])
        for sg in data.get("signers") or []:
            if isinstance(sg, dict):
                candidatos.append(sg)
        if isinstance(data.get("user"), dict):
            candidatos.append(data["user"])
        for cand in candidatos:
            if cand.get("key"):
                por_key.setdefault(cand["key"], ts)
            if cand.get("email"):
                por_email.setdefault(cand["email"].lower(), ts)

    return por_key, por_email


# ── CRUD básico ───────────────────────────────────────────────────────────────

@router.get("/", response_model=list[ContratoOut])
def listar_contratos(
    cliente_id: uuid.UUID | None = None,
    db: Session = Depends(get_db),
):
    q = db.query(Contrato)
    if cliente_id:
        q = q.filter(Contrato.cliente_id == cliente_id)
    return q.order_by(Contrato.created_at.desc()).all()


@router.post("/", response_model=ContratoOut, status_code=status.HTTP_201_CREATED)
def criar_contrato(data: ContratoCreate, db: Session = Depends(get_db)):
    contrato = Contrato(**data.model_dump())
    db.add(contrato)
    db.commit()
    db.refresh(contrato)
    return contrato


@router.get("/pasta-mestra")
def obter_pasta_mestra(tipo_documento: str = "contrato"):
    """Link da pasta mestra na raiz do Drive (duplica todos os documentos finalizados
    daquele tipo — /Contratos ou /Procurações)."""
    from app.services.google_drive import get_folder_link_raiz
    return {"link": get_folder_link_raiz([_pasta_drive(tipo_documento)])}


_TEMPLATE_PROCURACAO_NOME = "Modelo de Procuração (editável)"


@router.get("/template-procuracao")
def obter_template_procuracao():
    """
    Link de um Google Doc modelo da procuração (com dados de exemplo), pra
    consultar/editar o padrão visual sem depender de nenhum contrato específico.
    Reaproveita o arquivo se já existir na pasta mestra /Procurações — só cria
    da primeira vez que alguém pedir.
    """
    from app.services.google_drive import (
        drive_disponivel, resolver_pasta_id_raiz, listar_filhos, upload_arquivo_raiz,
    )
    if not drive_disponivel():
        return {"link": None}

    folder_id = resolver_pasta_id_raiz([_pasta_drive("procuracao")])
    if not folder_id:
        return {"link": None}

    filhos = listar_filhos(folder_id) or []
    existente = next((f for f in filhos if f.get("name") == _TEMPLATE_PROCURACAO_NOME), None)
    if existente and existente.get("web_view_link"):
        return {"link": existente["web_view_link"]}

    from app.services.procuracao_pdf import gerar_procuracao_html
    html_bytes = gerar_procuracao_html(
        outorgantes=[{
            "tipo": "PF", "nome": "Nome do Outorgante", "nacionalidade": "brasileiro(a)",
            "estado_civil": "[estado civil]", "profissao": "[profissão]",
            "cpf_cnpj": "[CPF]", "endereco": "[endereço completo]", "email": "[email]",
        }],
        outorgados=[{"nome": "Nome do Outorgado (advogado)", "oab": "[OAB]", "oab_uf": "ES", "cpf": "[CPF]"}],
        endereco_escritorio="Av. Desembargador Sampaio, n. 300, Praia do Canto, Vitória/ES - CEP 29.055-250",
        finalidade="",
    )
    link = upload_arquivo_raiz(
        html_bytes, _TEMPLATE_PROCURACAO_NOME, [_pasta_drive("procuracao")],
        mimetype="text/html", converter_html_para_google_docs=True,
    )
    return {"link": link}


# ── Templates de poderes (substituem a cláusula ad judicia padrão) ─────────────

@router.get("/poderes-templates", response_model=list[PoderesTemplateOut])
def listar_poderes_templates(db: Session = Depends(get_db)):
    return db.query(PoderesTemplate).order_by(PoderesTemplate.nome).all()


@router.post("/poderes-templates", response_model=PoderesTemplateOut, status_code=status.HTTP_201_CREATED)
def criar_poderes_template(data: PoderesTemplateCreate, db: Session = Depends(get_db)):
    template = PoderesTemplate(**data.model_dump())
    db.add(template)
    db.commit()
    db.refresh(template)
    return template


@router.delete("/poderes-templates/{template_id}", status_code=status.HTTP_204_NO_CONTENT)
def remover_poderes_template(template_id: uuid.UUID, db: Session = Depends(get_db)):
    template = db.query(PoderesTemplate).filter(PoderesTemplate.id == template_id).first()
    if not template:
        raise HTTPException(status_code=404, detail="Template não encontrado")
    db.delete(template)
    db.commit()


@router.get("/{contrato_id}", response_model=ContratoOut)
def obter_contrato(contrato_id: uuid.UUID, db: Session = Depends(get_db)):
    c = db.query(Contrato).filter(Contrato.id == contrato_id).first()
    if not c:
        raise HTTPException(status_code=404, detail="Contrato não encontrado")
    return c


@router.patch("/{contrato_id}", response_model=ContratoOut)
def atualizar_contrato(
    contrato_id: uuid.UUID, data: ContratoUpdate, db: Session = Depends(get_db)
):
    c = db.query(Contrato).filter(Contrato.id == contrato_id).first()
    if not c:
        raise HTTPException(status_code=404, detail="Contrato não encontrado")
    for field, value in data.model_dump(exclude_unset=True).items():
        setattr(c, field, value)
    db.commit()
    db.refresh(c)
    return c


@router.delete("/{contrato_id}", status_code=status.HTTP_204_NO_CONTENT)
def deletar_contrato(contrato_id: uuid.UUID, db: Session = Depends(get_db)):
    c = db.query(Contrato).filter(Contrato.id == contrato_id).first()
    if not c:
        raise HTTPException(status_code=404, detail="Contrato não encontrado")
    try:
        from app.models.cliente import Cliente
        from app.services.google_drive import deletar_arquivo
        cliente = db.query(Cliente).filter(Cliente.id == c.cliente_id).first()
        if cliente:
            for arq in c.arquivos or []:
                filename = arq.get("filename")
                if filename:
                    deletar_arquivo(cliente.nome, _pasta_drive(c.tipo_documento), filename)
    except Exception:
        pass
    # Marcar honorários vinculados como órfãos para validação
    from app.models.financeiro import Honorario
    for h in db.query(Honorario).filter(Honorario.contrato_id == c.id).all():
        h.contrato_orfao = True
        h.contrato_id = None
    db.delete(c)
    db.commit()


# ── Upload de PDF (suporta múltiplos) ────────────────────────────────────────

@router.post("/{contrato_id}/upload", response_model=ContratoOut)
async def upload_pdf(
    contrato_id: uuid.UUID,
    arquivos: list[UploadFile] = File(...),
    db: Session = Depends(get_db),
):
    c = db.query(Contrato).filter(Contrato.id == contrato_id).first()
    if not c:
        raise HTTPException(status_code=404, detail="Contrato não encontrado")

    lista = list(c.arquivos or [])
    for arquivo in arquivos:
        if not arquivo.filename:
            continue
        nome_arquivo = f"{contrato_id}_{uuid.uuid4().hex[:8]}_{arquivo.filename}"
        destino = UPLOADS_DIR / nome_arquivo
        conteudo_bytes = arquivo.file.read()
        destino.write_bytes(conteudo_bytes)
        lista.append({"filename": arquivo.filename, "path": str(destino), "clicksign_key": None})
        # Mantém arquivo_path legado apontando para o primeiro arquivo
        if not c.arquivo_path:
            c.arquivo_path = str(destino)
        drive_link = None
        try:
            from app.models.cliente import Cliente
            cliente = db.query(Cliente).filter(Cliente.id == c.cliente_id).first()
            if cliente:
                from app.services.google_drive import upload_arquivo
                drive_link = upload_arquivo(conteudo_bytes, arquivo.filename, cliente.nome, _pasta_drive(c.tipo_documento))
        except Exception:
            pass
        if drive_link:
            lista[-1]["drive_link"] = drive_link

    c.arquivos = lista
    db.commit()
    db.refresh(c)
    return c


@router.delete("/{contrato_id}/arquivo", response_model=ContratoOut)
def remover_arquivo(
    contrato_id: uuid.UUID,
    filename: str,
    db: Session = Depends(get_db),
):
    """Remove um arquivo específico da lista de arquivos do contrato."""
    c = db.query(Contrato).filter(Contrato.id == contrato_id).first()
    if not c:
        raise HTTPException(status_code=404, detail="Contrato não encontrado")
    if c.status != "rascunho":
        raise HTTPException(status_code=400, detail="Não é possível remover arquivos após o envio")

    nova_lista = [a for a in (c.arquivos or []) if a.get("filename") != filename]
    # Tenta apagar o arquivo físico
    for arq in (c.arquivos or []):
        if arq.get("filename") == filename:
            try:
                Path(arq["path"]).unlink(missing_ok=True)
            except Exception:
                pass
            try:
                from app.models.cliente import Cliente
                from app.services.google_drive import deletar_arquivo
                cliente = db.query(Cliente).filter(Cliente.id == c.cliente_id).first()
                if cliente:
                    deletar_arquivo(cliente.nome, _pasta_drive(c.tipo_documento), filename)
            except Exception:
                pass
    c.arquivos = nova_lista
    c.arquivo_path = nova_lista[0]["path"] if nova_lista else None
    db.commit()
    db.refresh(c)
    return c


@router.get("/{contrato_id}/arquivo/{filename}")
def ver_arquivo(contrato_id: uuid.UUID, filename: str, db: Session = Depends(get_db)):
    """Serve o arquivo PDF para visualização."""
    from fastapi.responses import FileResponse
    c = db.query(Contrato).filter(Contrato.id == contrato_id).first()
    if not c:
        raise HTTPException(status_code=404, detail="Contrato não encontrado")
    for arq in (c.arquivos or []):
        if arq.get("filename") == filename:
            path = Path(arq["path"])
            if path.exists():
                return FileResponse(str(path), media_type="application/pdf", filename=filename)
    raise HTTPException(status_code=404, detail="Arquivo não encontrado")


# ── Leitura de contratantes por IA ───────────────────────────────────────────

def _so_digitos(v: str | None) -> str:
    return "".join(ch for ch in (v or "") if ch.isdigit())


def _primeiro_pdf_path(c: Contrato) -> Path | None:
    """Caminho local do PDF principal do contrato (para enviar à IA)."""
    for arq in (c.arquivos or []):
        p = Path(arq.get("path", ""))
        if p.exists() and p.suffix.lower() == ".pdf":
            return p
    if c.arquivo_path:
        p = Path(c.arquivo_path)
        if p.exists():
            return p
    return None


@router.post("/{contrato_id}/ler-contratantes")
def ler_contratantes(contrato_id: uuid.UUID, db: Session = Depends(get_db)):
    """
    Lê o PDF anexado ao contrato com a IA e retorna os contratantes extraídos,
    já com candidatos de cliente existente (match por CPF/CNPJ e por nome).
    NÃO grava nada — só devolve sugestões para a tela de revisão decidir.
    """
    from app.models.cliente import Cliente
    from app.services.ia_contrato import extrair_contratantes

    c = db.query(Contrato).filter(Contrato.id == contrato_id).first()
    if not c:
        raise HTTPException(status_code=404, detail="Contrato não encontrado")

    pdf = _primeiro_pdf_path(c)
    if not pdf:
        raise HTTPException(status_code=400, detail="Nenhum PDF anexado para ler. Faça o upload do contrato primeiro.")

    resultado = extrair_contratantes(pdf.read_bytes(), "application/pdf")
    if resultado.get("erro"):
        raise HTTPException(status_code=502, detail=resultado["erro"])

    todos = db.query(Cliente).all()
    saida = []
    for ext in resultado.get("contratantes", []):
        cpf_dig = _so_digitos(ext.get("cpf_cnpj"))
        nome_l = (ext.get("nome") or "").strip().lower()
        candidatos = []
        for cli in todos:
            match = None
            if cpf_dig and _so_digitos(cli.cpf_cnpj) == cpf_dig:
                match = "cpf"
            elif nome_l and cli.nome and (
                nome_l == cli.nome.strip().lower()
                or nome_l in cli.nome.strip().lower()
                or cli.nome.strip().lower() in nome_l
            ):
                match = "nome"
            if match:
                candidatos.append({
                    "id": str(cli.id), "nome": cli.nome, "tipo": cli.tipo,
                    "cpf_cnpj": cli.cpf_cnpj, "email": cli.email,
                    "incompleto": bool(cli.incompleto), "match": match,
                })
        # cpf antes de nome
        candidatos.sort(key=lambda x: 0 if x["match"] == "cpf" else 1)
        saida.append({"extraido": ext, "candidatos": candidatos})

    return {"contratantes": saida, "financeiro": resultado.get("financeiro") or {}}


# Limites das colunas de `clientes` (evita StringDataRightTruncation → 500 no commit).
# `endereco` é TEXT (sem limite). Mantido em sincronia com models/cliente.py.
_CLIENTE_MAXLEN = {"cpf_cnpj": 18, "email": 255, "telefone": 30, "estado_civil": 120, "profissao": 150}


def _cap(campo: str, valor: str) -> str:
    m = _CLIENTE_MAXLEN.get(campo)
    return valor[:m] if (m and valor) else valor


def _preencher_vazios(cli, dados: dict, db: Session) -> None:
    """Preenche apenas os campos VAZIOS do cliente a partir de `dados` (merge não-destrutivo)."""
    from app.models.cliente import Cliente
    cpf = _cap("cpf_cnpj", (dados.get("cpf_cnpj") or "").strip())
    if not cli.cpf_cnpj and cpf:
        ja = db.query(Cliente).filter(Cliente.cpf_cnpj == cpf, Cliente.id != cli.id).first()
        if not ja:
            cli.cpf_cnpj = cpf
    for campo in ("email", "telefone", "endereco", "estado_civil", "profissao"):
        valor = (dados.get(campo) or "").strip()
        if valor and not getattr(cli, campo, None):
            setattr(cli, campo, _cap(campo, valor))


def _parse_date(s: str | None):
    """'AAAA-MM-DD' → date, tolerante a vazio/erro."""
    if not s:
        return None
    from datetime import date as _date
    try:
        return _date.fromisoformat(str(s).strip()[:10])
    except Exception:
        return None


def _add_months(d, n: int):
    """Soma n meses a uma data, ajustando o dia ao último dia do mês quando preciso."""
    import calendar
    from datetime import date as _date
    m = d.month - 1 + n
    y = d.year + m // 12
    m = m % 12 + 1
    dia = min(d.day, calendar.monthrange(y, m)[1])
    return _date(y, m, dia)


def _dividir_parcelas(total: float, n: int, primeiro_venc):
    """Divide `total` em n parcelas mensais a partir de `primeiro_venc`.
    A última parcela absorve o arredondamento. Retorna [(valor, data_vencimento)]."""
    base = round(total / n, 2)
    out = []
    acumulado = 0.0
    for i in range(n):
        if i == n - 1:
            v = round(total - acumulado, 2)
        else:
            v = base
            acumulado = round(acumulado + base, 2)
        out.append((v, _add_months(primeiro_venc, i)))
    return out


def _upsert_honorario_do_contrato(db: Session, contrato: Contrato, fin) -> None:
    """
    Cria ou atualiza o Honorário vinculado ao contrato a partir dos dados financeiros
    lidos pela IA (mesmo espírito do lançamento automático do 'Gerar contrato'). Só age
    se houver valor fixo ou êxito. Atualiza o existente se já houver um para o contrato.
    """
    from datetime import date as _date
    from app.models.financeiro import Honorario, Parcela

    if not fin:
        return
    valor = fin.valor_honorarios
    tem_exito = bool(fin.tem_exito)
    if not valor and not tem_exito:
        return  # nada financeiro a lançar

    venc = _parse_date(fin.data_vencimento)
    dcont = _parse_date(fin.data_contrato)
    pct = fin.percentual_exito

    existente = db.query(Honorario).filter(Honorario.contrato_id == contrato.id).first()
    if existente:
        # Se já há cronograma (parcelas), o valor_total é derivado dele — pode ter sido
        # customizado manualmente (split não-prorata). Não deixa a releitura da IA
        # sobrescrever com o total "cru" do contrato.
        if valor and not existente.parcelas:
            existente.valor_total = valor
        if fin.valor_causa is not None:
            existente.valor_causa = fin.valor_causa
        if pct is not None:
            existente.percentual_exito = pct
        if tem_exito:
            existente.tipo = "exito"
        if venc:
            existente.data_vencimento = venc
        if dcont:
            existente.data_contrato = dcont
        if fin.condicao_pagamento:
            existente.observacoes = fin.condicao_pagamento
    else:
        h = Honorario(
            cliente_id=contrato.cliente_id,
            processo_id=contrato.processo_id,
            contrato_id=contrato.id,
            descricao="Honorários — contrato (lido por IA)",
            tipo="exito" if tem_exito else "fixo",
            valor_total=valor or 0,
            valor_causa=fin.valor_causa,
            percentual_exito=pct,
            data_contrato=dcont or _date.today(),
            data_vencimento=venc,
            observacoes=(fin.condicao_pagamento or None),
            pendente_assinatura=True,
        )
        db.add(h)
        db.flush()
        # Se o contrato indicar parcelamento (>1) e houver valor fixo e 1º vencimento,
        # gera o cronograma de parcelas (ajustável depois na tela do Financeiro).
        n = int(getattr(fin, "num_parcelas", None) or 0)
        if valor and n >= 2 and venc:
            for numero, (pv, pd) in enumerate(_dividir_parcelas(float(valor), n, venc), start=1):
                db.add(Parcela(honorario_id=h.id, numero=numero, valor=pv, data_vencimento=pd))


@router.post("/{contrato_id}/aplicar-contratantes", response_model=ContratoOut)
def aplicar_contratantes(
    contrato_id: uuid.UUID, body: AplicarContratantesRequest, db: Session = Depends(get_db)
):
    """
    Aplica as decisões da tela de revisão: atualiza clientes existentes (só campos
    vazios), cria novos (incompletos = pendentes de revisão), vincula o contrato ao
    contratante principal e anota os co-contratantes nas observações desse cliente.
    """
    from app.models.cliente import Cliente
    from app.routers.clientes import _gerar_projeto

    c = db.query(Contrato).filter(Contrato.id == contrato_id).first()
    if not c:
        raise HTTPException(status_code=404, detail="Contrato não encontrado")

    processados: list[tuple[Cliente, bool]] = []  # (cliente, is_principal)
    criados: list[Cliente] = []
    for dec in body.decisoes:
        if dec.acao == "ignorar":
            continue

        dados = dec.model_dump()
        if dec.acao == "atualizar":
            if not dec.cliente_id:
                raise HTTPException(status_code=400, detail=f"Cliente não informado para atualizar '{dec.nome}'.")
            cli = db.query(Cliente).filter(Cliente.id == dec.cliente_id).first()
            if not cli:
                raise HTTPException(status_code=404, detail=f"Cliente {dec.cliente_id} não encontrado.")
            _preencher_vazios(cli, dados, db)
        else:  # criar (mesma inicialização do POST /clientes: incompleto + projeto/worktree)
            nome_novo = dec.nome.strip()[:255]
            if not dec.ignorar_similares:
                from app.services.cliente_dedup import encontrar_similares
                similares = encontrar_similares(nome_novo, db)
                if similares:
                    raise HTTPException(
                        status_code=409,
                        detail={"tipo": "nome_similar", "nome": nome_novo, "similares": similares},
                    )
            projeto_nome, worktree_nome = _gerar_projeto(nome_novo)
            cli = Cliente(
                nome=nome_novo, tipo=dec.tipo, incompleto=True,
                projeto_nome=projeto_nome, worktree_nome=worktree_nome,
            )
            db.add(cli)
            db.flush()  # garante id p/ checagem de unicidade em _preencher_vazios
            _preencher_vazios(cli, dados, db)
            criados.append(cli)

        if dec.diferenciador and dec.diferenciador.strip():
            nota = f"[contrato] {dec.diferenciador.strip()}"
            cli.observacoes = (cli.observacoes + "\n" + nota).strip() if cli.observacoes else nota

        processados.append((cli, dec.principal))

    if not processados:
        raise HTTPException(status_code=400, detail="Nenhuma decisão aplicável (todos ignorados).")

    # Contratante principal: o marcado, senão o primeiro processado.
    principal = next((cli for cli, is_p in processados if is_p), processados[0][0])

    # Anota co-contratantes no cadastro do principal.
    outros = [cli.nome for cli, _ in processados if cli is not principal]
    if outros:
        nota = f"[contrato] Mesmo contrato de: {', '.join(outros)}"
        principal.observacoes = (principal.observacoes + "\n" + nota).strip() if principal.observacoes else nota

    if body.vincular_contrato:
        c.cliente_id = principal.id

    # Lança/atualiza o Honorário do contrato (opt-in na tela) — usa o cliente já vinculado.
    if body.lancar_financeiro:
        _upsert_honorario_do_contrato(db, c, body.financeiro)

    db.commit()

    # Cria as pastas no Drive dos clientes novos (best-effort, como no POST /clientes).
    for cli in criados:
        try:
            from app.services.google_drive import ensure_cliente_folder
            ensure_cliente_folder(cli.nome)
        except Exception:
            pass

    db.refresh(c)
    return c


# ── Geração de PDF do contrato ────────────────────────────────────────────────

@router.post("/{contrato_id}/gerar-pdf", response_model=ContratoOut)
async def gerar_pdf_contrato(
    contrato_id: uuid.UUID,
    body: GerarPdfRequest,
    db: Session = Depends(get_db),
):
    """Gera o PDF do contrato de honorários e o adiciona à lista de arquivos."""
    from datetime import date as date_type
    from app.services.contrato_pdf import gerar_contrato

    c = db.query(Contrato).filter(Contrato.id == contrato_id).first()
    if not c:
        raise HTTPException(status_code=404, detail="Contrato não encontrado")

    data_contrato = None
    if body.data_contrato:
        try:
            data_contrato = date_type.fromisoformat(body.data_contrato)
        except ValueError:
            pass

    pdf_bytes = gerar_contrato(
        contratante_nome=body.contratante_nome,
        contratante_qualificacao=body.contratante_qualificacao,
        contratante_cpf_cnpj=body.contratante_cpf_cnpj,
        contratante_endereco=body.contratante_endereco,
        contratante_email=body.contratante_email,
        objeto_tipo=body.objeto_tipo,
        objeto_texto_livre=body.objeto_texto_livre,
        valor_honorarios=body.valor_honorarios,
        data_vencimento=body.data_vencimento,
        condicao_pagamento=body.condicao_pagamento,
        percentual_exito=body.percentual_exito,
        data_contrato=data_contrato,
    )

    nome_arquivo = f"Contrato_{body.contratante_nome.replace(' ', '_')}_{contrato_id.hex[:8]}.pdf"
    destino = UPLOADS_DIR / nome_arquivo
    destino.write_bytes(pdf_bytes)

    drive_link = None
    try:
        from app.models.cliente import Cliente
        cliente = db.query(Cliente).filter(Cliente.id == c.cliente_id).first()
        if cliente:
            from app.services.google_drive import upload_arquivo
            drive_link = upload_arquivo(pdf_bytes, nome_arquivo, cliente.nome, "Contratos")
    except Exception:
        pass

    # Pré-preenchimento reverso: os dados do contrato preenchem os campos VAZIOS do
    # cadastro do cliente (nunca sobrescreve o que já existe). Assim, um cliente criado
    # "só com o nome" pelo próprio contrato já chega à revisão com CPF/e-mail/endereço.
    try:
        from app.models.cliente import Cliente
        cli = db.query(Cliente).filter(Cliente.id == c.cliente_id).first()
        if cli:
            mudou = False
            novo_cpf = (body.contratante_cpf_cnpj or "").strip()
            if not cli.cpf_cnpj and novo_cpf:
                # respeita a unicidade de cpf_cnpj
                ja_usado = db.query(Cliente).filter(
                    Cliente.cpf_cnpj == novo_cpf, Cliente.id != cli.id
                ).first()
                if not ja_usado:
                    cli.cpf_cnpj = novo_cpf
                    mudou = True
            novo_email = (body.contratante_email or "").strip()
            if not cli.email and novo_email:
                cli.email = novo_email
                mudou = True
            novo_end = (body.contratante_endereco or "").strip()
            if not cli.endereco and novo_end:
                cli.endereco = novo_end
                mudou = True
            if mudou:
                db.commit()
    except Exception:
        db.rollback()

    lista = list(c.arquivos or [])
    lista.append({"filename": nome_arquivo, "path": str(destino), "clicksign_key": None, "drive_link": drive_link})
    c.arquivos = lista
    c.arquivo_path = str(destino)
    db.commit()
    db.refresh(c)

    # Auto-cria/atualiza lançamento no financeiro vinculado a este contrato
    try:
        import re as _re
        from app.models.financeiro import Honorario
        from datetime import date as _date

        # Usa valor numérico se disponível, senão faz parse do texto
        if body.valor_honorarios_num is not None:
            valor_float = body.valor_honorarios_num
        else:
            raw = body.valor_honorarios or "0"
            valor_float = float(_re.sub(r'[^\d,]', '', raw).replace(',', '.') or '0')

        exito_pct_str = body.percentual_exito.strip() if body.percentual_exito else None
        eh_exito = bool(exito_pct_str and exito_pct_str not in ("0%", "0", "não haverá êxito"))

        # Parse percentual numérico
        pct_num = body.percentual_exito_num
        if pct_num is None and exito_pct_str:
            try:
                pct_num = float(exito_pct_str.replace('%', '').strip())
            except Exception:
                pct_num = None

        # Verifica se já há honorário vinculado a este contrato
        ja_existe = db.query(Honorario).filter(
            Honorario.contrato_id == contrato_id
        ).first()

        venc = None
        if body.data_vencimento:
            try:
                venc = _date.fromisoformat(body.data_vencimento)
            except Exception:
                pass

        if ja_existe:
            # Atualiza o existente (pode ter sido regenerado o PDF)
            if valor_float > 0:
                ja_existe.valor_total = valor_float
            if body.valor_causa is not None:
                ja_existe.valor_causa = body.valor_causa
            if pct_num is not None:
                ja_existe.percentual_exito = pct_num
            if venc:
                ja_existe.data_vencimento = venc
            db.commit()
        elif valor_float > 0 or eh_exito:
            descricao_h = f"Honorários — {body.objeto_tipo or body.objeto_texto_livre or 'Contrato'}"
            h = Honorario(
                cliente_id=c.cliente_id,
                processo_id=c.processo_id,
                contrato_id=contrato_id,
                descricao=descricao_h,
                tipo="exito" if eh_exito else "fixo",
                valor_total=valor_float,
                valor_causa=body.valor_causa,
                percentual_exito=pct_num,
                data_contrato=data_contrato or _date.today(),
                data_vencimento=venc,
                observacoes=f"Gerado automaticamente pelo contrato.",
                pendente_assinatura=True,  # pendente até confirmação de assinaturas
            )
            db.add(h)
            db.commit()
    except Exception:
        pass

    return c


# ── Geração de PDF da procuração ──────────────────────────────────────────────

@router.post("/{contrato_id}/gerar-procuracao", response_model=ContratoOut)
async def gerar_pdf_procuracao(
    contrato_id: uuid.UUID,
    body: GerarProcuracaoRequest,
    db: Session = Depends(get_db),
    usuario=Depends(get_current_user),
):
    """Gera o PDF da procuração e o adiciona à lista de arquivos. Mesma infra de
    upload/Drive do 'Gerar contrato', sem o lançamento automático no financeiro
    (procuração não tem honorários). Reeditar e gerar de novo SOBRESCREVE a versão
    anterior (arquivo local + Drive), em vez de duplicar — ver `doc_gerado_filename`."""
    from datetime import date as date_type, datetime, timezone
    from app.services.procuracao_pdf import gerar_procuracao, gerar_procuracao_html
    from app.services.google_drive import extrair_file_id, deletar_arquivo_por_id

    c = db.query(Contrato).filter(Contrato.id == contrato_id).first()
    if not c:
        raise HTTPException(status_code=404, detail="Contrato não encontrado")

    outorgantes_validos = [o for o in body.outorgantes if o.nome.strip()]
    if not outorgantes_validos:
        raise HTTPException(status_code=400, detail="Informe ao menos um outorgante.")

    def _parse_data(s: str) -> date_type | None:
        if not s:
            return None
        try:
            return date_type.fromisoformat(s)
        except ValueError:
            return None

    data_procuracao = _parse_data(body.data_procuracao)
    data_validade = _parse_data(body.data_validade)

    kwargs = dict(
        outorgantes=[o.model_dump() for o in body.outorgantes],
        outorgados=[o.model_dump() for o in body.outorgados],
        endereco_escritorio=body.endereco_escritorio,
        poderes_modo=body.poderes_modo,
        poderes_especiais=list(body.poderes_especiais),
        poderes_adicionais=body.poderes_adicionais,
        poderes_template_texto=body.poderes_template_texto,
        finalidade=body.finalidade,
        data_validade=data_validade,
        data_procuracao=data_procuracao,
    )
    pdf_bytes = gerar_procuracao(forcar_uma_pagina=body.forcar_uma_pagina, **kwargs)

    primeiro_nome = outorgantes_validos[0].nome
    nome_arquivo = f"Procuracao_{primeiro_nome.replace(' ', '_')}_{contrato_id.hex[:8]}.pdf"
    destino = UPLOADS_DIR / nome_arquivo
    destino.write_bytes(pdf_bytes)

    # Remove a versão anterior gerada pelo sistema (edição sobrescreve, não duplica).
    arquivos_atuais = list(c.arquivos or [])
    if c.doc_gerado_filename:
        anterior = next((a for a in arquivos_atuais if a.get("filename") == c.doc_gerado_filename), None)
        arquivos_atuais = [a for a in arquivos_atuais if a.get("filename") != c.doc_gerado_filename]
        if anterior and anterior.get("filename") != nome_arquivo:
            try:
                Path(anterior["path"]).unlink(missing_ok=True)
            except Exception:
                pass
        if anterior:
            for link_key in ("drive_link", "docs_link"):
                link = anterior.get(link_key)
                if not link:
                    continue
                try:
                    fid = extrair_file_id(link)
                    if fid:
                        deletar_arquivo_por_id(fid)
                except Exception:
                    pass

    # Sobe pra pasta do cliente (subpasta Procurações) E pra pasta mestra.
    drive_link, _ = _duplicar_para_drive(db, c, pdf_bytes, nome_arquivo)
    docs_link = None
    try:
        html_bytes = gerar_procuracao_html(forcar_uma_pagina=body.forcar_uma_pagina, **kwargs)
        nome_docs = f"{nome_arquivo[:-4]} (editável)"
        docs_link, _ = _duplicar_para_drive(
            db, c, html_bytes, nome_docs, mimetype="text/html", converter_html_para_google_docs=True,
        )
    except Exception:
        pass

    # Pré-preenchimento reverso (mesma lógica do contrato): preenche só campos vazios
    # do cliente vinculado ao contrato, a partir do PRIMEIRO outorgante.
    try:
        from app.models.cliente import Cliente
        cli = db.query(Cliente).filter(Cliente.id == c.cliente_id).first()
        primeiro = outorgantes_validos[0]
        if cli:
            mudou = False
            novo_cpf = (primeiro.cpf_cnpj or "").strip()
            if not cli.cpf_cnpj and novo_cpf:
                ja_usado = db.query(Cliente).filter(
                    Cliente.cpf_cnpj == novo_cpf, Cliente.id != cli.id
                ).first()
                if not ja_usado:
                    cli.cpf_cnpj = novo_cpf
                    mudou = True
            novo_email = (primeiro.email or "").strip()
            if not cli.email and novo_email:
                cli.email = novo_email
                mudou = True
            novo_end = (primeiro.endereco or "").strip()
            if not cli.endereco and novo_end:
                cli.endereco = novo_end
                mudou = True
            if primeiro.tipo == "PF":
                novo_ec = (primeiro.estado_civil or "").strip()
                if not cli.estado_civil and novo_ec:
                    cli.estado_civil = novo_ec
                    mudou = True
                nova_prof = (primeiro.profissao or "").strip()
                if not cli.profissao and nova_prof:
                    cli.profissao = nova_prof
                    mudou = True
            if mudou:
                db.commit()
    except Exception:
        db.rollback()

    arquivos_atuais.append({
        "filename": nome_arquivo, "path": str(destino), "clicksign_key": None,
        "drive_link": drive_link, "docs_link": docs_link,
    })
    c.arquivos = arquivos_atuais
    c.arquivo_path = str(destino)
    c.doc_gerado_filename = nome_arquivo
    c.procuracao_dados = body.model_dump()
    c.doc_gerado_por = getattr(usuario, "nome", None)
    c.doc_gerado_em = datetime.now(timezone.utc)
    db.commit()
    db.refresh(c)
    return c


# ── Signatários ───────────────────────────────────────────────────────────────

@router.post("/{contrato_id}/signatarios", response_model=SignatarioOut, status_code=status.HTTP_201_CREATED)
def adicionar_signatario(
    contrato_id: uuid.UUID, data: SignatarioCreate, db: Session = Depends(get_db)
):
    c = db.query(Contrato).filter(Contrato.id == contrato_id).first()
    if not c:
        raise HTTPException(status_code=404, detail="Contrato não encontrado")
    sig = Signatario(contrato_id=contrato_id, **data.model_dump())
    db.add(sig)
    db.commit()
    db.refresh(sig)
    return sig


@router.delete("/{contrato_id}/signatarios/{sig_id}", status_code=status.HTTP_204_NO_CONTENT)
def remover_signatario(contrato_id: uuid.UUID, sig_id: uuid.UUID, db: Session = Depends(get_db)):
    sig = db.query(Signatario).filter(
        Signatario.id == sig_id, Signatario.contrato_id == contrato_id
    ).first()
    if not sig:
        raise HTTPException(status_code=404, detail="Signatário não encontrado")
    db.delete(sig)
    db.commit()


@router.post("/{contrato_id}/signatarios/{sig_id}/lembrar")
def lembrar_signatario(contrato_id: uuid.UUID, sig_id: uuid.UUID, db: Session = Depends(get_db)):
    """Reenvia o e-mail de convite de assinatura do ClickSign (mesmo recurso do
    botão de lembrete no site deles)."""
    sig = db.query(Signatario).filter(
        Signatario.id == sig_id, Signatario.contrato_id == contrato_id
    ).first()
    if not sig:
        raise HTTPException(status_code=404, detail="Signatário não encontrado")
    if sig.status_assinatura == "assinado":
        raise HTTPException(status_code=400, detail="Este signatário já assinou.")
    if not sig.clicksign_request_key:
        raise HTTPException(status_code=400, detail="Este signatário ainda não foi enviado para assinatura.")
    if not clicksign.notificar_signatario(sig.clicksign_request_key):
        raise HTTPException(status_code=502, detail="Falha ao enviar lembrete pelo ClickSign.")
    return {"ok": True}


# ── Envio para ClickSign ──────────────────────────────────────────────────────

@router.post("/{contrato_id}/enviar", response_model=ContratoOut)
def enviar_para_assinatura(contrato_id: uuid.UUID, db: Session = Depends(get_db)):
    c = db.query(Contrato).filter(Contrato.id == contrato_id).first()
    if not c:
        raise HTTPException(status_code=404, detail="Contrato não encontrado")
    if not c.arquivo_path:
        raise HTTPException(status_code=400, detail="Faça upload do PDF antes de enviar")
    if not c.signatarios:
        raise HTTPException(status_code=400, detail="Adicione ao menos um signatário")

    # Determina lista de arquivos (usa arquivos JSONB se disponível, cai em arquivo_path legado)
    arquivos_para_enviar = list(c.arquivos or [])
    if not arquivos_para_enviar and c.arquivo_path:
        arquivos_para_enviar = [{"filename": Path(c.arquivo_path).name, "path": c.arquivo_path, "clicksign_key": None}]

    erros: list[str] = []

    # 1. Se houver mais de um PDF, mescla em um único arquivo antes do upload.
    #    O ClickSign API v1 não tem envelope multi-doc — um único PDF contém tudo.
    if len(arquivos_para_enviar) > 1:
        try:
            from pypdf import PdfWriter
            writer = PdfWriter()
            for arq in arquivos_para_enviar:
                writer.append(arq["path"])
            # Usa o nome do arquivo principal já salvo no sistema (ex: gerado por
            # "Gerar contrato"/"Gerar procuração") em vez de um nome genérico — é esse
            # nome que aparece pro signatário no ClickSign e no e-mail de convite.
            principal = next((a for a in arquivos_para_enviar if a.get("filename") == c.doc_gerado_filename), None)
            prefixo = "Procuracao" if c.tipo_documento == "procuracao" else "Contrato"
            nome_merged = (principal or arquivos_para_enviar[0]).get("filename") or f"{prefixo}_{contrato_id.hex[:8]}_completo.pdf"
            path_merged = UPLOADS_DIR / nome_merged
            with open(path_merged, "wb") as fout:
                writer.write(fout)
            arquivos_para_upload = [{"filename": nome_merged, "path": str(path_merged), "clicksign_key": None}]
        except Exception as e:
            raise HTTPException(status_code=500, detail=f"Erro ao mesclar PDFs: {e}")
    else:
        arquivos_para_upload = arquivos_para_enviar

    # 2. Upload do documento (único) para o ClickSign
    arq_principal = arquivos_para_upload[0]
    nome_arq = arq_principal.get("filename", Path(arq_principal["path"]).name)
    try:
        doc_key_principal = clicksign.upload_documento(arq_principal["path"], nome_arq)
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"Falha no upload para o ClickSign: {e}")

    # Marca a clicksign_key em cada entrada original (todos apontam para o doc mesclado)
    lista_atualizada = [{**arq, "clicksign_key": doc_key_principal} for arq in arquivos_para_enviar]
    c.clicksign_document_key = doc_key_principal
    c.arquivos = lista_atualizada

    # 3. Criar signatários, vincular ao documento e enviar notificação por email
    # ↳ POST /lists vincula mas NÃO envia email; é necessário chamar POST /notifications
    for sig in c.signatarios:
        try:
            signer_key = clicksign.criar_signatario(
                sig.nome, sig.email, cpf=sig.cpf,
                data_nascimento=sig.data_nascimento.isoformat() if sig.data_nascimento else None,
            )
            sig.clicksign_signer_key = signer_key
            req_key = clicksign.adicionar_signatario_ao_documento(
                doc_key_principal, signer_key, sig.papel
            )
            if req_key:
                sig.clicksign_request_key = req_key          # armazena por signatário
                c.clicksign_request_signature_key = req_key
                clicksign.notificar_signatario(req_key)      # dispara email de convite
        except Exception as e:
            erros.append(f"Signatário '{sig.email}': {e}")

    # (Não chamar /finish — isso fecha o documento permanentemente.
    #  auto_close=True já encerra ao receber todas as assinaturas.)

    if erros:
        import logging
        logging.warning("ClickSign erros parciais: %s", erros)

    c.status = "aguardando_assinatura"
    db.commit()
    db.refresh(c)
    return c


@router.post("/{contrato_id}/confirmar-assinatura", response_model=ContratoOut)
def confirmar_assinatura_manual(contrato_id: uuid.UUID, db: Session = Depends(get_db)):
    """Marca contrato como assinado manualmente e remove tag pendente_assinatura do honorário."""
    c = db.query(Contrato).filter(Contrato.id == contrato_id).first()
    if not c:
        raise HTTPException(status_code=404, detail="Contrato não encontrado")
    c.status = "assinado"
    c.assinatura_manual = True
    # Remove pendência do honorário vinculado
    try:
        from app.models.financeiro import Honorario
        h = db.query(Honorario).filter(Honorario.contrato_id == contrato_id).first()
        if h:
            h.pendente_assinatura = False
    except Exception:
        pass
    db.commit()
    db.refresh(c)
    return c


@router.post("/{contrato_id}/finalizar-assinado-manual", response_model=ContratoOut)
def finalizar_assinado_manual(contrato_id: uuid.UUID, db: Session = Depends(get_db)):
    """
    Finaliza um contrato já assinado fora do sistema (ex: assinatura física ou por outro
    meio), a partir do(s) PDF(s) já anexados — sem passar pelo ClickSign e sem notificar
    ou reenviar nada ao cliente. Marca status="assinado" + assinatura_manual=True e
    duplica o PDF final para a pasta do cliente e para a pasta mestra /Contratos no Drive.
    """
    c = db.query(Contrato).filter(Contrato.id == contrato_id).first()
    if not c:
        raise HTTPException(status_code=404, detail="Contrato não encontrado")
    if c.status != "rascunho":
        raise HTTPException(status_code=400, detail="Só é possível finalizar contratos em rascunho")

    arquivos_atuais = list(c.arquivos or [])
    if not arquivos_atuais and c.arquivo_path:
        arquivos_atuais = [{"filename": Path(c.arquivo_path).name, "path": c.arquivo_path}]
    if not arquivos_atuais:
        raise HTTPException(status_code=400, detail="Anexe o PDF já assinado antes de finalizar")

    # Mescla múltiplos PDFs em um único arquivo final, como no envio ao ClickSign
    if len(arquivos_atuais) > 1:
        try:
            from pypdf import PdfWriter
            writer = PdfWriter()
            for arq in arquivos_atuais:
                writer.append(arq["path"])
            principal = next((a for a in arquivos_atuais if a.get("filename") == c.doc_gerado_filename), None)
            prefixo = "Procuracao" if c.tipo_documento == "procuracao" else "Contrato"
            nome_final = (principal or arquivos_atuais[0]).get("filename") or f"{prefixo}_{contrato_id.hex[:8]}_assinado.pdf"
            path_final = UPLOADS_DIR / nome_final
            with open(path_final, "wb") as fout:
                writer.write(fout)
        except Exception as e:
            raise HTTPException(status_code=500, detail=f"Erro ao mesclar PDFs: {e}")
    else:
        path_final = Path(arquivos_atuais[0]["path"])
        nome_final = arquivos_atuais[0].get("filename") or path_final.name

    pdf_bytes = path_final.read_bytes()
    c.arquivo_assinado_path = str(path_final)
    c.status = "assinado"
    c.assinatura_manual = True

    link_cliente, link_master = _duplicar_para_drive(db, c, pdf_bytes, nome_final)
    if link_cliente:
        c.drive_link_cliente = link_cliente
    if link_master:
        c.drive_link_master = link_master

    # Remove pendência do honorário vinculado
    try:
        from app.models.financeiro import Honorario
        h = db.query(Honorario).filter(Honorario.contrato_id == contrato_id).first()
        if h:
            h.pendente_assinatura = False
    except Exception:
        pass

    db.commit()
    db.refresh(c)
    return c


@router.post("/{contrato_id}/cancelar", response_model=ContratoOut)
def cancelar_contrato_clicksign(contrato_id: uuid.UUID, db: Session = Depends(get_db)):
    c = db.query(Contrato).filter(Contrato.id == contrato_id).first()
    if not c:
        raise HTTPException(status_code=404, detail="Contrato não encontrado")
    if c.clicksign_document_key:
        clicksign.cancelar_documento(c.clicksign_document_key)
    c.status = "cancelado"
    db.commit()
    db.refresh(c)
    return c


@router.post("/{contrato_id}/sincronizar-status", response_model=ContratoOut)
def sincronizar_status_clicksign(contrato_id: uuid.UUID, db: Session = Depends(get_db)):
    """
    Consulta o status REAL do documento no ClickSign e reconcilia o estado local
    (útil quando o webhook não chegou: contrato assinado no ClickSign mas ainda
    "Pendente" no sistema). Atualiza cada signatário e o status do contrato; se
    já estiver fechado, baixa/arquiva o PDF assinado e limpa a pendência do
    honorário vinculado.
    """
    from datetime import datetime, timezone

    c = db.query(Contrato).filter(Contrato.id == contrato_id).first()
    if not c:
        raise HTTPException(status_code=404, detail="Contrato não encontrado")
    if not c.clicksign_document_key:
        raise HTTPException(status_code=400, detail="Contrato não foi enviado ao ClickSign (sem documento vinculado).")

    doc = clicksign.status_documento(c.clicksign_document_key)
    if doc is None:
        raise HTTPException(status_code=502, detail="Não foi possível consultar o status no ClickSign.")

    doc_status = (doc.get("status") or "").lower()

    if doc_status == "canceled":
        c.status = "cancelado"
        db.commit()
        db.refresh(c)
        return c

    por_key, por_email = _extrair_assinados(doc)

    for sig in c.signatarios:
        assinou = False
        ts = None
        if sig.clicksign_signer_key and sig.clicksign_signer_key in por_key:
            assinou, ts = True, por_key[sig.clicksign_signer_key]
        elif sig.email and sig.email.lower() in por_email:
            assinou, ts = True, por_email[sig.email.lower()]
        elif doc_status == "closed":
            assinou = True
        if assinou and sig.status_assinatura != "assinado":
            sig.status_assinatura = "assinado"
            sig.assinado_em = _parse_iso(ts) or datetime.now(timezone.utc)

    signatarios = list(c.signatarios)
    todos_assinaram = bool(signatarios) and all(s.status_assinatura == "assinado" for s in signatarios)
    algum_assinou = any(s.status_assinatura == "assinado" for s in signatarios)

    if doc_status == "closed" or todos_assinaram:
        c.status = "assinado"
        # Baixa/arquiva o assinado sempre que já der pra considerar concluído — não só
        # quando o ClickSign reporta "closed" literalmente (evita ficar sem o PDF final
        # se o status demorar a fechar por lá mas todos já assinaram por aqui). Endpoint
        # síncrono (roda em threadpool) — pode esperar o ClickSign gerar o link do
        # assinado, que leva alguns segundos após o fechamento.
        _baixar_e_arquivar_assinado_clicksign(db, c, c.clicksign_document_key, tentativas=6, espera_s=4.0)
        try:
            from app.models.financeiro import Honorario
            h = db.query(Honorario).filter(Honorario.contrato_id == contrato_id).first()
            if h:
                h.pendente_assinatura = False
        except Exception:
            pass
    elif algum_assinou:
        c.status = "parcialmente_assinado"

    db.commit()
    db.refresh(c)
    return c


# ── Webhook ClickSign (router_publico — sem auth, ver comentário acima) ────────

@router_publico.post("/webhook/clicksign")
async def webhook_clicksign(request: Request, db: Session = Depends(get_db)):
    """
    Recebe callbacks do ClickSign sobre eventos de assinatura.
    Atualiza status do contrato e signatários.
    """
    import os
    secret = os.getenv("CLICKSIGN_WEBHOOK_SECRET")
    if secret and request.query_params.get("secret") != secret:
        return {"ok": False}

    payload = await request.json()
    evento = payload.get("event", {})
    nome_evento = evento.get("name", "")
    doc = payload.get("document", {})
    doc_key = doc.get("key")

    if not doc_key:
        return {"ok": True}

    contrato = db.query(Contrato).filter(Contrato.clicksign_document_key == doc_key).first()
    if not contrato:
        return {"ok": True}

    # Evento: signatário assinou
    if nome_evento == "sign":
        signer_key = evento.get("signer", {}).get("key")
        if signer_key:
            sig = db.query(Signatario).filter(
                Signatario.clicksign_signer_key == signer_key
            ).first()
            if sig:
                from datetime import datetime, timezone
                sig.status_assinatura = "assinado"
                sig.assinado_em = datetime.now(timezone.utc)

        # Verifica se todos assinaram
        todos = db.query(Signatario).filter(Signatario.contrato_id == contrato.id).all()
        if all(s.status_assinatura == "assinado" for s in todos):
            contrato.status = "assinado"
            _baixar_e_arquivar_assinado_clicksign(db, contrato, doc_key)
        else:
            contrato.status = "parcialmente_assinado"

    elif nome_evento == "cancel":
        contrato.status = "cancelado"

    elif nome_evento == "close":
        contrato.status = "assinado"
        _baixar_e_arquivar_assinado_clicksign(db, contrato, doc_key)

    db.commit()
    return {"ok": True}


def _baixar_e_arquivar_assinado_clicksign(
    db: Session, contrato: Contrato, doc_key: str, tentativas: int = 1, espera_s: float = 4.0,
) -> None:
    """
    Baixa o PDF final assinado do ClickSign (se ainda não baixado) e o duplica no Drive
    — pasta do cliente e pasta mestra /Contratos ou /Procurações. Idempotente: não baixa/
    reenvia de novo se `arquivo_assinado_path` já estiver preenchido (evita duplicar em
    múltiplos eventos de webhook para o mesmo documento, ex: "sign" do último signatário
    + "close"). `tentativas`/`espera_s`: o link do PDF assinado só fica pronto alguns
    segundos após o ClickSign fechar o documento — no webhook (async) usa só 1 tentativa
    pra não travar o event loop; quem chama de um endpoint síncrono (ex: sincronizar-
    status, que roda em threadpool) pode pedir mais tentativas com espera entre elas.
    """
    if contrato.arquivo_assinado_path:
        return
    pdf_bytes = clicksign.baixar_documento_assinado(doc_key, tentativas=tentativas, espera_s=espera_s)
    if not pdf_bytes:
        return
    nome_arquivo = f"{contrato.id}_assinado.pdf"
    path_assinado = UPLOADS_DIR / nome_arquivo
    path_assinado.write_bytes(pdf_bytes)
    contrato.arquivo_assinado_path = str(path_assinado)

    link_cliente, link_master = _duplicar_para_drive(db, contrato, pdf_bytes, nome_arquivo)
    if link_cliente:
        contrato.drive_link_cliente = link_cliente
    if link_master:
        contrato.drive_link_master = link_master


# ── Download do PDF assinado ──────────────────────────────────────────────────

@router.get("/{contrato_id}/download-assinado")
def download_assinado(contrato_id: uuid.UUID, db: Session = Depends(get_db)):
    from fastapi.responses import FileResponse
    c = db.query(Contrato).filter(Contrato.id == contrato_id).first()
    if not c or not c.arquivo_assinado_path:
        raise HTTPException(status_code=404, detail="PDF assinado não disponível")
    prefixo = "procuracao" if c.tipo_documento == "procuracao" else "contrato"
    return FileResponse(c.arquivo_assinado_path, media_type="application/pdf", filename=f"{prefixo}_{contrato_id}_assinado.pdf")
