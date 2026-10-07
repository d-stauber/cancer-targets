from pathlib import Path
import os

ROOT = Path(os.environ.get("CT_ROOT", Path(__file__).resolve().parents[2]))
CONFIG = ROOT / "config"
DATA = Path(os.environ.get("CT_DATA", ROOT / "data"))
RAW = DATA / "raw"
INTERIM = DATA / "interim"
PROCESSED = DATA / "processed"
DB = DATA / "ct.duckdb"
WEB_DIST = ROOT / "web" / "dist"

for _p in (RAW, INTERIM, PROCESSED):
    _p.mkdir(parents=True, exist_ok=True)
