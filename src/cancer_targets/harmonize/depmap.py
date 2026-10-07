"""DepMap: models, expression (log2 TPM+1), CRISPR gene effect."""
import logging
import numpy as np, pandas as pd
from ..paths import RAW
from .util import write, log_unmapped
from .genes import get_mapper

log = logging.getLogger("ct.depmap")
D = RAW / "depmap"

def _wide_to_long(path, value_name: str, source: str) -> pd.DataFrame:
    gm = get_mapper()
    df = pd.read_csv(path, index_col=0)
    if df.index.name is None or df.index.name == "Unnamed: 0":
        df.index.name = "model_id"
    # some releases have a ProfileID/ModelID column; keep ModelID rows only
    if "ModelID" in df.columns:
        df = df.set_index("ModelID")
    df = df.loc[df.index.astype(str).str.startswith("ACH-")]
    ids = pd.Series(df.columns).map(gm.depmap_column)
    unmapped = [c for c, i in zip(df.columns, ids) if pd.isna(i)]
    log_unmapped(source, unmapped)
    rate = 1 - len(unmapped) / len(df.columns)
    log.info("%s: %d models x %d genes, mapping rate %.3f", source, df.shape[0], df.shape[1], rate)
    assert rate >= 0.95, f"{source} mapping rate too low: {rate}"
    keep = ids.notna().values
    df = df.loc[:, keep]
    df.columns = ids[keep].astype(int).values
    # collapse duplicate gene_ids (rare): take max
    if df.columns.duplicated().any():
        df = df.T.groupby(level=0).max().T
    long = df.astype(np.float32).stack().reset_index()
    long.columns = ["model_id", "gene_id", value_name]
    long["gene_id"] = long.gene_id.astype(np.int32)
    long = long.dropna(subset=[value_name])
    return long

def build_models() -> pd.DataFrame:
    m = pd.read_csv(D / "Model.csv")
    keep = ["ModelID", "CellLineName", "StrippedCellLineName", "OncotreeLineage", "OncotreePrimaryDisease",
            "OncotreeSubtype", "OncotreeCode", "DepmapModelType", "PrimaryOrMetastasis", "Sex", "Age",
            "SampleCollectionSite", "GrowthPattern", "CCLEName", "RRID"]
    keep = [k for k in keep if k in m.columns]
    m = m[keep].rename(columns={"ModelID": "model_id"})
    m["is_normal"] = m.OncotreePrimaryDisease.eq("Non-Cancerous")
    write(m, "depmap_models")
    return m

def build_expression() -> pd.DataFrame:
    long = _wide_to_long(D / "OmicsExpressionProteinCodingGenesTPMLogp1.csv", "value", "depmap_expr")
    write(long, "expr_depmap", sort_by=["gene_id", "model_id"])
    return long

def build_crispr() -> None:
    p = D / "CRISPRGeneEffect.csv"
    if not p.exists():
        log.warning("CRISPRGeneEffect.csv missing; skipping dependency"); return
    long = _wide_to_long(p, "effect", "depmap_crispr")
    write(long, "crispr_effect", sort_by=["gene_id", "model_id"])
    ce = D / "CRISPRInferredCommonEssentials.csv"
    if ce.exists():
        gm = get_mapper()
        c = pd.read_csv(ce)
        col = c.columns[0]
        ids = c[col].map(gm.depmap_column).dropna().astype(np.int32).unique()
        write(pd.DataFrame({"gene_id": ids, "is_common_essential": True}), "common_essentials")
