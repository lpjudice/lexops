"""
Integração com Google Calendar.

Fluxo OAuth:
  1. GET /auth/google          → redireciona para consent screen
  2. GET /auth/google/callback → troca code por tokens, salva em tokens.json
  3. Ao criar/atualizar prazo  → cria/atualiza evento no calendário
"""

import os
from datetime import date, timedelta

import httpx
from app.services.google_master_tokens import load_master_google_tokens, save_master_google_tokens

SCOPES = " ".join([
    "https://www.googleapis.com/auth/calendar",
    "https://www.googleapis.com/auth/gmail.readonly",
    "https://www.googleapis.com/auth/gmail.send",
    "https://www.googleapis.com/auth/drive.file",
])
CALENDAR_API = "https://www.googleapis.com/calendar/v3"


def _get_client_config() -> dict:
    return {
        "client_id": os.getenv("GOOGLE_CLIENT_ID", ""),
        "client_secret": os.getenv("GOOGLE_CLIENT_SECRET", ""),
        "redirect_uri": os.getenv("GOOGLE_REDIRECT_URI", "http://localhost:8000/auth/google/callback"),
    }


def get_auth_url() -> str:
    cfg = _get_client_config()
    params = {
        "client_id": cfg["client_id"],
        "redirect_uri": cfg["redirect_uri"],
        "response_type": "code",
        "scope": SCOPES,
        "access_type": "offline",
        "prompt": "consent",
    }
    qs = "&".join(f"{k}={v}" for k, v in params.items())
    return f"https://accounts.google.com/o/oauth2/v2/auth?{qs}"


def exchange_code(code: str) -> dict:
    cfg = _get_client_config()
    resp = httpx.post(
        "https://oauth2.googleapis.com/token",
        data={
            "code": code,
            "client_id": cfg["client_id"],
            "client_secret": cfg["client_secret"],
            "redirect_uri": cfg["redirect_uri"],
            "grant_type": "authorization_code",
        },
    )
    resp.raise_for_status()
    tokens = resp.json()
    save_master_google_tokens(tokens)
    return tokens


def _load_tokens() -> dict | None:
    return load_master_google_tokens()


def _refresh_token(tokens: dict) -> dict:
    cfg = _get_client_config()
    resp = httpx.post(
        "https://oauth2.googleapis.com/token",
        data={
            "refresh_token": tokens["refresh_token"],
            "client_id": cfg["client_id"],
            "client_secret": cfg["client_secret"],
            "grant_type": "refresh_token",
        },
    )
    resp.raise_for_status()
    new_tokens = {**tokens, **resp.json()}
    save_master_google_tokens(new_tokens)
    return new_tokens


def _auth_header() -> dict | None:
    tokens = _load_tokens()
    if not tokens:
        return None
    # tenta com access_token; se falhar, faz refresh
    return {"Authorization": f"Bearer {tokens['access_token']}"}


def criar_evento(
    titulo: str,
    data_limite: date,
    descricao: str = "",
    event_id: str | None = None,
) -> str | None:
    """
    Cria ou atualiza evento no Google Calendar.
    Retorna o event_id criado/atualizado, ou None se não estiver autenticado.
    """
    tokens = _load_tokens()
    if not tokens:
        return None

    headers = {"Authorization": f"Bearer {tokens['access_token']}", "Content-Type": "application/json"}

    body = {
        "summary": titulo,
        "description": descricao,
        "start": {"date": data_limite.isoformat()},
        "end": {"date": (data_limite + timedelta(days=1)).isoformat()},
        "reminders": {
            "useDefault": False,
            "overrides": [
                {"method": "popup", "minutes": 60 * 24 * 2},   # 2 dias antes
                {"method": "popup", "minutes": 60 * 24 * 5},   # 5 dias antes
            ],
        },
    }

    if event_id:
        resp = httpx.put(
            f"{CALENDAR_API}/calendars/primary/events/{event_id}",
            headers=headers,
            json=body,
        )
    else:
        resp = httpx.post(
            f"{CALENDAR_API}/calendars/primary/events",
            headers=headers,
            json=body,
        )

    if resp.status_code == 401:
        # token expirado — tenta refresh
        try:
            tokens = _refresh_token(tokens)
            headers["Authorization"] = f"Bearer {tokens['access_token']}"
            if event_id:
                resp = httpx.put(
                    f"{CALENDAR_API}/calendars/primary/events/{event_id}",
                    headers=headers, json=body,
                )
            else:
                resp = httpx.post(
                    f"{CALENDAR_API}/calendars/primary/events",
                    headers=headers, json=body,
                )
        except Exception:
            return None

    if resp.is_success:
        return resp.json().get("id")
    return None


def deletar_evento(event_id: str) -> bool:
    tokens = _load_tokens()
    if not tokens:
        return False
    headers = {"Authorization": f"Bearer {tokens['access_token']}"}
    resp = httpx.delete(
        f"{CALENDAR_API}/calendars/primary/events/{event_id}",
        headers=headers,
    )
    return resp.status_code in (204, 410)


def google_conectado() -> bool:
    return _load_tokens() is not None


def _listar_eventos_do_dia(data: date, tokens: dict) -> list[dict]:
    """Lista eventos com horário de um dia específico (para calcular slots livres)."""
    headers = {"Authorization": f"Bearer {tokens['access_token']}"}
    # BRT (UTC-3) boundaries
    start = f"{data.isoformat()}T00:00:00-03:00"
    end = f"{data.isoformat()}T23:59:59-03:00"
    resp = httpx.get(
        f"{CALENDAR_API}/calendars/primary/events",
        headers=headers,
        params={
            "timeMin": start,
            "timeMax": end,
            "singleEvents": "true",
            "orderBy": "startTime",
        },
        timeout=30,
    )
    if not resp.is_success:
        return []
    return resp.json().get("items", [])


def _proximo_slot_livre(eventos: list[dict], data: date, duracao_min: int = 30) -> tuple[str, str]:
    """
    Retorna (start_datetime, end_datetime) para o próximo slot livre no dia.
    Horário comercial: 9:00–18:00 (BRT).
    """
    from datetime import datetime, timezone, timedelta as td

    horario_inicio = 9 * 60   # 09:00 em minutos desde meia-noite
    horario_fim = 18 * 60     # 18:00

    # Extrair intervalos ocupados
    ocupados: list[tuple[int, int]] = []
    brt = timezone(td(hours=-3))
    for ev in eventos:
        start_str = ev.get("start", {}).get("dateTime")
        end_str = ev.get("end", {}).get("dateTime")
        if not start_str or not end_str:
            continue  # all-day event — ignora
        try:
            s = datetime.fromisoformat(start_str).astimezone(brt)
            e = datetime.fromisoformat(end_str).astimezone(brt)
            ocupados.append((s.hour * 60 + s.minute, e.hour * 60 + e.minute))
        except Exception:
            pass

    # Percorre slots de 30 min dentro do horário comercial
    slot = horario_inicio
    while slot + duracao_min <= horario_fim:
        slot_end = slot + duracao_min
        conflict = any(
            not (slot_end <= occ_s or slot >= occ_e)
            for occ_s, occ_e in ocupados
        )
        if not conflict:
            d = data.isoformat()
            return (
                f"{d}T{slot // 60:02d}:{slot % 60:02d}:00-03:00",
                f"{d}T{slot_end // 60:02d}:{slot_end % 60:02d}:00-03:00",
            )
        slot += duracao_min

    # Fallback: primeiro slot do dia mesmo que conflite
    d = data.isoformat()
    return f"{d}T09:00:00-03:00", f"{d}T09:30:00-03:00"


def criar_evento_tarefa(
    titulo: str,
    data_limite: date,
    descricao: str = "",
    event_id: str | None = None,
) -> str | None:
    """
    Cria ou atualiza evento TIMED (não all-day) para uma tarefa,
    escolhendo o próximo slot livre no horário comercial.
    Retorna o event_id criado/atualizado, ou None se falhar.
    """
    tokens = _load_tokens()
    if not tokens:
        return None

    def _do(tkns: dict) -> str | None:
        headers = {"Authorization": f"Bearer {tkns['access_token']}", "Content-Type": "application/json"}

        eventos = _listar_eventos_do_dia(data_limite, tkns)
        if event_id:
            eventos = [e for e in eventos if e.get("id") != event_id]

        start_dt, end_dt = _proximo_slot_livre(eventos, data_limite)

        body = {
            "summary": f"📋 {titulo}",
            "description": descricao or f"Tarefa: {titulo}",
            "start": {"dateTime": start_dt, "timeZone": "America/Sao_Paulo"},
            "end": {"dateTime": end_dt, "timeZone": "America/Sao_Paulo"},
            "reminders": {
                "useDefault": False,
                "overrides": [
                    {"method": "popup", "minutes": 60},
                    {"method": "popup", "minutes": 1440},
                ],
            },
        }

        if event_id:
            resp = httpx.put(
                f"{CALENDAR_API}/calendars/primary/events/{event_id}",
                headers=headers, json=body, timeout=30,
            )
        else:
            resp = httpx.post(
                f"{CALENDAR_API}/calendars/primary/events",
                headers=headers, json=body, timeout=30,
            )
        resp.raise_for_status()
        return resp.json().get("id")

    try:
        return _do(tokens)
    except httpx.HTTPStatusError as e:
        if e.response.status_code == 401:
            new_tokens = _refresh_token(tokens)
            return _do(new_tokens)
        return None
    except Exception:
        return None
