"""PRISM Repurposing drug screens (Broad): single-dose log2 fold-change viability (24Q2 extended primary, 6.8k compounds)
and 8-point dose-response parameters (19Q4 secondary, AUC / IC50)."""
import logging, re
import numpy as np, pandas as pd
from ..paths import RAW
from .util import write, col
from .genes import get_mapper

log = logging.getLogger("ct.prism")
P = RAW / "prism"

def core_id(s: pd.Series) -> pd.Series:
    """'BRD:BRD-K19687926-379-07-4' / 'BRD-K19687926-001-01-7' -> 'BRD-K19687926' (same molecule, different batch/salt)."""
    return s.astype(str).str.replace(r"^BRD:", "", regex=True).str.extract(r"^(BRD-[A-Z]\d{8})")[0]

def _split_targets(s) -> list[str]:
    if not isinstance(s, str):
        return []
    return [t.strip() for t in re.split(r"[,;|]", s) if t.strip()]

def build_prism() -> None:
    cl = P / "Repurposing_Public_24Q2_Extended_Primary_Compound_List.csv"
    mx = P / "Repurposing_Public_24Q2_Extended_Primary_Data_Matrix.csv"
    if not (cl.exists() and mx.exists()):
        log.warning("PRISM 24Q2 files missing; skipping"); return
    gm = get_mapper()
    c = pd.read_csv(cl)
    comp = pd.DataFrame({
        "broad_id": c["IDs"].astype(str), "name": c["Drug.Name"].astype(str).str.strip(),
        "moa": c["MOA"], "targets": c["repurposing_target"], "screen": c["screen"], "dose_um": pd.to_numeric(c["dose"], errors="coerce"),
        "synonyms": c["Synonyms"]})
    comp = comp.drop_duplicates("broad_id")
    comp["core_id"] = core_id(comp.broad_id)
    # drug -> target genes
    rows = [(b, t) for b, ts in zip(comp.broad_id, comp.targets) for t in _split_targets(ts)]
    dt = pd.DataFrame(rows, columns=["broad_id", "target_symbol"])
    dt["gene_id"] = dt.target_symbol.map(gm.symbol).astype("Int32")
    unmapped = dt[dt.gene_id.isna()].target_symbol.unique()
    log.info("PRISM: %d compounds, %d target links (%d symbols unmapped, e.g. %s)", len(comp), len(dt), len(unmapped), list(unmapped[:5]))
    dt = dt.dropna(subset=["gene_id"]).assign(gene_id=lambda d: d.gene_id.astype(np.int32)).drop_duplicates(["broad_id", "gene_id"])
    # single-dose LFC matrix: rows compounds, cols DepMap model ids
    m = pd.read_csv(mx, index_col=0)
    m.index = m.index.astype(str)
    long = m.stack().reset_index(); long.columns = ["broad_id", "model_id", "lfc"]
    long["lfc"] = long.lfc.astype(np.float32)
    long = long[long.broad_id.isin(comp.broad_id)]
    comp["n_lines"] = comp.broad_id.map(long.groupby("broad_id").size()).fillna(0).astype(np.int32)
    comp["median_lfc"] = comp.broad_id.map(long.groupby("broad_id").lfc.median()).astype(np.float32)
    comp["frac_sensitive"] = comp.broad_id.map(long.assign(s=long.lfc < -1).groupby("broad_id").s.mean()).astype(np.float32)
    write(long, "prism_lfc", sort_by=["model_id", "broad_id"])
    write(dt, "prism_targets", sort_by=["gene_id", "broad_id"])
    # secondary dose-response (optional)
    dr = P / "secondary-screen-dose-response-curve-parameters.csv"
    if dr.exists():
        d = pd.read_csv(dr, low_memory=False)
        bid, mid = col(d, "broad_id"), col(d, "depmap_id")
        keep = pd.DataFrame({"broad_id": d[bid].astype(str), "model_id": d[mid].astype(str),
                             "auc": pd.to_numeric(d[col(d, "auc")], errors="coerce").astype(np.float32),
                             "ic50_um": pd.to_numeric(d[col(d, "ic50")], errors="coerce").astype(np.float32),
                             "ec50_um": pd.to_numeric(d[col(d, "ec50")], errors="coerce").astype(np.float32),
                             "r2": pd.to_numeric(d[col(d, "r2")], errors="coerce").astype(np.float32),
                             "screen_id": d[col(d, "screen_id")].astype(str) if "screen_id" in d.columns else None,
                             "name": d[col(d, "name")].astype(str), "moa": d[col(d, "moa")] if "moa" in d.columns else None,
                             "target": d[col(d, "target")] if "target" in d.columns else None})
        keep = keep.dropna(subset=["auc"])
        keep["core_id"] = core_id(keep.broad_id)
        # one AUC per molecule x line: prefer the latest screen (technical redos are MTS010), then the lowest r2-weighted AUC
        keep = keep.sort_values(["core_id", "model_id", "screen_id", "r2"]).drop_duplicates(["core_id", "model_id"], keep="last")
        write(keep.drop(columns=["name", "moa", "target", "broad_id"]), "prism_auc", sort_by=["model_id", "core_id"])
        comp["n_lines_auc"] = comp.core_id.map(keep.groupby("core_id").size()).fillna(0).astype(np.int32)
        missing = keep[~keep.core_id.isin(comp.core_id)]
        log.info("PRISM secondary: %d molecule x line AUCs (%d molecules; %d not in the 24Q2 compound list)", len(keep), keep.core_id.nunique(), missing.core_id.nunique())
    comp["name_upper"] = comp.name.str.upper()
    write(comp, "prism_compounds", sort_by=["name"])
    log.info("PRISM: %d LFC values across %d lines", len(long), long.model_id.nunique())
