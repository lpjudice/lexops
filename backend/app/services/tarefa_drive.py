"""Código único por entidade + lógica de pastas no Google Drive para tarefas.

Estrutura no Drive (sob a raiz LexOps):
  Tarefas/<abrev>-<codigo>/                      ← anexos da tarefa (menu original)
  Tarefas em Card/<abrev>-<codigo>/              ← anexos do card macro
  Tarefas em Card/<abrev>-<codigo>/<sub>-<cod>/  ← anexos da subtarefa

O código (6 chars base36) fica no FINAL dos nomes de pastas/arquivos para não
quebrar ordenação por prefixo (1-2-3-4) e servir de identificador único.
"""

import re
import secrets

_ALFABETO = "abcdefghijklmnopqrstuvwxyz0123456789"


def gerar_codigo(n: int = 6) -> str:
    """Código curto base36 (ex.: 'k7m2q9')."""
    return "".join(secrets.choice(_ALFABETO) for _ in range(n))


def abreviar(titulo: str | None, max_len: int = 24) -> str:
    """Abrevia o título para nome de pasta: remove chars inválidos e trunca."""
    t = (titulo or "Tarefa").strip()
    t = re.sub(r'[/\\:*?"<>|]', "", t)
    t = re.sub(r"\s+", " ", t).strip()
    if len(t) > max_len:
        t = t[:max_len].rstrip()
    return t or "Tarefa"


def nome_arquivo_com_codigo(nome: str, codigo: str) -> str:
    """Adiciona o código ao FINAL do nome, antes da extensão REAL (se houver).

    Só considera extensão um sufixo `.ext` de 1–5 chars alfanuméricos no fim do
    nome; nomes com '.' no meio (ex.: "…Mandado. — Intimação") recebem o código
    literalmente no fim, sem quebrar o nome.
    """
    m = re.search(r"\.([A-Za-z0-9]{1,5})$", nome)
    if m:
        return f"{nome[:m.start()]}-{codigo}.{m.group(1)}"
    return f"{nome}-{codigo}"


def pasta_card(abrev: str, codigo: str) -> list[str]:
    return ["Tarefas em Card", f"{abrev}-{codigo}"]


def pasta_card_subtask(macro_abrev: str, codigo: str, sub_abrev: str) -> list[str]:
    return ["Tarefas em Card", f"{macro_abrev}-{codigo}", f"{sub_abrev}-{codigo}"]


def pasta_tarefa(abrev: str, codigo: str) -> list[str]:
    return ["Tarefas", f"{abrev}-{codigo}"]
