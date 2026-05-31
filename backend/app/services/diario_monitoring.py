import json
import re
from pathlib import Path

MONITORING_FILE = Path("/app/backend/uploads/diario_monitoring.json")
DEFAULT_TRIBUNAIS = ["TJES", "TJSP", "TJAM"]


def _normalizar_oabs(raw) -> list[dict]:
    """Normaliza a lista de OABs para [{'numero': '14477', 'uf': 'ES'}], sem duplicar."""
    resultado: list[dict] = []
    vistos: set[tuple[str, str]] = set()
    for item in raw or []:
        if not isinstance(item, dict):
            continue
        numero = re.sub(r"\D", "", str(item.get("numero") or ""))
        uf = str(item.get("uf") or "").strip().upper()[:2]
        if not numero or len(uf) != 2:
            continue
        chave = (numero, uf)
        if chave in vistos:
            continue
        vistos.add(chave)
        resultado.append({"numero": numero, "uf": uf})
    return resultado


def _normalizar(data: dict) -> dict:
    return {
        "tribunais": [str(t) for t in (data.get("tribunais") or DEFAULT_TRIBUNAIS)],
        "termos_extras": [str(t).strip() for t in (data.get("termos_extras") or []) if str(t).strip()],
        "oabs": _normalizar_oabs(data.get("oabs")),
        "auto_sync": bool(data.get("auto_sync", True)),
    }


def load_monitoring_config() -> dict:
    if not MONITORING_FILE.exists():
        return _normalizar({})
    try:
        data = json.loads(MONITORING_FILE.read_text())
    except Exception:
        data = {}
    return _normalizar(data)


def save_monitoring_config(data: dict) -> dict:
    normalized = _normalizar(data)
    MONITORING_FILE.parent.mkdir(parents=True, exist_ok=True)
    MONITORING_FILE.write_text(json.dumps(normalized, ensure_ascii=False, indent=2))
    return normalized
