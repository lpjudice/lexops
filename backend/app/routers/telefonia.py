"""Chamadas de voz via Bland.ai:
  - GET  /telefonia/status        — diagnóstico rápido (configurado ou não).
  - POST /telefonia/me-ligar      — dispara uma chamada para o número do
                                     Lucas (settings.telefonia_numero_lucas)
                                     com uma tarefa/aviso em linguagem natural.
  - POST /telefonia/ligar         — dispara uma chamada para um número
                                     informado (ex.: cliente/parte), em nome
                                     do escritório.
  - GET  /telefonia/chamadas/{id} — status de uma chamada disparada.

Todas exigem usuário autenticado — este módulo nunca é chamado por quem não
está logado no painel.
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException

from app.config import settings
from app.dependencies import get_current_user
from app.models.usuario import Usuario
from app.schemas.telefonia import LigarRequest, MeLigarRequest
from app.services import bland_api

router = APIRouter(prefix="/telefonia", tags=["telefonia"])


@router.get("/status")
def status(usuario: Usuario = Depends(get_current_user)):
    return {
        "configurado": bool(settings.bland_api_key),
        "numero_lucas_configurado": bool(settings.telefonia_numero_lucas),
    }


@router.post("/me-ligar")
def me_ligar(payload: MeLigarRequest, usuario: Usuario = Depends(get_current_user)):
    if not settings.telefonia_numero_lucas:
        raise HTTPException(400, "Número do Lucas não configurado (telefonia_numero_lucas).")
    resultado = bland_api.disparar_chamada(
        telefone=settings.telefonia_numero_lucas,
        tarefa=payload.tarefa,
        voice=payload.voice,
    )
    if resultado is None:
        raise HTTPException(502, "Bland.ai não configurado ou chamada falhou.")
    if "erro" in resultado:
        raise HTTPException(502, f"Erro da Bland.ai: {resultado['erro']}")
    return resultado


@router.post("/ligar")
def ligar(payload: LigarRequest, usuario: Usuario = Depends(get_current_user)):
    resultado = bland_api.disparar_chamada(
        telefone=payload.telefone,
        tarefa=payload.tarefa,
        voice=payload.voice,
    )
    if resultado is None:
        raise HTTPException(502, "Bland.ai não configurado, número inválido ou chamada falhou.")
    if "erro" in resultado:
        raise HTTPException(502, f"Erro da Bland.ai: {resultado['erro']}")
    return resultado


@router.get("/chamadas/{call_id}")
def consultar_chamada(call_id: str, usuario: Usuario = Depends(get_current_user)):
    resultado = bland_api.consultar_chamada(call_id)
    if resultado is None:
        raise HTTPException(502, "Bland.ai não configurado ou consulta falhou.")
    return resultado
