import json
from pathlib import Path

MONITORING_FILE = Path("/app/backend/uploads/diario_monitoring.json")
DEFAULT_TRIBUNAIS = ["TJES", "TJSP", "TJAM"]


def load_monitoring_config() -> dict:
    if not MONITORING_FILE.exists():
        return {"tribunais": DEFAULT_TRIBUNAIS, "termos_extras": [], "auto_sync": True}
    try:
        data = json.loads(MONITORING_FILE.read_text())
    except Exception:
        data = {}
    return {
        "tribunais": [str(t) for t in (data.get("tribunais") or DEFAULT_TRIBUNAIS)],
        "termos_extras": [str(t).strip() for t in (data.get("termos_extras") or []) if str(t).strip()],
        "auto_sync": bool(data.get("auto_sync", True)),
    }


def save_monitoring_config(data: dict) -> dict:
    normalized = {
        "tribunais": [str(t) for t in (data.get("tribunais") or DEFAULT_TRIBUNAIS)],
        "termos_extras": [str(t).strip() for t in (data.get("termos_extras") or []) if str(t).strip()],
        "auto_sync": bool(data.get("auto_sync", True)),
    }
    MONITORING_FILE.parent.mkdir(parents=True, exist_ok=True)
    MONITORING_FILE.write_text(json.dumps(normalized, ensure_ascii=False, indent=2))
    return normalized
