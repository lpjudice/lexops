from __future__ import annotations

import re


CNJ_TJ_MAP = {
    "01": "TJAC",
    "02": "TJAL",
    "03": "TJAP",
    "04": "TJAM",
    "05": "TJBA",
    "06": "TJCE",
    "07": "TJDFT",
    "08": "TJES",
    "09": "TJGO",
    "10": "TJMA",
    "11": "TJMT",
    "12": "TJMS",
    "13": "TJMG",
    "14": "TJPA",
    "15": "TJPB",
    "16": "TJPR",
    "17": "TJPE",
    "18": "TJPI",
    "19": "TJRJ",
    "20": "TJRN",
    "21": "TJRS",
    "22": "TJRO",
    "23": "TJRR",
    "24": "TJSC",
    "25": "TJSE",
    "26": "TJSP",
    "27": "TJTO",
}


def normalizar_cnj(numero: str) -> str:
    return re.sub(r"\D", "", numero or "")


def normalizar_tribunal(tribunal: str | None) -> str:
    return re.sub(r"[^A-Z0-9]", "", (tribunal or "").upper())


def inferir_tribunal_pelo_cnj(numero_cnj: str) -> str | None:
    digits = normalizar_cnj(numero_cnj)
    if len(digits) != 20:
        return None

    ramo = digits[13]
    tribunal_codigo = digits[14:16]

    if ramo == "8":
        return CNJ_TJ_MAP.get(tribunal_codigo)
    if ramo == "4" and tribunal_codigo in {"01", "02", "03", "04", "05", "06"}:
        return f"TRF{int(tribunal_codigo)}"
    if ramo == "6":
        return "STJ"
    if ramo == "7":
        return "STM"

    return None


def candidatos_tribunal(numero_cnj: str, tribunal_informado: str | None) -> list[str]:
    candidatos: list[str] = []

    tribunal_norm = normalizar_tribunal(tribunal_informado)
    inferido = inferir_tribunal_pelo_cnj(numero_cnj)

    for item in (tribunal_norm, inferido):
        if item and item not in candidatos:
            candidatos.append(item)

    return candidatos
