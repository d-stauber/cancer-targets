"""Human Protein Atlas: normal IHC, cancer IHC, subcellular location, RNA tissue consensus."""
import logging, zipfile, io
import numpy as np, pandas as pd
from ..paths import RAW
from .util import write, col, log_unmapped
from .genes import get_mapper

log = logging.getLogger("ct.hpa")
H = RAW / "hpa"
LEVEL = {"Not detected": 0, "Low": 1, "Medium": 2, "High": 3}

def _read_zip_tsv(name: str) -> pd.DataFrame | None:
    p = H / name
    if not p.exists():
        log.warning("HPA file missing: %s", name); return None
    with zipfile.ZipFile(p) as z:
        inner = [n for n in z.namelist() if n.endswith(".tsv")][0]
        return pd.read_csv(io.BytesIO(z.read(inner)), sep="\t", low_memory=False)

def _map(df: pd.DataFrame, source: str) -> pd.DataFrame:
    gm = get_mapper()
    g = col(df, "Gene")
    df["gene_id"] = df[g].map(gm.ensembl).astype("Int32")
    miss = df.gene_id.isna()
    if miss.any():
        gn = col(df, "Gene name")
        df.loc[miss, "gene_id"] = df.loc[miss, gn].map(gm.symbol).astype("Int32")
    log_unmapped(source, df.loc[df.gene_id.isna(), g].unique())
    return df.dropna(subset=["gene_id"]).assign(gene_id=lambda d: d.gene_id.astype(np.int32))

def build_normal_ihc():
    df = _read_zip_tsv("normal_ihc_data.tsv.zip")
    if df is None: return
    df = _map(df, "hpa_normal")
    t, l, r = col(df, "Tissue"), col(df, "Level"), col(df, "Reliability")
    df = df[df[r].isin(["Enhanced", "Supported", "Approved"])]
    df["level_num"] = df[l].map(LEVEL).astype("Int8")
    df = df.dropna(subset=["level_num"])
    out = df.groupby(["gene_id", t], as_index=False)["level_num"].max().rename(columns={t: "tissue"})
    out["level_num"] = out.level_num.astype(np.int8)
    write(out, "hpa_normal_ihc", sort_by=["gene_id", "tissue"])

def build_cancer_ihc():
    df = _read_zip_tsv("cancer_ihc_data.tsv.zip")
    if df is None: return
    df = _map(df, "hpa_cancer")
    c = col(df, "Cancer", "Tumor")
    if "High" in df.columns:  # wide format: Gene, Cancer, High, Medium, Low, Not detected
        out = df.groupby(["gene_id", c], as_index=False)[["High", "Medium", "Low", "Not detected"]].sum()
    else:  # long format with Level column: count patients per level
        l = col(df, "Level")
        out = df.pivot_table(index=["gene_id", c], columns=l, values=df.columns[0], aggfunc="count", fill_value=0).reset_index()
        for k in ("High", "Medium", "Low", "Not detected"):
            if k not in out.columns: out[k] = 0
    out = out.rename(columns={c: "cancer", "Not detected": "not_detected", "High": "n_high", "Medium": "n_medium", "Low": "n_low"})
    out["n_patients"] = out[["n_high", "n_medium", "n_low", "not_detected"]].sum(axis=1)
    out["cancer"] = out.cancer.str.lower()
    write(out, "hpa_cancer_ihc", sort_by=["gene_id", "cancer"])

def build_subcellular():
    df = _read_zip_tsv("subcellular_location.tsv.zip")
    if df is None: return
    df = _map(df, "hpa_subcell")
    out = df[["gene_id", col(df, "Reliability"), col(df, "Main location"), col(df, "Additional location"),
              col(df, "Extracellular location"), col(df, "Enhanced"), col(df, "Supported"), col(df, "Approved")]].copy()
    out.columns = ["gene_id", "reliability", "main_location", "additional_location", "extracellular_location",
                   "enhanced", "supported", "approved"]
    out = out.drop_duplicates("gene_id")
    write(out, "hpa_subcellular", sort_by=["gene_id"])

def build_rna_tissue():
    df = _read_zip_tsv("rna_tissue_consensus.tsv.zip")
    if df is None: return
    df = _map(df, "hpa_rna")
    t, v = col(df, "Tissue"), col(df, "nTPM")
    out = df.groupby(["gene_id", t], as_index=False)[v].max().rename(columns={t: "tissue", v: "ntpm"})
    out["value"] = np.log2(out.ntpm.astype(np.float32) + 1).astype(np.float32)
    write(out[["gene_id", "tissue", "value"]], "expr_hpa_rna_tissue", sort_by=["tissue", "gene_id"])

def build_all():
    build_normal_ihc(); build_cancer_ihc(); build_subcellular(); build_rna_tissue()
