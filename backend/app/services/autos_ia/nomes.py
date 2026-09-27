"""Deriva um nome legível pro arquivo a partir do próprio nome do arquivo — sem
IA nenhuma, só parsing de string. O nome já vem formatado como
"NNN - AAAA-MM-DD - Tipo - resumo.ext" (ver orchestrator.py,
_nome_documento_andamento — arquivo travado, não mexer); aqui só reaproveita
essa estrutura conhecida pra uma exibição mais compacta na listagem de
documentos, descartando o número sequencial e a data (já mostrados em outras
colunas da tela) e mantendo tipo+resumo, que é o que ajuda a reconhecer o
documento num relance.
"""
import re
from pathlib import Path

_PADRAO_NOME_GERADO = re.compile(r"^\d{2,4}\s*-\s*(?:\d{4}-\d{2}-\d{2}|sem-data)\s*-\s*(.+)$")


def derivar_nome_indexado(arquivo_nome: str | None) -> str | None:
    if not arquivo_nome:
        return None
    stem = Path(arquivo_nome).stem
    m = _PADRAO_NOME_GERADO.match(stem)
    if m:
        resto = m.group(1).strip(" -")
        if resto:
            return resto
    return stem.replace("_", " ").strip() or None
