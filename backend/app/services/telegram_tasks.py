"""Serviço de captura rápida de tarefas via Telegram (Tarefas_sui_bot).

Fluxo principal:
  1. Usuário manda lista de tarefas (uma por linha) → salva tudo imediatamente.
  2. Bot responde com resumo + botões para complementar em bloco.
  3. Usuário pode definir datas, revisar duplicadas, ou simplesmente parar.

Baseado no protótipo do Codex; adaptado para usar o token dedicado do bot de Tarefas
e as convenções de telegram_api.py do projeto.
"""
from __future__ import annotations

import re
import unicodedata
import uuid
from datetime import date, timedelta
from difflib import SequenceMatcher
from typing import Any

import httpx
from sqlalchemy.orm import Session

from app.config import settings
from app.models.cliente import Cliente
from app.models.tarefa import Tarefa
from app.models.tarefa_card import TarefaCard, TarefaCardSubtask
from app.models.tarefa_projeto import TarefaProjeto
from app.models.telegram_task import TelegramChatSession, TelegramTaskBatch, TelegramTaskItem
from app.models.usuario import Usuario

# ---------------------------------------------------------------------------
# Stopwords para normalização de texto
# ---------------------------------------------------------------------------
STOPWORDS = {
    "a", "ao", "aos", "as", "com", "contra", "da", "das", "de", "do", "dos", "e",
    "em", "na", "nas", "no", "nos", "o", "os", "ou", "para", "por", "pra", "pro",
    "um", "uma", "uns", "umas",
}


# ---------------------------------------------------------------------------
# Telegram API (token dedicado do bot de Tarefas)
# ---------------------------------------------------------------------------

def _post(method: str, payload: dict) -> dict | None:
    token = settings.telegram_tarefas_bot_token
    if not token:
        return None
    url = f"https://api.telegram.org/bot{token}/{method}"
    try:
        resp = httpx.post(url, json=payload, timeout=20.0)
        data = resp.json()
        return data.get("result") if data.get("ok") else None
    except Exception:
        return None


def send_message(chat_id: str | int, text: str, reply_markup: dict | None = None) -> dict | None:
    payload: dict[str, Any] = {"chat_id": chat_id, "text": text}
    if reply_markup:
        payload["reply_markup"] = reply_markup
    return _post("sendMessage", payload)


def edit_message(chat_id: str | int, message_id: int, text: str, reply_markup: dict | None = None) -> dict | None:
    payload: dict[str, Any] = {"chat_id": chat_id, "message_id": message_id, "text": text}
    if reply_markup:
        payload["reply_markup"] = reply_markup
    return _post("editMessageText", payload)


def answer_callback(callback_query_id: str, text: str | None = None) -> None:
    payload: dict[str, Any] = {"callback_query_id": callback_query_id}
    if text:
        payload["text"] = text
    _post("answerCallbackQuery", payload)


def register_webhook(base_url: str) -> dict | None:
    webhook_url = f"{base_url.rstrip('/')}/telegram-tarefas/webhook"
    payload: dict[str, Any] = {"url": webhook_url}
    if settings.telegram_tarefas_webhook_secret:
        payload["secret_token"] = settings.telegram_tarefas_webhook_secret
    return _post("setWebhook", payload)


def get_webhook_info() -> dict | None:
    return _post("getWebhookInfo", {})


# ---------------------------------------------------------------------------
# Markups padrão
# ---------------------------------------------------------------------------

def default_reply_markup() -> dict:
    return {"inline_keyboard": [[{"text": "Deixar como está", "callback_data": "tg:global:skip"}]]}


# ---------------------------------------------------------------------------
# Normalização e parsing de texto
# ---------------------------------------------------------------------------

def normalize_text(text: str) -> str:
    normalized = unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode()
    normalized = re.sub(r"[^\w\s]", " ", normalized.lower())
    normalized = re.sub(r"\s+", " ", normalized).strip()
    return normalized


def parse_task_lines(text: str) -> list[str]:
    cleaned = text.strip()
    if not cleaned:
        return []
    if "\n" not in cleaned and ";" in cleaned:
        lines = cleaned.split(";")
    else:
        lines = cleaned.splitlines()
    tasks: list[str] = []
    for raw in lines:
        line = raw.strip()
        line = re.sub(r"^\s*(?:[-*•]|\d+[.)])\s*", "", line)
        line = re.sub(r"\s+", " ", line).strip(" -\t")
        if not line or line.startswith("/"):
            continue
        tasks.append(line[:500])
    return tasks


def _title_tokens(text: str) -> set[str]:
    return {token for token in normalize_text(text).split() if len(token) >= 3 and token not in STOPWORDS}


# ---------------------------------------------------------------------------
# Inferência de cliente
# ---------------------------------------------------------------------------

def infer_client_for_title(db: Session, title: str) -> tuple[Cliente | None, float]:
    title_norm = normalize_text(title)
    title_tokens = _title_tokens(title)
    best_client: Cliente | None = None
    best_score = 0.0

    for client in db.query(Cliente).order_by(Cliente.nome).all():
        client_norm = normalize_text(client.nome)
        if not client_norm:
            continue

        score = 0.0
        client_tokens = _title_tokens(client.nome)
        if client_norm in title_norm:
            score = 0.99
        elif client_tokens:
            overlap = client_tokens & title_tokens
            if overlap:
                coverage = len(overlap) / len(client_tokens)
                score = max(score, 0.58 + 0.34 * coverage)
                if coverage == 1:
                    score = max(score, 0.93)
            partial_hits = [t for t in client_tokens if any(t in tt or tt in t for tt in title_tokens)]
            if partial_hits:
                score = max(score, 0.52 + 0.12 * (len(partial_hits) / len(client_tokens)))

        ratio = SequenceMatcher(None, title_norm, client_norm).ratio()
        score = max(score, ratio * 0.68)

        if score > best_score:
            best_client = client
            best_score = score

    if best_score < 0.72:
        return None, best_score
    return best_client, round(best_score, 3)


# ---------------------------------------------------------------------------
# Detecção de duplicadas
# ---------------------------------------------------------------------------

def find_probable_duplicate(db: Session, title: str, cliente_id: uuid.UUID | None) -> tuple[Tarefa | None, float]:
    title_norm = normalize_text(title)
    if not title_norm:
        return None, 0.0

    candidates = (
        db.query(Tarefa)
        .filter(Tarefa.status.in_(["pendente", "em_andamento"]))
        .order_by(Tarefa.updated_at.desc())
        .limit(200)
        .all()
    )

    best: Tarefa | None = None
    best_score = 0.0
    for tarefa in candidates:
        existing_norm = normalize_text(tarefa.titulo)
        if not existing_norm:
            continue
        if existing_norm == title_norm:
            score = 1.0
        else:
            score = SequenceMatcher(None, title_norm, existing_norm).ratio()
            if title_norm in existing_norm or existing_norm in title_norm:
                score = max(score, 0.9)
        if cliente_id and tarefa.cliente_id == cliente_id:
            score += 0.04
        if score > best_score:
            best = tarefa
            best_score = score

    if best_score < 0.86:
        return None, best_score
    return best, round(min(best_score, 1.0), 3)


# ---------------------------------------------------------------------------
# Usuário padrão do bot
# ---------------------------------------------------------------------------

def resolve_default_user(db: Session) -> Usuario | None:
    ref = settings.telegram_tarefas_default_user.strip()
    if not ref:
        return None
    try:
        user_id = uuid.UUID(ref)
        return db.query(Usuario).filter(Usuario.id == user_id).first()
    except ValueError:
        return db.query(Usuario).filter(Usuario.email == ref).first()


# ---------------------------------------------------------------------------
# Sessão de chat
# ---------------------------------------------------------------------------

def get_or_create_session(db: Session, chat_id: str) -> TelegramChatSession:
    session = db.query(TelegramChatSession).filter(TelegramChatSession.chat_id == chat_id).first()
    if session:
        return session
    session = TelegramChatSession(chat_id=chat_id, payload={})
    db.add(session)
    db.flush()
    return session


def reset_session(session: TelegramChatSession) -> None:
    session.pending_action = None
    session.payload = {}


# ---------------------------------------------------------------------------
# Criação de lote
# ---------------------------------------------------------------------------

def _append_tag(existing: str | None, tag: str) -> str:
    parts = [p.strip() for p in (existing or "").split(",") if p.strip()]
    if tag not in parts:
        parts.append(tag)
    return ", ".join(parts)


def create_batch_from_text(
    db: Session, chat_id: str, source_message_id: int | None, text: str
) -> tuple[TelegramTaskBatch, list[TelegramTaskItem]]:
    batch = TelegramTaskBatch(
        chat_id=chat_id,
        source_message_id=str(source_message_id) if source_message_id else None,
        raw_text=text,
        status="ativo",
    )
    db.add(batch)
    db.flush()

    session = get_or_create_session(db, chat_id)
    default_user = resolve_default_user(db)
    created_items: list[TelegramTaskItem] = []
    seen_titles: dict[str, uuid.UUID] = {}

    for title in parse_task_lines(text):
        normalized_title = normalize_text(title)
        inferred_client, client_score = infer_client_for_title(db, title)
        duplicate_task, duplicate_score = find_probable_duplicate(
            db, title, inferred_client.id if inferred_client else None
        )
        if not duplicate_task and normalized_title in seen_titles:
            duplicate_task = db.query(Tarefa).filter(Tarefa.id == seen_titles[normalized_title]).first()
            duplicate_score = 1.0 if duplicate_task else 0.0

        tarefa = Tarefa(
            titulo=title,
            status="pendente",
            cliente_id=inferred_client.id if inferred_client else None,
            tags=_append_tag(None, "telegram"),
        )
        if default_user:
            tarefa.criado_por_id = default_user.id
        db.add(tarefa)

        # Cria também no menu Tarefas em Cards (como card macro avulso)
        card = TarefaCard(
            titulo=title,
            status="pendente",
            cliente_id=inferred_client.id if inferred_client else None,
        )
        if default_user:
            card.criado_por_id = default_user.id
        db.add(card)
        db.flush()

        item = TelegramTaskItem(
            batch_id=batch.id,
            tarefa_id=tarefa.id,
            card_id=card.id,
            titulo_original=title,
            titulo_normalizado=normalized_title,
            cliente_inferido_id=inferred_client.id if inferred_client else None,
            cliente_inferido_nome=inferred_client.nome if inferred_client else None,
            cliente_inferencia_score=client_score if inferred_client else None,
            duplicada_de_tarefa_id=duplicate_task.id if duplicate_task else None,
            duplicada_score=duplicate_score if duplicate_task else None,
        )
        db.add(item)
        created_items.append(item)
        seen_titles[normalized_title] = tarefa.id

    session.current_batch_id = batch.id
    reset_session(session)
    db.commit()

    for item in created_items:
        db.refresh(item)
    db.refresh(batch)
    return batch, created_items


# ---------------------------------------------------------------------------
# Mensagens de resumo
# ---------------------------------------------------------------------------

def load_batch_items(db: Session, batch_id: uuid.UUID) -> list[TelegramTaskItem]:
    return (
        db.query(TelegramTaskItem)
        .filter(TelegramTaskItem.batch_id == batch_id)
        .order_by(TelegramTaskItem.created_at.asc())
        .all()
    )


def build_batch_summary(db: Session, batch: TelegramTaskBatch) -> str:
    items = load_batch_items(db, batch.id)
    duplicates = sum(1 for item in items if item.duplicada_de_tarefa_id)
    inferred_clients = sum(1 for item in items if item.cliente_inferido_id)

    lines = [f"✅ {len(items)} tarefa(s) registrada(s)."]
    if inferred_clients:
        lines.append(f"🔍 {inferred_clients} com cliente sugerido.")
    if duplicates:
        lines.append(f"⚠️ {duplicates} possível(is) duplicada(s).")
    lines.append("")

    for idx, item in enumerate(items[:10], start=1):
        suffixes = []
        if item.cliente_inferido_nome:
            suffixes.append(item.cliente_inferido_nome)
        if item.duplicada_de_tarefa_id:
            suffixes.append("duplicada?")
        suffix = f" ({' · '.join(suffixes)})" if suffixes else ""
        lines.append(f"{idx}. {item.titulo_original}{suffix}")

    if len(items) > 10:
        lines.append(f"... e mais {len(items) - 10}.")

    lines.append("")
    lines.append("Quer definir datas ou deixar como está?")
    return "\n".join(lines)


def build_post_responsavel_prompt(batch: TelegramTaskBatch) -> tuple[str, dict]:
    """Pergunta, após definir o responsável, se quer vincular a uma macro ou deixar como está."""
    keyboard = [
        [{"text": "📌 Vincular a Macros", "callback_data": f"tg:batch:{batch.id.hex}:card_link"}],
        [{"text": "✅ Deixar como está", "callback_data": f"tg:batch:{batch.id.hex}:done"}],
    ]
    return "Quer vincular alguma dessas tarefas a uma macro (Tarefa mãe), ou deixar como está?", {"inline_keyboard": keyboard}


def batch_actions_markup(batch: TelegramTaskBatch, has_duplicates: bool) -> dict:
    keyboard: list[list[dict]] = [
        [
            {"text": "👤 Responsável", "callback_data": f"tg:batch:{batch.id.hex}:resp"},
            {"text": "📅 Datas", "callback_data": f"tg:batch:{batch.id.hex}:dates"},
        ],
        [
            {"text": "📌 Vincular a Macros", "callback_data": f"tg:batch:{batch.id.hex}:card_link"},
        ],
        [
            {"text": "✅ Deixar como está", "callback_data": f"tg:batch:{batch.id.hex}:done"},
        ]
    ]
    if has_duplicates:
        keyboard.append([{"text": "🔁 Revisar duplicadas", "callback_data": f"tg:batch:{batch.id.hex}:dupes"}])
    return {"inline_keyboard": keyboard}


# ---------------------------------------------------------------------------
# Fluxo de vínculo com Tarefa Macro (Tarefas em Cards)
# ---------------------------------------------------------------------------

def _active_projetos(db: Session) -> list[TarefaProjeto]:
    return db.query(TarefaProjeto).filter(TarefaProjeto.oculto == False).order_by(TarefaProjeto.nome).all()  # noqa: E712


def _open_macros(db: Session, projeto_id: uuid.UUID | None = None) -> list[TarefaCard]:
    q = db.query(TarefaCard).filter(TarefaCard.status.in_(["pendente", "em_andamento"]))
    if projeto_id:
        q = q.filter(TarefaCard.projeto_id == projeto_id)
    return q.order_by(TarefaCard.created_at.desc()).limit(20).all()


def build_card_link_menu(db: Session, batch: TelegramTaskBatch) -> tuple[str, dict]:
    """Mostra quais tarefas do lote ainda não foram vinculadas a uma macro."""
    items = load_batch_items(db, batch.id)
    # Tarefas já vinculadas ficam marcadas no payload da sessão (linked_item_ids)
    lines = ["Selecione a tarefa para vincular a uma macro:"]
    keyboard: list[list[dict]] = []
    for item in items:
        # callback: tg:item:{item_hex}:card_proj (pede projeto primeiro)
        cb = f"tg:item:{item.id.hex}:card_proj"  # 3+1+4+1+32+1+8 = 50 bytes ✓
        keyboard.append([{"text": item.titulo_original[:40], "callback_data": cb}])
    keyboard.append([{"text": "✅ Pronto", "callback_data": f"tg:batch:{batch.id.hex}:done"}])
    return "\n".join(lines), {"inline_keyboard": keyboard}


def build_projeto_menu_for_item(db: Session, item_hex: str) -> tuple[str, dict]:
    """Pergunta se quer filtrar por projeto antes de ver as macros."""
    projetos = _active_projetos(db)
    keyboard: list[list[dict]] = []
    for idx, p in enumerate(projetos[:8]):  # máx 8 projetos
        cb = f"tg:item:{item_hex}:card_p:{idx}"  # ~52 bytes ✓
        keyboard.append([{"text": f"🎨 {p.nome}", "callback_data": cb}])
    # Sem filtro de projeto
    cb_all = f"tg:item:{item_hex}:card_p:all"  # ~52 bytes ✓
    keyboard.append([{"text": "Sem filtro de projeto", "callback_data": cb_all}])
    keyboard.append([{"text": "✖ Cancelar", "callback_data": f"tg:item:{item_hex}:card_cancel"}])
    return "Filtrar por projeto?", {"inline_keyboard": keyboard}


def build_macro_menu_for_item(db: Session, item_hex: str, projeto_id: uuid.UUID | None) -> tuple[str, dict]:
    """Lista as macros abertas (opcionalmente filtradas por projeto)."""
    macros = _open_macros(db, projeto_id)
    keyboard: list[list[dict]] = []
    for idx, macro in enumerate(macros[:10]):
        cb = f"tg:item:{item_hex}:card_m:{idx}"  # ~52 bytes ✓
        label = macro.titulo[:35]
        if macro.projeto_id:
            p = db.get(TarefaProjeto, macro.projeto_id)
            if p:
                label = f"[{p.nome[:10]}] {macro.titulo[:25]}"
        keyboard.append([{"text": label, "callback_data": cb}])
    if not macros:
        return "Nenhuma macro aberta encontrada. A tarefa ficará como card avulso.", {"inline_keyboard": [
            [{"text": "✅ Ok", "callback_data": f"tg:item:{item_hex}:card_cancel"}]
        ]}
    keyboard.append([{"text": "✖ Manter como card avulso", "callback_data": f"tg:item:{item_hex}:card_cancel"}])
    return "Escolha a macro:", {"inline_keyboard": keyboard}


def link_item_to_macro(db: Session, item: TelegramTaskItem, macro: TarefaCard) -> None:
    """Converte o TarefaCard avulso em subtarefa da macro e remove o card avulso."""
    # Busca o card avulso criado pelo bot
    tarefa = db.query(Tarefa).filter(Tarefa.id == item.tarefa_id).first()

    # Cria subtarefa na macro com dados do item
    ordem = max((st.ordem for st in macro.subtasks), default=-1) + 1
    subtask = TarefaCardSubtask(
        card_id=macro.id,
        texto=item.titulo_original,
        ordem=ordem,
        responsavel=tarefa.responsavel if tarefa else None,
        responsavel_email=tarefa.responsavel_email if tarefa else None,
        data_limite=tarefa.data_limite if tarefa else None,
    )
    db.add(subtask)

    # Remove o card avulso que foi criado para esta tarefa
    if item.card_id:
        avulso = db.query(TarefaCard).filter(TarefaCard.id == item.card_id).first()
        if avulso:
            db.delete(avulso)
        item.card_id = None

    db.commit()


# ---------------------------------------------------------------------------
# Menu de responsável
# ---------------------------------------------------------------------------

def _active_usuarios(db: Session):
    """Retorna lista de usuários ativos ordenada por nome (usada para índice no callback)."""
    from app.models.usuario import Usuario as UsuarioModel
    return db.query(UsuarioModel).filter(UsuarioModel.ativo == True).order_by(UsuarioModel.nome).limit(12).all()  # noqa: E712


def build_responsavel_menu(db: Session, batch_id: uuid.UUID) -> tuple[str, dict]:
    """Retorna lista de usuários ativos como botões inline.

    Usa índice numérico no callback_data para não exceder o limite de 64 bytes
    do Telegram (f'tg:batch:{hex32}:resp_set:{idx}' = máx. 55 bytes).
    """
    usuarios = _active_usuarios(db)
    keyboard: list[list[dict]] = []
    row: list[dict] = []
    for idx, u in enumerate(usuarios):
        cb = f"tg:batch:{batch_id.hex}:resp_set:{idx}"  # ≤55 bytes — dentro do limite
        btn = {"text": u.nome, "callback_data": cb}
        row.append(btn)
        if len(row) == 2:
            keyboard.append(row)
            row = []
    if row:
        keyboard.append(row)
    keyboard.append([{"text": "✏️ Digitar nome / Terceiros", "callback_data": f"tg:batch:{batch_id.hex}:resp_custom"}])
    keyboard.append([{"text": "✅ Deixar como está", "callback_data": f"tg:batch:{batch_id.hex}:done"}])
    return "Quem vai executar essas tarefas?", {"inline_keyboard": keyboard}


def apply_responsavel(db: Session, batch_id: uuid.UUID, responsavel: str, responsavel_email: str | None = None) -> int:
    items = load_batch_items(db, batch_id)
    count = 0
    for item in items:
        tarefa = db.query(Tarefa).filter(Tarefa.id == item.tarefa_id).first()
        if not tarefa:
            continue
        tarefa.responsavel = responsavel
        if responsavel_email is not None:
            tarefa.responsavel_email = responsavel_email  # type: ignore[assignment]
        # Sincroniza no card avulso (se ainda existir como card avulso)
        if item.card_id:
            card = db.query(TarefaCard).filter(TarefaCard.id == item.card_id).first()
            if card:
                card.responsavel = responsavel
                if responsavel_email is not None:
                    card.responsavel_email = responsavel_email
        count += 1
    db.commit()
    return count


# ---------------------------------------------------------------------------
# Menu de datas
# ---------------------------------------------------------------------------

def build_dates_menu(batch_id: uuid.UUID, selected_mode: bool = False) -> tuple[str, dict]:
    prefix = "sel_" if selected_mode else ""
    keyboard: list[list[dict]] = [
        [
            {"text": "Sem data", "callback_data": f"tg:batch:{batch_id.hex}:{prefix}open"},
            {"text": "Hoje", "callback_data": f"tg:batch:{batch_id.hex}:{prefix}today"},
        ],
        [
            {"text": "Amanhã", "callback_data": f"tg:batch:{batch_id.hex}:{prefix}tomorrow"},
            {"text": "Esta semana", "callback_data": f"tg:batch:{batch_id.hex}:{prefix}week"},
        ],
        [
            {"text": "Data fixa", "callback_data": f"tg:batch:{batch_id.hex}:{prefix}fixed"},
            {"text": "Período", "callback_data": f"tg:batch:{batch_id.hex}:{prefix}period"},
        ],
    ]
    if not selected_mode:
        keyboard.append([{"text": "Selecionar itens", "callback_data": f"tg:batch:{batch_id.hex}:select"}])
    keyboard.append([{"text": "✅ Deixar como está", "callback_data": f"tg:batch:{batch_id.hex}:done"}])
    return "Como quer tratar as datas?", {"inline_keyboard": keyboard}


def build_selection_message(db: Session, batch_id: uuid.UUID, selected_ids: set[str]) -> tuple[str, dict]:
    items = load_batch_items(db, batch_id)
    lines = ["Escolha quais tarefas quer ajustar:", ""]
    keyboard: list[list[dict]] = []

    for idx, item in enumerate(items, start=1):
        checked = "☑" if item.id.hex in selected_ids else "☐"
        lines.append(f"{checked} {idx}. {item.titulo_original}")
        keyboard.append([{
            "text": f"{checked} {idx}. {item.titulo_original[:40]}",
            "callback_data": f"tg:item:{item.id.hex}:toggle",
        }])

    keyboard.append([{"text": "Definir data nessas", "callback_data": f"tg:batch:{batch_id.hex}:selected_dates"}])
    keyboard.append([
        {"text": "Limpar seleção", "callback_data": f"tg:batch:{batch_id.hex}:clear_selection"},
        {"text": "✅ Deixar como está", "callback_data": f"tg:batch:{batch_id.hex}:done"},
    ])
    return "\n".join(lines), {"inline_keyboard": keyboard}


# ---------------------------------------------------------------------------
# Aplicação de datas
# ---------------------------------------------------------------------------

def _week_range() -> tuple[date, date]:
    today = date.today()
    end = today + timedelta(days=max(0, 6 - today.weekday()))
    return today, end


def _set_task_dates(tarefa: Tarefa, mode: str, value: date | tuple[date, date] | None = None) -> None:
    if mode == "open":
        tarefa.data_inicio = None  # type: ignore[assignment]
        tarefa.data_fim = None  # type: ignore[assignment]
        tarefa.data_limite = None
    elif mode in {"today", "tomorrow", "fixed"}:
        assert isinstance(value, date)
        tarefa.data_inicio = None  # type: ignore[assignment]
        tarefa.data_fim = None  # type: ignore[assignment]
        tarefa.data_limite = value
    elif mode in {"week", "period"}:
        assert isinstance(value, tuple)
        start, end = value
        tarefa.data_inicio = start  # type: ignore[assignment]
        tarefa.data_fim = end  # type: ignore[assignment]
        tarefa.data_limite = end


def _sync_card_dates(db: Session, item: TelegramTaskItem, tarefa: Tarefa) -> None:
    """Copia data_limite do item de tarefa para o card avulso correspondente."""
    if item.card_id:
        card = db.query(TarefaCard).filter(TarefaCard.id == item.card_id).first()
        if card:
            card.data_limite = tarefa.data_limite


def apply_date_mode(
    db: Session, batch_id: uuid.UUID, mode: str, selected_item_ids: list[str] | None = None
) -> int:
    items = load_batch_items(db, batch_id)
    selected = set(selected_item_ids or [])
    count = 0
    for item in items:
        if selected_item_ids is not None and item.id.hex not in selected:
            continue
        tarefa = db.query(Tarefa).filter(Tarefa.id == item.tarefa_id).first()
        if not tarefa:
            continue
        if mode == "open":
            _set_task_dates(tarefa, "open")
        elif mode == "today":
            _set_task_dates(tarefa, "today", date.today())
        elif mode == "tomorrow":
            _set_task_dates(tarefa, "tomorrow", date.today() + timedelta(days=1))
        elif mode == "week":
            _set_task_dates(tarefa, "week", _week_range())
        _sync_card_dates(db, item, tarefa)
        count += 1
    db.commit()
    return count


def apply_fixed_date(
    db: Session, batch_id: uuid.UUID, fixed_date: date, selected_item_ids: list[str] | None = None
) -> int:
    items = load_batch_items(db, batch_id)
    selected = set(selected_item_ids or [])
    count = 0
    for item in items:
        if selected_item_ids is not None and item.id.hex not in selected:
            continue
        tarefa = db.query(Tarefa).filter(Tarefa.id == item.tarefa_id).first()
        if not tarefa:
            continue
        _set_task_dates(tarefa, "fixed", fixed_date)
        _sync_card_dates(db, item, tarefa)
        count += 1
    db.commit()
    return count


def apply_period(
    db: Session, batch_id: uuid.UUID, start: date, end: date, selected_item_ids: list[str] | None = None
) -> int:
    items = load_batch_items(db, batch_id)
    selected = set(selected_item_ids or [])
    count = 0
    for item in items:
        if selected_item_ids is not None and item.id.hex not in selected:
            continue
        tarefa = db.query(Tarefa).filter(Tarefa.id == item.tarefa_id).first()
        if not tarefa:
            continue
        _set_task_dates(tarefa, "period", (start, end))
        _sync_card_dates(db, item, tarefa)
        count += 1
    db.commit()
    return count


def drop_probable_duplicates(db: Session, batch_id: uuid.UUID) -> int:
    items = load_batch_items(db, batch_id)
    removed = 0
    for item in items:
        if not item.duplicada_de_tarefa_id:
            continue
        tarefa = db.query(Tarefa).filter(Tarefa.id == item.tarefa_id).first()
        if tarefa:
            db.delete(tarefa)
            removed += 1
    db.commit()
    return removed


# ---------------------------------------------------------------------------
# Parsing de datas
# ---------------------------------------------------------------------------

def parse_date_input(raw: str) -> date | None:
    text = raw.strip()
    patterns = [
        r"^(?P<d>\d{2})/(?P<m>\d{2})/(?P<y>\d{4})$",
        r"^(?P<d>\d{2})/(?P<m>\d{2})$",
        r"^(?P<y>\d{4})-(?P<m>\d{2})-(?P<d>\d{2})$",
    ]
    for pattern in patterns:
        match = re.match(pattern, text)
        if not match:
            continue
        day = int(match.group("d"))
        month = int(match.group("m"))
        year = int(match.group("y")) if "y" in match.groupdict() and match.group("y") else date.today().year
        try:
            parsed = date(year, month, day)
            if parsed < date.today() - timedelta(days=365):
                parsed = date(date.today().year, month, day)
            return parsed
        except ValueError:
            return None
    return None


def parse_period_input(raw: str) -> tuple[date, date] | None:
    match = re.match(r"^\s*(.+?)\s+a\s+(.+?)\s*$", raw.strip(), flags=re.IGNORECASE)
    if not match:
        return None
    start = parse_date_input(match.group(1))
    end = parse_date_input(match.group(2))
    if not start or not end or end < start:
        return None
    return start, end
