"""
Agregador de contexto ("Linha Longa") para os chats de IA de Cliente e Processo.

Monta, a partir dos dados já existentes no banco (não duplica nada), um bloco
de texto com: memória estratégica atual, dados cadastrais, andamentos
recentes, prazos pendentes, tarefas, anotações e financeiro — respeitando
confidencialidade e permissão de financeiro do usuário que está perguntando.
"""
from datetime import date

from sqlalchemy.orm import Session

from app.models.anotacao import Anotacao
from app.models.cliente import Cliente
from app.models.email_cliente import EmailCliente
from app.models.financeiro import Honorario
from app.models.memoria_estrategica import MemoriaEstrategica
from app.models.prazo import Prazo
from app.models.processo import Processo, processo_clientes
from app.models.reuniao import Reuniao
from app.models.tarefa import Tarefa
from app.models.usuario import Usuario

ANDAMENTOS_LIMITE = 10
ANOTACOES_LIMITE = 10
EMAILS_LIMITE = 10
REUNIOES_LIMITE = 10


def _processos_do_cliente(db: Session, cliente: Cliente) -> list[Processo]:
    """Processos onde o cliente é o principal (FK direta) OU litisconsorte."""
    litisconsorcio = (
        db.query(Processo)
        .join(processo_clientes, Processo.id == processo_clientes.c.processo_id)
        .filter(processo_clientes.c.cliente_id == cliente.id)
        .all()
    )
    vistos = {p.id for p in cliente.processos}
    todos = list(cliente.processos)
    for p in litisconsorcio:
        if p.id not in vistos:
            todos.append(p)
            vistos.add(p.id)
    return todos


def _emails_texto(db: Session, usuario: Usuario, cliente_id) -> list[str]:
    q = db.query(EmailCliente).filter(
        EmailCliente.cliente_id == cliente_id,
        EmailCliente.categoria.in_(["processual", "comercial"]),
    )
    emails = q.order_by(EmailCliente.data.desc()).limit(EMAILS_LIMITE * 2).all()
    linhas = []
    for e in emails:
        if e.privado and usuario.role != "super_admin" and e.privado_por != usuario.id:
            continue
        data = e.data.strftime("%Y-%m-%d") if e.data else "?"
        linhas.append(f"- [{data}] De: {e.remetente or '?'} — {e.assunto or '(sem assunto)'}: {(e.snippet or '')[:200]}")
        if len(linhas) >= EMAILS_LIMITE:
            break
    return linhas


def _reunioes_texto(db: Session, usuario: Usuario, *, cliente_id=None, processo_id=None) -> list[str]:
    q = db.query(Reuniao)
    if processo_id:
        q = q.filter(Reuniao.processo_id == processo_id)
    elif cliente_id:
        q = q.filter(Reuniao.cliente_id == cliente_id)
    reunioes = q.order_by(Reuniao.data_reuniao.desc()).limit(REUNIOES_LIMITE * 2).all()
    linhas = []
    for r in reunioes:
        if not _visivel_para(usuario, r.confidencial, r.usuarios_com_acesso):
            continue
        data = r.data_reuniao.strftime("%Y-%m-%d") if r.data_reuniao else "?"
        resumo = r.resumo_ia or "(sem resumo)"
        linhas.append(f"- [{data}] {r.titulo}: {resumo[:300]}")
        if len(linhas) >= REUNIOES_LIMITE:
            break
    return linhas


def _memoria_atual(db: Session, *, cliente_id=None, processo_id=None) -> str | None:
    q = db.query(MemoriaEstrategica)
    if cliente_id:
        q = q.filter(MemoriaEstrategica.cliente_id == cliente_id)
    if processo_id:
        q = q.filter(MemoriaEstrategica.processo_id == processo_id)
    m = q.order_by(MemoriaEstrategica.created_at.desc()).first()
    return m.texto if m else None


def _visivel_para(usuario: Usuario, confidencial: bool, usuarios_com_acesso: list | None) -> bool:
    if not confidencial:
        return True
    if usuario.role == "super_admin":
        return True
    ids_com_acesso = usuarios_com_acesso or []
    return str(usuario.id) in ids_com_acesso


def _anotacoes_texto(db: Session, usuario: Usuario, *, cliente_id=None, processo_id=None) -> list[str]:
    q = db.query(Anotacao)
    if processo_id:
        q = q.filter(Anotacao.processo_id == processo_id)
    elif cliente_id:
        q = q.filter(Anotacao.cliente_id == cliente_id)
    anotacoes = q.order_by(Anotacao.data_evento.desc()).limit(ANOTACOES_LIMITE * 2).all()
    linhas = []
    for a in anotacoes:
        if not _visivel_para(usuario, a.confidencial, None):
            continue
        linhas.append(f"- [{a.data_evento}] ({a.tipo}) {a.titulo or ''}: {a.texto[:300]}")
        if len(linhas) >= ANOTACOES_LIMITE:
            break
    return linhas


def _tarefas_texto(db: Session, usuario: Usuario, *, cliente_id=None, processo_id=None) -> list[str]:
    q = db.query(Tarefa)
    if processo_id:
        q = q.filter(Tarefa.processo_id == processo_id)
    elif cliente_id:
        q = q.filter(Tarefa.cliente_id == cliente_id)
    q = q.filter(Tarefa.status.notin_(["concluido", "cancelado"]))
    tarefas = q.order_by(Tarefa.data_limite.asc().nullslast()).limit(30).all()
    linhas = []
    for t in tarefas:
        if not _visivel_para(usuario, t.confidencial, t.usuarios_com_acesso):
            continue
        prazo = f", prazo {t.data_limite}" if t.data_limite else ""
        resp = f", responsável {t.responsavel}" if t.responsavel else ""
        linhas.append(f"- {t.titulo} (status: {t.status}{prazo}{resp})")
    return linhas


def _prazos_texto(processo: Processo) -> list[str]:
    hoje = date.today()
    linhas = []
    for p in processo.prazos:
        if p.status != "pendente":
            continue
        limite = p.data_limite or p.data_limite_sem_feriado
        dias_restantes = (limite - hoje).days if limite else None
        alerta = " ⚠️ VENCIDO" if dias_restantes is not None and dias_restantes < 0 else ""
        resp = f", responsável {p.responsavel}" if p.responsavel else ""
        linhas.append(f"- {p.tipo}: limite {limite}{resp}{alerta}")
    return linhas


def _andamentos_texto(processo: Processo) -> list[str]:
    return [
        f"- [{a.data_andamento}] {a.tipo or 'Andamento'}: {a.descricao[:300]}"
        for a in processo.andamentos[:ANDAMENTOS_LIMITE]
    ]


def _financeiro_texto(db: Session, usuario: Usuario, *, cliente_id=None, processo_id=None) -> list[str]:
    if not usuario.pode_ver_financeiro:
        return []
    q = db.query(Honorario)
    if processo_id:
        q = q.filter(Honorario.processo_id == processo_id)
    elif cliente_id:
        q = q.filter(Honorario.cliente_id == cliente_id)
    linhas = []
    for h in q.all():
        linhas.append(
            f"- Honorário {h.status}: total R$ {h.valor_total:.2f}, "
            f"recebido R$ {h.total_recebido:.2f}, saldo R$ {h.saldo_pendente:.2f}"
        )
    return linhas


def montar_contexto_cliente(db: Session, cliente: Cliente, usuario: Usuario) -> str:
    blocos = ["## Cliente", f"Nome: {cliente.nome} ({cliente.tipo})"]
    if cliente.observacoes:
        blocos.append(f"Observações: {cliente.observacoes}")

    memoria = _memoria_atual(db, cliente_id=cliente.id)
    if memoria:
        blocos.append("\n## Memória Estratégica (o que buscamos com este cliente)")
        blocos.append(memoria)

    processos = _processos_do_cliente(db, cliente)
    if processos:
        blocos.append(f"\n## Processos vinculados ({len(processos)})")
        for p in processos:
            litisconsorte = " (litisconsórcio)" if p not in cliente.processos else ""
            blocos.append(f"- {p.numero_cnj} ({p.status}, {p.fase or 'fase n/d'}){litisconsorte}: {p.objeto or 'sem objeto cadastrado'}")
            if p.ultimo_andamento_data or p.ultimo_andamento_desc:
                nao_lidos = f", {p.andamentos_nao_lidos} não lido(s)" if p.andamentos_nao_lidos else ""
                blocos.append(f"  Último andamento [{p.ultimo_andamento_data or '?'}]{nao_lidos}: {p.ultimo_andamento_desc or '(sem descrição)'}")

    tarefas = _tarefas_texto(db, usuario, cliente_id=cliente.id)
    if tarefas:
        blocos.append("\n## Tarefas pendentes")
        blocos.extend(tarefas)

    anotacoes = _anotacoes_texto(db, usuario, cliente_id=cliente.id)
    if anotacoes:
        blocos.append("\n## Anotações recentes")
        blocos.extend(anotacoes)

    reunioes = _reunioes_texto(db, usuario, cliente_id=cliente.id)
    if reunioes:
        blocos.append("\n## Reuniões recentes")
        blocos.extend(reunioes)

    emails = _emails_texto(db, usuario, cliente.id)
    if emails:
        blocos.append("\n## E-mails recentes")
        blocos.extend(emails)

    financeiro = _financeiro_texto(db, usuario, cliente_id=cliente.id)
    if financeiro:
        blocos.append("\n## Financeiro")
        blocos.extend(financeiro)

    return "\n".join(blocos)


def montar_contexto_processo(db: Session, processo: Processo, usuario: Usuario) -> str:
    blocos = [
        "## Processo",
        f"Nº CNJ: {processo.numero_cnj} — {processo.tribunal or processo.estado}",
        f"Status: {processo.status}, Fase: {processo.fase or 'n/d'}",
    ]
    if processo.objeto:
        blocos.append(f"Objeto: {processo.objeto}")
    if processo.cliente:
        blocos.append(f"Cliente: {processo.cliente.nome}")

    memoria_processo = _memoria_atual(db, processo_id=processo.id)
    memoria_cliente = _memoria_atual(db, cliente_id=processo.cliente_id) if processo.cliente_id else None
    if memoria_cliente:
        blocos.append("\n## Memória Estratégica do Cliente")
        blocos.append(memoria_cliente)
    if memoria_processo:
        blocos.append("\n## Memória Estratégica deste Processo")
        blocos.append(memoria_processo)

    prazos = _prazos_texto(processo)
    if prazos:
        blocos.append("\n## Prazos pendentes")
        blocos.extend(prazos)

    andamentos = _andamentos_texto(processo)
    if andamentos:
        blocos.append(f"\n## Últimos andamentos (até {ANDAMENTOS_LIMITE})")
        blocos.extend(andamentos)

    tarefas = _tarefas_texto(db, usuario, processo_id=processo.id)
    if tarefas:
        blocos.append("\n## Tarefas pendentes")
        blocos.extend(tarefas)

    anotacoes = _anotacoes_texto(db, usuario, processo_id=processo.id)
    if anotacoes:
        blocos.append("\n## Anotações recentes")
        blocos.extend(anotacoes)

    reunioes = _reunioes_texto(db, usuario, processo_id=processo.id)
    if reunioes:
        blocos.append("\n## Reuniões recentes")
        blocos.extend(reunioes)

    financeiro = _financeiro_texto(db, usuario, processo_id=processo.id)
    if financeiro:
        blocos.append("\n## Financeiro")
        blocos.extend(financeiro)

    return "\n".join(blocos)
