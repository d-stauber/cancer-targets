"""Create/refresh the DuckDB database with views over processed parquet files."""
import logging
import duckdb
from ..paths import PROCESSED, DB

log = logging.getLogger("ct.db")

def build_db():
    tmp = DB.with_suffix(".duckdb.tmp")
    if tmp.exists():
        tmp.unlink()
    con = duckdb.connect(str(tmp))
    for p in sorted(PROCESSED.glob("*.parquet")):
        con.execute(f"create or replace view {p.stem} as select * from read_parquet('{p.as_posix()}')")
    views = [r[0] for r in con.execute("select table_name from information_schema.tables").fetchall()]
    log.info("db views: %s", views)
    con.close()
    import os
    os.replace(tmp, DB)
