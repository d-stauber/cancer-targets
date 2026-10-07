"""UCSC Xena TOIL recompute (TCGA + TARGET + GTEx): stream the RSEM TPM matrix into per-context summaries."""
import gzip, logging
import numpy as np, pandas as pd
from ..paths import RAW, INTERIM
from .util import write, log_unmapped
from .genes import get_mapper

log = logging.getLogger("ct.xena")
X = RAW / "xena"
EXPR_CUTOFF = 2.0

TUMOR_TYPES = {"Primary Tumor", "Primary Solid Tumor", "Primary Blood Derived Cancer - Peripheral Blood",
               "Primary Blood Derived Cancer - Bone Marrow", "Additional - New Primary"}

def sample_groups() -> tuple[pd.DataFrame, pd.DataFrame]:
    """Return (groups, members): groups has context_type/key/name/site; members maps sample->group key."""
    p = pd.read_csv(X / "TcgaTargetGTEX_phenotype.txt.gz", sep="\t", encoding="latin-1")
    p = p.rename(columns={"primary disease or tissue": "disease", "_primary_site": "site",
                          "_sample_type": "stype", "_study": "study"})
    rows = []
    tcga = p[(p.study == "TCGA") & (p.stype.isin(TUMOR_TYPES) | ((p.disease == "Skin Cutaneous Melanoma") & (p.stype == "Metastatic")))]
    for d, g in tcga.groupby("disease"):
        rows.append(("tcga", d, d, g.site.iloc[0], g["sample"].tolist()))
    target = p[(p.study == "TARGET") & p.stype.isin(TUMOR_TYPES)]
    for d, g in target.groupby("disease"):
        rows.append(("target", d, f"TARGET {d}", g.site.iloc[0], g["sample"].tolist()))
    tn = p[(p.study == "TCGA") & (p.stype == "Solid Tissue Normal")]
    for s, g in tn.groupby("site"):
        rows.append(("tcga_normal", s, f"TCGA normal: {s}", s, g["sample"].tolist()))
    gt = p[(p.study == "GTEX") & (p.stype == "Normal Tissue")]
    for s, g in gt.groupby("site"):
        rows.append(("gtex_toil", s, f"GTEx (TOIL): {s}", s, g["sample"].tolist()))
    groups = pd.DataFrame([(t, k, n, s, len(m)) for t, k, n, s, m in rows],
                          columns=["context_type", "key", "name", "site", "n_members"])
    groups = groups[groups.n_members >= 5].reset_index(drop=True)
    members = pd.DataFrame([(t, k, m) for t, k, n, s, ms in rows for m in ms], columns=["context_type", "key", "sample_id"])
    members = members.merge(groups[["context_type", "key"]])
    return groups, members

def _stats(block: np.ndarray) -> dict:
    """block: genes x samples (log2 TPM+1)."""
    q = np.nanpercentile(block, [25, 50, 75, 90], axis=1)
    return {"q25": q[0], "median": q[1], "q75": q[2], "p90": q[3], "mean": np.nanmean(block, axis=1),
            "max": np.nanmax(block, axis=1), "frac_expr": np.mean(block >= EXPR_CUTOFF, axis=1)}

def build_xena(chunksize: int = 800) -> None:
    gm = get_mapper()
    groups, members = sample_groups()
    path = X / "TcgaTargetGtex_rsem_gene_tpm.gz"
    with gzip.open(path, "rt") as f:
        header = f.readline().rstrip("\n").split("\t")
    samples = header[1:]
    pos = {s: i for i, s in enumerate(samples)}
    members = members[members.sample_id.isin(pos)]
    groups = groups.merge(members.groupby(["context_type", "key"]).size().rename("n_present").reset_index())
    groups["n_members"] = groups.n_present
    idx = {(t, k): np.array(sorted(pos[s] for s in g.sample_id)) for (t, k), g in members.groupby(["context_type", "key"])}
    log.info("xena: %d samples, %d groups", len(samples), len(groups))
    parts, unmapped = [], []
    dtypes = {s_: np.float32 for s_ in samples}; dtypes[header[0]] = str
    reader = pd.read_csv(path, sep="\t", chunksize=chunksize, index_col=0, dtype=dtypes, na_values=["NA"], engine="c")
    for ci, chunk in enumerate(reader):
        gid = pd.Series(chunk.index).map(gm.ensembl)
        keep = gid.notna().values
        unmapped.extend(chunk.index[~keep].tolist())
        if not keep.any():
            continue
        chunk = chunk.loc[keep]
        gids = gid[keep].astype(np.int32).values
        vals = chunk.values  # log2(tpm+0.001)
        tpm = np.clip(np.power(2.0, vals.astype(np.float64)) - 0.001, 0, None)
        x = np.log2(tpm + 1).astype(np.float32)
        for (t, k), ii in idx.items():
            st = _stats(x[:, ii])
            df = pd.DataFrame(st)
            df["gene_id"] = gids; df["context_type"] = t; df["key"] = k; df["n"] = len(ii)
            parts.append(df)
        if ci % 10 == 0:
            log.info("xena chunk %d (%d genes so far)", ci, sum(len(p) for p in parts) // max(len(idx), 1))
    log_unmapped("xena", pd.Series(unmapped).str.replace(r"\.\d+$", "", regex=True).unique()[:50000])
    out = pd.concat(parts, ignore_index=True)
    for c in ("median", "mean", "q25", "q75", "p90", "max", "frac_expr"):
        out[c] = out[c].astype(np.float32)
    # duplicate gene_ids from multiple Ensembl ids -> keep highest median
    out = out.sort_values(["context_type", "key", "gene_id", "median"], ascending=[True, True, True, False])
    out = out.drop_duplicates(["context_type", "key", "gene_id"])
    write(out, "xena_summary", sort_by=["context_type", "key", "gene_id"])
    write(groups, "xena_groups")
    write(members, "xena_members")
    log.info("xena: %d summary rows, %d genes", len(out), out.gene_id.nunique())
