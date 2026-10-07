"""DuckDB access for the API: one read-only connection per process, cursor per request.
Custom (user-uploaded) contexts live in data/custom/*.parquet and are unioned in at query time."""
import threading
import duckdb, pandas as pd
from ..paths import DB, DATA

CUSTOM = DATA / "custom"
CUSTOM.mkdir(parents=True, exist_ok=True)
_lock = threading.Lock()
_con: duckdb.DuckDBPyConnection | None = None
_db_mtime: float = 0.0

def _custom_views(con):
    cc, cs, csc = CUSTOM / "custom_contexts.parquet", CUSTOM / "custom_summary.parquet", CUSTOM / "custom_scores.parquet"
    if cc.exists() and cs.exists():
        con.execute(f"create or replace view all_contexts as select * from contexts union all by name select * from read_parquet('{cc.as_posix()}')")
        con.execute(f"create or replace view all_summary as select * from expr_context_summary union all by name select * from read_parquet('{cs.as_posix()}')")
    else:
        con.execute("create or replace view all_contexts as select * from contexts")
        con.execute("create or replace view all_summary as select * from expr_context_summary")
    if csc.exists():
        con.execute(f"create or replace view all_scores as select * from gene_context_scores union all by name select * from read_parquet('{csc.as_posix()}')")
    else:
        con.execute("create or replace view all_scores as select * from gene_context_scores")

def _open() -> duckdb.DuckDBPyConnection:
    base = duckdb.connect(str(DB), read_only=True)
    con = duckdb.connect()
    con.execute(f"attach '{DB.as_posix()}' as ct (read_only)")
    for (name,) in base.execute("select table_name from information_schema.tables").fetchall():
        con.execute(f"create or replace view {name} as select * from ct.{name}")
    base.close()
    _custom_views(con)
    return con

def connect() -> duckdb.DuckDBPyConnection:
    """One connection per process; transparently reopened when data/ct.duckdb is rebuilt."""
    global _con, _db_mtime
    with _lock:
        mtime = DB.stat().st_mtime if DB.exists() else 0.0
        if _con is not None and mtime != _db_mtime:
            try:
                _con.close()
            except Exception:
                pass
            _con = None
        if _con is None:
            _con = _open()
            _db_mtime = mtime
        return _con

def refresh_custom():
    con = connect()
    with _lock:
        _custom_views(con)

def q(sql: str, params: list | None = None) -> pd.DataFrame:
    con = connect()
    with _lock:
        return con.execute(sql, params or []).df()

def columnar(df: pd.DataFrame) -> dict:
    """Column-oriented JSON with NaN -> null."""
    out = {}
    for c in df.columns:
        s = df[c]
        if s.dtype.kind in "fc":
            out[c] = [None if pd.isna(v) else float(v) for v in s]
        elif s.dtype.kind in "iu":
            out[c] = [None if pd.isna(v) else int(v) for v in s]
        elif s.dtype.kind == "b":
            out[c] = [None if pd.isna(v) else bool(v) for v in s]
        else:
            out[c] = [None if (v is None or (isinstance(v, float) and pd.isna(v)) or v is pd.NA) else v for v in s.tolist()]
    return out

def records(df: pd.DataFrame) -> list[dict]:
    cols = columnar(df)
    return [dict(zip(cols.keys(), vals)) for vals in zip(*cols.values())] if len(df) else []
