"""CCLE proteomics (Nusinow et al. 2020) -> per-line percentile rank per protein (optional)."""
import logging
import numpy as np, pandas as pd
from ..paths import RAW
from .util import write, read
from .genes import get_mapper

log = logging.getLogger("ct.proteomics")

def build_proteomics() -> None:
    cands = list((RAW / "proteomics").glob("protein_quant_current_normalized.csv*"))
    p = cands[0] if cands else RAW / "proteomics" / "missing"
    if not p.exists():
        log.warning("CCLE proteomics not present; skipping"); return
    gm = get_mapper()
    df = pd.read_csv(p, low_memory=False)
    sym = df["Gene_Symbol"] if "Gene_Symbol" in df.columns else df.iloc[:, 1]
    df["gene_id"] = sym.map(gm.symbol).astype("Int32")
    df = df.dropna(subset=["gene_id"])
    cols = [c for c in df.columns if "_TenPx" in c]
    models = read("depmap_models")[["model_id", "CCLEName"]].dropna()
    ccle_to_model = dict(zip(models.CCLEName, models.model_id))
    m = df[["gene_id"] + cols].set_index("gene_id")
    m.columns = [c.split("_TenPx")[0] for c in cols]
    m = m.T.groupby(level=0).mean().T
    m = m.groupby(level=0).max()
    m.columns = [ccle_to_model.get(c) for c in m.columns]
    m = m.loc[:, [c for c in m.columns if c is not None]]
    long = m.stack().reset_index(); long.columns = ["gene_id", "model_id", "rel_abundance"]
    long = long.dropna()
    long["pct"] = long.groupby("gene_id")["rel_abundance"].rank(pct=True).astype(np.float32)
    long["gene_id"] = long.gene_id.astype(np.int32)
    write(long, "ccle_proteomics", sort_by=["gene_id", "model_id"])
    log.info("proteomics: %d proteins x %d lines", long.gene_id.nunique(), long.model_id.nunique())
