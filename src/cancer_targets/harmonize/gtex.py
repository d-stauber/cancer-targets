"""GTEx v10 median TPM per tissue -> long log2(TPM+1)."""
import logging
import numpy as np, pandas as pd
from ..paths import RAW
from .util import write, log_unmapped
from .genes import get_mapper

log = logging.getLogger("ct.gtex")

def build_gtex() -> pd.DataFrame:
    gm = get_mapper()
    path = next((RAW / "gtex").glob("*gene_median_tpm.gct.gz"))
    df = pd.read_csv(path, sep="\t", skiprows=2)
    df["gene_id"] = df["Name"].map(gm.ensembl).astype("Int32")
    miss = df.gene_id.isna()
    # fallback on symbol for unversioned mismatches
    df.loc[miss, "gene_id"] = df.loc[miss, "Description"].map(gm.symbol).astype("Int32")
    log_unmapped("gtex", df.loc[df.gene_id.isna(), "Name"])
    df = df.dropna(subset=["gene_id"])
    tissues = [c for c in df.columns if c not in ("Name", "Description", "gene_id")]
    long = df.melt(id_vars=["gene_id"], value_vars=tissues, var_name="tissue", value_name="tpm")
    long["value"] = np.log2(long.tpm.astype(np.float32) + 1).astype(np.float32)
    long = long.groupby(["gene_id", "tissue"], as_index=False)["value"].max()
    long["gene_id"] = long.gene_id.astype(np.int32)
    write(long, "expr_gtex_v10", sort_by=["tissue", "gene_id"])
    log.info("GTEx v10: %d tissues, %d genes", long.tissue.nunique(), long.gene_id.nunique())
    return long
