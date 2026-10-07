import logging, re
import pandas as pd
from ..paths import PROCESSED, INTERIM

log = logging.getLogger("ct.harmonize")

def write(df: pd.DataFrame, name: str, sort_by: list[str] | None = None) -> None:
    if sort_by:
        df = df.sort_values(sort_by, kind="stable")
    path = PROCESSED / f"{name}.parquet"
    df.to_parquet(path, index=False, compression="zstd")
    log.info("wrote %s (%d rows, %d cols)", path.name, len(df), df.shape[1])

def read(name: str, columns=None) -> pd.DataFrame:
    return pd.read_parquet(PROCESSED / f"{name}.parquet", columns=columns)

def exists(name: str) -> bool:
    return (PROCESSED / f"{name}.parquet").exists()

def strip_version(s: pd.Series) -> pd.Series:
    return s.astype(str).str.replace(r"\.\d+$", "", regex=True)

def log_unmapped(source: str, ids) -> None:
    ids = list(ids)
    if ids:
        pd.Series(ids, name="id").to_csv(INTERIM / f"unmapped_{source}.csv", index=False)
        log.warning("%s: %d unmapped ids written to unmapped_%s.csv", source, len(ids), source)

def col(df: pd.DataFrame, *candidates: str) -> str:
    """Case-insensitive column lookup with assertion."""
    lower = {c.lower(): c for c in df.columns}
    for c in candidates:
        if c.lower() in lower:
            return lower[c.lower()]
    raise KeyError(f"none of {candidates} in columns {list(df.columns)[:20]}")
