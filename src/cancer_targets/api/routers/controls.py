"""Custom control/context upload: CSV with gene column (symbol/Ensembl) + expression column (TPM or log2(TPM+1))."""
import io, logging
import numpy as np, pandas as pd
from fastapi import APIRouter, UploadFile, File, Form, HTTPException
from ..db import q, records, refresh_custom, CUSTOM
from ...harmonize.genes import GeneMapper
from ...harmonize.util import read

router = APIRouter(tags=["controls"])
log = logging.getLogger("ct.api.controls")

@router.get("/controls")
def list_controls():
    p = CUSTOM / "custom_contexts.parquet"
    return records(pd.read_parquet(p)) if p.exists() else []

MAX_BYTES = 50 * 1024 * 1024

@router.post("/controls")
async def upload(file: UploadFile = File(...), name: str = Form(...), units: str = Form("tpm"), gene_col: str = Form(""), value_col: str = Form("")):
    name = name.strip()[:80]
    if not name:
        raise HTTPException(400, "name is required")
    data = await file.read(MAX_BYTES + 1)
    if len(data) > MAX_BYTES:
        raise HTTPException(413, f"file larger than {MAX_BYTES // (1024 * 1024)} MB")
    raw = data.decode("utf-8", errors="replace")
    sep = "\t" if raw.count("\t") > raw.count(",") else ","
    df = pd.read_csv(io.StringIO(raw), sep=sep)
    if df.shape[1] < 2:
        raise HTTPException(400, "need at least a gene column and a value column")
    gc = gene_col or df.columns[0]
    vc = value_col or next((c for c in df.columns[1:] if pd.api.types.is_numeric_dtype(df[c])), df.columns[1])
    gm = GeneMapper(read("gene_map"))
    ids = df[gc].astype(str)
    gid = ids.map(gm.ensembl).astype("Int32")
    m = gid.isna(); gid[m] = ids[m].map(gm.symbol).astype("Int32")
    vals = pd.to_numeric(df[vc], errors="coerce")
    d = pd.DataFrame({"gene_id": gid, "v": vals}).dropna()
    if units.lower() == "tpm":
        d["median"] = np.log2(d.v.clip(lower=0) + 1)
    elif units.lower() in ("log2tpm1", "log2(tpm+1)"):
        d["median"] = d.v
    else:
        raise HTTPException(400, "units must be tpm or log2tpm1")
    d = d.groupby("gene_id", as_index=False)["median"].max()
    if len(d) < 1000:
        raise HTTPException(400, f"only {len(d)} genes mapped; check the gene column ({gc})")
    cc, cs = CUSTOM / "custom_contexts.parquet", CUSTOM / "custom_summary.parquet"
    existing = pd.read_parquet(cc) if cc.exists() else None
    base = int(q("select max(context_id) as m from contexts").m[0])
    cid = (int(existing.context_id.max()) + 1) if existing is not None and len(existing) else base + 1000
    ctx = pd.DataFrame([{"context_id": np.int32(cid), "context_type": "custom", "key": f"custom:{cid}", "name": name, "n_members": 1,
                         "lineage": None, "primary_disease": None, "subtype": None, "is_normal": True, "source": "upload",
                         "tcga_keys": None, "gtex_v10_tissue": None, "gtex_toil_site": None, "hpa_normal_tissue": None, "hpa_cancer": None, "disease_names": None}])
    summ = pd.DataFrame({"context_id": np.int32(cid), "gene_id": d.gene_id.astype(np.int32), "median": d["median"].astype(np.float32)})
    for c in ("mean", "q25", "q75", "p90", "max"): summ[c] = summ["median"]
    summ["frac_expr"] = (summ["median"] >= 2).astype(np.float32); summ["n"] = np.int32(1)
    summ["pct_rank"] = summ["median"].rank(pct=True).astype(np.float32)
    ref = q("select qn from all_summary where context_id = (select min(context_id) from all_contexts where context_type='gtex_tissue') order by qn").qn.values
    r = summ["median"].rank(method="average").values
    summ["qn"] = np.interp((r - 1) / max(len(r) - 1, 1), np.linspace(0, 1, len(ref)), ref).astype(np.float32)
    pd.concat([existing, ctx]).to_parquet(cc, index=False) if existing is not None else ctx.to_parquet(cc, index=False)
    prev = pd.read_parquet(cs) if cs.exists() else None
    pd.concat([prev, summ]).to_parquet(cs, index=False) if prev is not None else summ.to_parquet(cs, index=False)
    # score the upload as a target context too (expression vs TOIL GTEx reference; no matched normal / members)
    try:
        n_scored = _score_custom(ctx, summ)
    except Exception as e:  # scoring failure must not lose the upload
        log.exception("custom scoring failed: %s", e); n_scored = 0
    refresh_custom()
    return {"context_id": cid, "name": name, "n_genes": int(len(summ)), "n_scored": n_scored, "gene_col": gc, "value_col": vc}

def _score_custom(ctx: pd.DataFrame, summ: pd.DataFrame) -> int:
    from ...scoring.components import Scorer, add_ranks
    from ...scoring.rank import OUT_COLS
    sc = Scorer(light=True, extra_contexts=ctx)
    cid = int(ctx.context_id.iloc[0])
    d = sc.score_contexts([cid], summ[["context_id", "gene_id", "median", "qn", "frac_expr", "n"]])
    d = add_ranks(d, sc.profiles)
    cols = [c for c in OUT_COLS if c in d.columns] + [c for c in d.columns if c.startswith(("score_", "rank_", "pct_"))]
    d = d[cols]
    csc = CUSTOM / "custom_scores.parquet"
    prev = pd.read_parquet(csc) if csc.exists() else None
    (pd.concat([prev, d]) if prev is not None else d).to_parquet(csc, index=False)
    return int(len(d))
