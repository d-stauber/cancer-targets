import json, datetime as dt
from pathlib import Path
from ..paths import RAW

MANIFEST = RAW / "manifest.json"

def load() -> dict:
    if MANIFEST.exists():
        return json.loads(MANIFEST.read_text())
    return {}

def record(source: str, name: str, **info):
    m = load()
    m.setdefault(source, {})[name] = {**info, "fetched_at": dt.datetime.now().isoformat(timespec="seconds")}
    MANIFEST.write_text(json.dumps(m, indent=2))
