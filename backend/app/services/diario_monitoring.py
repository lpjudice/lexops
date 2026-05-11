import json
from pathlib import Path

MONITORING_FILE = Path("/app/backend/uploads/diario_monitoring.json")
DEFAULT_TRIBUNAIS = ["TJES", "TJSP", "TJAM"]


def _lista_limpa(valores) -> list[str]:
    return [str(t).strip() for t in (valores or []) if str(t).strip()]


def load_monitoring_config() -> dict:
    if not MONITORING_FILE.exists():
        return {
            "tribunais": DEFAULT_TRIBUNAIS,
            "termos_extras": [],
            "advogados_monitorados": [],
            "clientes_monitorados_extras": [],
            "auto_sync": True,
        }
    try:
        data = json.loads(MONITORING_FILE.read_text())
    except Exception:
        data = {}
    advogados = _lista_limpa(data.get("advogados_monitorados"))
    # Compatibilidade: os antigos "nomes adicionais" viram advogados monitorados
    # para preservar a leitura principal até o usuário recategorizar na tela.
    if not advogados:
        advogados = _lista_limpa(data.get("termos_extras"))
    clientes_extras = _lista_limpa(data.get("clientes_monitorados_extras"))
    return {
        "tribunais": [str(t) for t in (data.get("tribunais") or DEFAULT_TRIBUNAIS)],
        "termos_extras": advogados,
        "advogados_monitorados": advogados,
        "clientes_monitorados_extras": clientes_extras,
        "auto_sync": bool(data.get("auto_sync", True)),
    }


def save_monitoring_config(data: dict) -> dict:
    advogados = _lista_limpa(data.get("advogados_monitorados"))
    if not advogados:
        advogados = _lista_limpa(data.get("termos_extras"))
    clientes_extras = _lista_limpa(data.get("clientes_monitorados_extras"))
    normalized = {
        "tribunais": [str(t) for t in (data.get("tribunais") or DEFAULT_TRIBUNAIS)],
        "termos_extras": advogados,
        "advogados_monitorados": advogados,
        "clientes_monitorados_extras": clientes_extras,
        "auto_sync": bool(data.get("auto_sync", True)),
    }
    MONITORING_FILE.parent.mkdir(parents=True, exist_ok=True)
    MONITORING_FILE.write_text(json.dumps(normalized, ensure_ascii=False, indent=2))
    return normalized
