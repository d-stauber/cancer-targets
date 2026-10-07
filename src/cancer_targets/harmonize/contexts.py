"""Assemble the contexts table and per-context expression summaries (expr_context_summary)."""
import logging
import numpy as np, pandas as pd
from ..paths import CONFIG
from .util import write, read, exists

log = logging.getLogger("ct.contexts")
EXPR_CUTOFF = 2.0
MIN_GROUP = 3

def _context_map() -> pd.DataFrame:
    cm = pd.read_csv(CONFIG / "context_map.csv")
    return cm

def _apply_map(ctx: pd.DataFrame, cm: pd.DataFrame) -> pd.DataFrame:
    cols = ["tcga_keys", "gtex_v10_tissue", "gtex_toil_site", "hpa_normal_tissue", "hpa_cancer", "disease_names"]
    for c in cols:
        ctx[c] = None
    lin = cm[cm.level == "lineage"].set_index("key")
    pdz = cm[cm.level == "primary_disease"].set_index("key")
    tcg = cm[cm.level == "tcga"].set_index("key")
    for i, r in ctx.iterrows():
        src = None
        if r.context_type in ("tcga", "target") and r.key in tcg.index:
            src = tcg.loc[r.key]
        elif r.context_type in ("cell_line", "lineage", "primary_disease", "subtype", "normal_lines"):
            if isinstance(r.primary_disease, str) and r.primary_disease in pdz.index:
                src = pdz.loc[r.primary_disease]
            elif isinstance(r.lineage, str) and r.lineage in lin.index:
                src = lin.loc[r.lineage]
        if src is not None:
            for c in cols:
                v = src[c]
                ctx.at[i, c] = v if isinstance(v, str) else None
    # normal-tissue contexts map to themselves for matched comparisons
    is_gv = ctx.context_type == "gtex_tissue"
    ctx.loc[is_gv, "gtex_v10_tissue"] = ctx.loc[is_gv, "key"]
    return ctx

def _summ_from_matrix(mat: pd.DataFrame, gene_ids: np.ndarray) -> pd.DataFrame:
    """mat: members x genes -> summary per gene."""
    v = mat.values.astype(np.float32)
    q = np.nanpercentile(v, [25, 50, 75, 90], axis=0)
    return pd.DataFrame({"gene_id": gene_ids, "median": q[1], "mean": np.nanmean(v, axis=0), "q25": q[0], "q75": q[2],
                         "p90": q[3], "max": np.nanmax(v, axis=0), "frac_expr": np.mean(v >= EXPR_CUTOFF, axis=0), "n": v.shape[0]})

def quantile_normalize(summ: pd.DataFrame, ctx: pd.DataFrame) -> np.ndarray:
    """Map every context's median vector onto the pooled GTEx v10 reference distribution (mean of sorted tissue vectors).
    Removes pipeline scale differences (e.g. DepMap protein-coding-only TPM) while preserving within-context ranks."""
    ref_ids = ctx[ctx.context_type == "gtex_tissue"].context_id.values
    ref = summ[summ.context_id.isin(ref_ids)]
    n_genes = ref.groupby("context_id").size().min()
    sorted_vecs = [np.sort(g["median"].values)[:n_genes] for _, g in ref.groupby("context_id")]
    ref_q = np.mean(np.vstack(sorted_vecs), axis=0)
    grid = np.linspace(0, 1, len(ref_q))
    out = np.empty(len(summ), dtype=np.float32)
    pos = summ.groupby("context_id").indices
    for cid, idx in pos.items():
        v = summ["median"].values[idx]
        r = pd.Series(v).rank(method="average").values
        out[idx] = np.interp((r - 1) / max(len(v) - 1, 1), grid, ref_q)
    return out

def build_contexts_and_summary() -> None:
    models = read("depmap_models")
    expr = read("expr_depmap")
    wide = expr.pivot(index="model_id", columns="gene_id", values="value")
    gene_ids = wide.columns.values.astype(np.int32)
    models = models[models.model_id.isin(wide.index)]
    ctx_rows, members, summaries = [], [], []

    def add_ctx(ctype, key, name, n, lineage=None, primary_disease=None, subtype=None, is_normal=False, source="depmap"):
        ctx_rows.append(dict(context_type=ctype, key=key, name=name, n_members=n, lineage=lineage,
                             primary_disease=primary_disease, subtype=subtype, is_normal=is_normal, source=source))
        return len(ctx_rows) - 1

    # 1. cell lines
    for r in models.itertuples():
        add_ctx("cell_line", r.model_id, r.CellLineName, 1, r.OncotreeLineage, r.OncotreePrimaryDisease, r.OncotreeSubtype, bool(r.is_normal))
    cl_ids = {r.model_id: i for i, r in enumerate(models.itertuples())}
    cl_mat = wide.loc[models.model_id]
    v = cl_mat.values.astype(np.float32)
    s = pd.DataFrame({"context_idx": np.repeat(np.arange(len(models)), len(gene_ids)),
                      "gene_id": np.tile(gene_ids, len(models)), "median": v.ravel()})
    s["mean"] = s["median"]; s["q25"] = s["median"]; s["q75"] = s["median"]; s["p90"] = s["median"]; s["max"] = s["median"]
    s["frac_expr"] = (s["median"] >= EXPR_CUTOFF).astype(np.float32); s["n"] = 1
    summaries.append(s.dropna(subset=["median"]))
    for r in models.itertuples():
        members.append((cl_ids[r.model_id], r.model_id))

    # 2. aggregates over cancer lines
    cancer = models[~models.is_normal]
    def add_group(ctype, key, name, sub, **kw):
        if len(sub) < MIN_GROUP: return
        i = add_ctx(ctype, key, name, len(sub), **kw)
        summ = _summ_from_matrix(wide.loc[sub.model_id], gene_ids); summ["context_idx"] = i
        summaries.append(summ)
        members.extend((i, m) for m in sub.model_id)
    for lin, sub in cancer.groupby("OncotreeLineage"):
        add_group("lineage", lin, f"{lin} (all lines)", sub, lineage=lin)
    for (lin, dz), sub in cancer.groupby(["OncotreeLineage", "OncotreePrimaryDisease"]):
        add_group("primary_disease", dz, f"{dz}", sub, lineage=lin, primary_disease=dz)
    for (lin, dz, st), sub in cancer.groupby(["OncotreeLineage", "OncotreePrimaryDisease", "OncotreeSubtype"]):
        add_group("subtype", st, f"{st}", sub, lineage=lin, primary_disease=dz, subtype=st)
    normal = models[models.is_normal]
    for lin, sub in normal.groupby("OncotreeLineage"):
        add_group("normal_lines", lin, f"Non-cancerous lines: {lin}", sub, lineage=lin, is_normal=True)

    # 3. Xena summaries (TCGA / TARGET / TCGA normal / GTEx TOIL)
    if exists("xena_summary"):
        xg = read("xena_groups"); xs = read("xena_summary")
        for r in xg.itertuples():
            i = add_ctx(r.context_type, r.key, r.name, int(r.n_members), lineage=r.site,
                        is_normal=r.context_type in ("tcga_normal", "gtex_toil"), source="xena")
            sub = xs[(xs.context_type == r.context_type) & (xs.key == r.key)].drop(columns=["context_type", "key"]).copy()
            sub["context_idx"] = i
            summaries.append(sub)
        xm = read("xena_members")
        key_to_idx = {(c["context_type"], c["key"]): i for i, c in enumerate(ctx_rows)}
        members.extend((key_to_idx[(t, k)], s) for t, k, s in zip(xm.context_type, xm.key, xm.sample_id) if (t, k) in key_to_idx)

    # 4. GTEx v10 medians and HPA RNA consensus (single value per tissue)
    for name, ctype, label in (("expr_gtex_v10", "gtex_tissue", "GTEx v10: "), ("expr_hpa_rna_tissue", "hpa_rna_tissue", "HPA RNA: ")):
        if not exists(name): continue
        g = read(name)
        for tissue, sub in g.groupby("tissue"):
            i = add_ctx(ctype, tissue, label + tissue.replace("_", " "), 0, is_normal=True, source=name.split("_", 1)[1])
            s = sub[["gene_id", "value"]].rename(columns={"value": "median"}).copy()
            for c in ("mean", "q25", "q75", "p90", "max"): s[c] = s["median"]
            s["frac_expr"] = (s["median"] >= EXPR_CUTOFF).astype(np.float32); s["n"] = 0; s["context_idx"] = i
            summaries.append(s)

    ctx = pd.DataFrame(ctx_rows)
    ctx.insert(0, "context_id", np.arange(len(ctx), dtype=np.int32))
    ctx = _apply_map(ctx, _context_map())
    write(ctx, "contexts")
    mem = pd.DataFrame(members, columns=["context_id", "sample_id"]); mem["context_id"] = mem.context_id.astype(np.int32)
    write(mem, "context_members", sort_by=["context_id"])
    summ = pd.concat(summaries, ignore_index=True)
    summ = summ.rename(columns={"context_idx": "context_id"})
    summ["context_id"] = summ.context_id.astype(np.int32); summ["gene_id"] = summ.gene_id.astype(np.int32)
    for c in ("median", "mean", "q25", "q75", "p90", "max", "frac_expr"):
        summ[c] = summ[c].astype(np.float32)
    summ["n"] = summ.n.astype(np.int32)
    summ["pct_rank"] = summ.groupby("context_id")["median"].rank(pct=True).astype(np.float32)
    summ["qn"] = quantile_normalize(summ, ctx)
    summ = summ[["context_id", "gene_id", "median", "qn", "mean", "q25", "q75", "p90", "max", "frac_expr", "n", "pct_rank"]]
    write(summ, "expr_context_summary", sort_by=["context_id", "gene_id"])
    log.info("contexts: %d (%s)", len(ctx), ctx.context_type.value_counts().to_dict())
