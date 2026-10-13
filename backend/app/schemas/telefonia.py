from __future__ import annotations

from pydantic import BaseModel


class MeLigarRequest(BaseModel):
    tarefa: str
    voice: str | None = None


class LigarRequest(BaseModel):
    telefone: str
    tarefa: str
    voice: str | None = None
