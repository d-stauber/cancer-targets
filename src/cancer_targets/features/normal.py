"""Tissue weights and vital-weighted normal references."""
import re
import numpy as np, pandas as pd, yaml
from ..paths import CONFIG
from ..harmonize.util import read, exists

def load_thresholds() -> dict:
    return yaml.safe_load((CONFIG / "weights.yaml").read_text())

def tissue_weight_table() -> list[tuple[re.Pattern, str, float]]:
    tw = pd.read_csv(CONFIG / "tissue_weights.csv")
    return [(re.compile(p, re.I), g, float(w)) for p, g, w in zip(tw.pattern, tw.group, tw.weight)]

def weight_for(tissue: str, rules=None) -> tuple[str, float]:
    rules = rules or tissue_weight_table()
    t = tissue.lower().replace("_", " ") if "_" in tissue else tissue.lower()
    for rx, g, w in rules:
        if rx.search(t) or rx.search(tissue.lower()):
            return g, w
    return "moderate", 0.6

def normal_reference(long: pd.DataFrame, forgiveness: float) -> pd.DataFrame:
    """long: gene_id, tissue, value -> per gene: n_ref (vital-weighted max), n_vital_max, top_tissue."""
    rules = tissue_weight_table()
    tissues = long.tissue.unique()
    w = {t: weight_for(t, rules)[1] for t in tissues}
    d = long.copy()
    d["w"] = d.tissue.map(w).astype(np.float32)
    d = d[d.w > 0]
    d["adj"] = d.value - (1 - d.w) * forgiveness
    idx = d.groupby("gene_id")["adj"].idxmax()
    top = d.loc[idx, ["gene_id", "adj", "tissue"]].rename(columns={"adj": "n_ref", "tissue": "n_ref_tissue"})
    vital = d[d.w >= 1.0].groupby("gene_id")["value"].max().rename("n_vital_max").reset_index()
    out = top.merge(vital, how="left")
    out["n_ref"] = out.n_ref.clip(lower=0).astype(np.float32)
    out["n_vital_max"] = out.n_vital_max.fillna(0).astype(np.float32)
    return out

def hpa_normal_penalty() -> pd.DataFrame:
    """S_hpa = 1 - max_t(w_t * level/3); also max level in vital tissues."""
    if not exists("hpa_normal_ihc"):
        return pd.DataFrame(columns=["gene_id", "S_hpa", "hpa_vital_max_level"])
    h = read("hpa_normal_ihc")
    rules = tissue_weight_table()
    w = {t: weight_for(t, rules)[1] for t in h.tissue.unique()}
    h["w"] = h.tissue.map(w).astype(np.float32)
    h = h[h.w > 0]
    h["pen"] = h.w * h.level_num / 3.0
    s = h.groupby("gene_id")["pen"].max().rename("pen").reset_index()
    s["S_hpa"] = (1 - s.pen).astype(np.float32)
    v = h[h.w >= 1.0].groupby("gene_id")["level_num"].max().rename("hpa_vital_max_level").reset_index()
    return s[["gene_id", "S_hpa"]].merge(v, how="left")
