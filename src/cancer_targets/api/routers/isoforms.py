"""Isoform / alternative-exon views: transcript structure, isoform composition by context, and exon inclusion
(tumor vs adjacent normal vs GTEx per tissue) for genes with per-sample isoform data."""
from typing import Optional
import io
import numpy as np, pandas as pd
from fastapi import APIRouter, HTTPException
from fastapi.responses import StreamingResponse
from ..db import q, records
from ...harmonize.isoforms import detail_config

router = APIRouter(tags=["isoforms"])
XENA_TYPES = "tcga,target,tcga_normal,gtex_toil"

def _has(v: str) -> bool:
    return not q("select table_name from information_schema.tables where table_name = ?", [v]).empty

def _gene(symbol: str) -> tuple[int, str]:
    g = q("""select gene_id, symbol from gene_map where upper(symbol) = upper(?)
             union all select gene_id, symbol from gene_map where list_contains(string_split(coalesce(alias_symbols,''),'|'), ?) limit 1""", [symbol, symbol])
    if g.empty:
        raise HTTPException(404, f"gene not found: {symbol}")
    return int(g.gene_id[0]), g.symbol[0]

def _bins_for(gid: int, exons: pd.DataFrame, strand: str) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Stored labelled bins for detail genes; generic union-of-exons bins otherwise."""
    if _has("isoform_exon_bins"):
        b = q("select bin, label, start, \"end\", is_variable from isoform_exon_bins where gene_id = ? order by bin", [gid])
        if not b.empty:
            m = q("select transcript_id, bin from isoform_bin_member where gene_id = ?", [gid])
            return b, m
    e = exons.sort_values("start"); bins, cur = [], None
    for s, en in zip(e.start, e.end):
        if cur and s <= cur[1]: cur[1] = max(cur[1], en)
        else: cur = [s, en]; bins.append(cur)
    bins = sorted(bins, key=lambda x: x[0], reverse=(strand == "-"))
    b = pd.DataFrame(bins, columns=["start", "end"]); b["bin"] = np.arange(1, len(b) + 1); b["label"] = "E" + b.bin.astype(str)
    mem = [(t, int(r.bin)) for t, g in exons.groupby("transcript_id") for r in b.itertuples() if ((g.start <= r.end) & (g.end >= r.start)).any()]
    m = pd.DataFrame(mem, columns=["transcript_id", "bin"])
    n = m.transcript_id.nunique(); cnt = m.groupby("bin").size()
    b["is_variable"] = b.bin.map(cnt).fillna(0) < n
    return b, m

def _variant_summary(labels: list[str], variable: set[str]) -> str:
    v = [l for l in labels if l in variable]
    if not variable: return ""
    if not v: return "no variable exons"
    order = [l for l in sorted(variable, key=lambda s: (len(s), s))]
    return "–".join([v[0], v[-1]]) if len(v) > 2 and all(x in v for x in order[order.index(v[0]):order.index(v[-1]) + 1]) else ", ".join(v)

@router.get("/isoforms/genes")
def detail_genes():
    cfg = detail_config()
    return [{"symbol": s, "note": (c or {}).get("note"), "default_exon": (c or {}).get("default_exon"), "variable": (c or {}).get("variable")} for s, c in cfg.items()]

@router.get("/genes/{symbol}/isoforms")
def structure(symbol: str, max_transcripts: int = 25):
    if not _has("isoform_transcripts"):
        raise HTTPException(404, "isoform data not built (ct build --step isoforms)")
    gid, sym = _gene(symbol)
    tr = q("select * from isoform_transcripts where gene_id = ?", [gid])
    if tr.empty:
        raise HTTPException(404, f"no transcripts for {sym}")
    ex = q("select e.* from isoform_exons e join isoform_transcripts t using(transcript_id) where t.gene_id = ?", [gid])
    strand = tr.strand.iloc[0]
    bins, mem = _bins_for(gid, ex, strand)
    # order transcripts by overall expression (mean TPM over tumor + normal contexts), then annotation quality
    if _has("isoform_context_summary"):
        e = q("select transcript_id, avg(mean_tpm) as mean_tpm, max(median) as max_median from isoform_context_summary where gene_id = ? group by 1", [gid])
        tr = tr.merge(e, how="left", on="transcript_id")
    else:
        tr["mean_tpm"] = np.nan; tr["max_median"] = np.nan
    tr = tr.sort_values(["mean_tpm", "is_ccds", "is_basic", "n_exons"], ascending=False, na_position="last").head(max_transcripts)
    cfg = (detail_config().get(sym) or {})
    variable = set(cfg.get("variable") or [])
    lab = dict(zip(bins.bin, bins.label))
    tmap = mem.groupby("transcript_id").bin.apply(lambda s: sorted(s)).to_dict()
    tr["bins"] = tr.transcript_id.map(lambda t: tmap.get(t, []))
    tr["exon_labels"] = tr.bins.map(lambda bs: [lab[b] for b in bs])
    vbins = bins[bins.label.isin(variable)].bin if variable else bins[bins.is_variable].bin
    vlo, vhi = (int(vbins.min()), int(vbins.max())) if len(vbins) else (None, None)
    def summary(bs, ls):
        s = _variant_summary(ls, variable)
        # a transcript that lacks exons on both sides of the variable region cannot tell us whether it skips it
        if vlo is not None and s == "no variable exons" and not (any(b < vlo for b in bs) and any(b > vhi for b in bs)):
            return "partial (does not span variable region)"
        return s
    tr["variant_summary"] = [summary(bs, ls) for bs, ls in zip(tr.bins, tr.exon_labels)]
    out = records(tr.drop(columns=["bins", "exon_labels"]))
    for o, bs, ls in zip(out, tr.bins, tr.exon_labels):
        o["bins"] = [int(b) for b in bs]; o["exon_labels"] = ls
    has_detail = _has("isoform_detail") and sym in detail_config()
    n_lines = int(q("select count(distinct d.sample_id) as n from isoform_detail d join isoform_transcripts t using(transcript_id) where t.gene_id = ? and d.sample_id like 'ACH-%'", [gid]).n[0]) if has_detail else 0
    return {"gene": sym, "gene_id": gid, "strand": strand, "chrom": tr.chrom.iloc[0], "n_transcripts_total": int(q("select count(*) as n from isoform_transcripts where gene_id = ?", [gid]).n[0]),
            "bins": records(bins), "transcripts": out, "detail": has_detail, "n_cell_lines": n_lines, "note": cfg.get("note"),
            "default_exon": cfg.get("default_exon") or (bins[bins.is_variable].label.iloc[0] if bins.is_variable.any() else None),
            "variable": sorted(variable, key=lambda s: (len(s), s)) if variable else bins[bins.is_variable].label.tolist()}

@router.get("/genes/{symbol}/isoforms/composition")
def composition(symbol: str, types: str = XENA_TYPES):
    if not _has("isoform_context_summary"):
        raise HTTPException(404, "isoform expression not built")
    gid, sym = _gene(symbol)
    d = q("""select c.context_id, c.context_type, c.name, c.key, c.lineage, c.n_members, s.transcript_id, t.transcript_name,
                    s.median, s.q25, s.q75, s.mean_tpm, s.pooled_frac, s.frac_expr
             from isoform_context_summary s join all_contexts c using(context_id) join isoform_transcripts t using(transcript_id)
             where s.gene_id = ? and c.context_type in (select unnest(string_split(?, ',')))""", [gid, types])
    return {"gene": sym, "rows": records(d)}

def _feature_values(gid: int, sym: str, feature: str) -> pd.DataFrame:
    """Per sample: gene total TPM and feature TPM (transcripts containing an exon bin, or one transcript)."""
    kind, _, val = feature.partition(":")
    if kind == "exon":
        b = q("select bin from isoform_exon_bins where gene_id = ? and label = ?", [gid, val])
        if b.empty:
            raise HTTPException(400, f"unknown exon '{val}' for {sym}")
        feat_sql = "select transcript_id from isoform_bin_member where gene_id = ? and bin = ?"; fp = [gid, int(b.bin[0])]
    elif kind == "transcript":
        feat_sql = "select ? as transcript_id"; fp = [val.split(".")[0]]
    else:
        raise HTTPException(400, "feature must be exon:<label> or transcript:<ENST id>")
    return q(f"""select d.sample_id, sum(d.tpm) as total_tpm,
                        sum(case when d.transcript_id in ({feat_sql}) then d.tpm else 0 end) as feat_tpm
                 from isoform_detail d join isoform_transcripts t using(transcript_id)
                 where t.gene_id = ? group by 1""", fp + [gid])

def _auroc(a: np.ndarray, b: np.ndarray) -> float | None:
    if len(a) < 3 or len(b) < 3: return None
    r = pd.Series(np.concatenate([a, b])).rank().values
    return float((r[:len(a)].sum() - len(a) * (len(a) + 1) / 2) / (len(a) * len(b)))

@router.get("/genes/{symbol}/isoforms/inclusion")
def inclusion(symbol: str, feature: Optional[str] = None, metric: str = "psi", min_gene_tpm: float = 5.0,
              types: str = XENA_TYPES, format: str = "json"):
    """metric=psi: fraction of the gene's TPM from transcripts containing the feature (samples with gene TPM >= min_gene_tpm).
    metric=tpm: log2(TPM+1) of feature-containing transcripts (absolute level, relevant for targeting)."""
    gid, sym = _gene(symbol)
    if not (_has("isoform_detail") and sym in detail_config()):
        raise HTTPException(404, f"{sym} has no per-sample isoform data; add it to config/isoform_genes.yaml and rebuild")
    cfg = detail_config().get(sym) or {}
    feature = feature or f"exon:{cfg.get('default_exon') or 'E1'}"
    v = _feature_values(gid, sym, feature)
    mem = q("""select m.context_id, m.sample_id, c.context_type, c.name, c.key, c.lineage from context_members m join all_contexts c using(context_id)
               where c.context_type in (select unnest(string_split(?, ',')))""", [types])
    d = mem.merge(v, on="sample_id")
    if metric == "psi":
        d = d[d.total_tpm >= min_gene_tpm].assign(value=lambda x: x.feat_tpm / x.total_tpm)
    elif metric == "tpm":
        d = d.assign(value=np.log2(d.feat_tpm + 1))
    else:
        raise HTTPException(400, "metric must be psi or tpm")
    g = d.groupby(["context_id", "context_type", "name", "key", "lineage"], dropna=False).value
    s = g.describe(percentiles=[0.05, 0.25, 0.5, 0.75, 0.95]).reset_index()
    s = s.rename(columns={"5%": "p05", "25%": "q25", "50%": "median", "75%": "q75", "95%": "p95", "count": "n"})
    s["n_total"] = s.context_id.map(mem.groupby("context_id").size()).fillna(0).astype(int)
    # tumor vs normal per tissue site (Xena _primary_site): TCGA/TARGET type vs TCGA adjacent normal and GTEx of the same site
    vals = {cid: grp.value.values for cid, grp in d.groupby("context_id")}
    site_norm = {k: c for c, t, k in zip(s.context_id, s.context_type, s.key) if t == "tcga_normal"}
    site_gtex = {k: c for c, t, k in zip(s.context_id, s.context_type, s.key) if t == "gtex_toil"}
    med = dict(zip(s.context_id, s["median"]))
    comp = []
    for r in s[s.context_type.isin(["tcga", "target"])].itertuples():
        site = r.lineage; cn, cg = site_norm.get(site), site_gtex.get(site)
        comp.append({"context_id": int(r.context_id), "tumor": r.name, "site": site, "n_tumor": int(r.n), "tumor_median": float(r.median),
                     "adj_normal_median": med.get(cn), "n_adj_normal": int(len(vals.get(cn, []))) if cn else 0,
                     "gtex_median": med.get(cg), "n_gtex": int(len(vals.get(cg, []))) if cg else 0,
                     "delta_vs_gtex": float(r.median - med[cg]) if cg in med else None,
                     "delta_vs_adj_normal": float(r.median - med[cn]) if cn in med else None,
                     "auroc_vs_gtex": _auroc(vals[r.context_id], vals[cg]) if cg in vals else None,
                     "auroc_vs_adj_normal": _auroc(vals[r.context_id], vals[cn]) if cn in vals else None})
    comp = pd.DataFrame(comp)
    if format == "csv":
        buf = io.StringIO(); comp.to_csv(buf, index=False)
        return StreamingResponse(iter([buf.getvalue()]), media_type="text/csv", headers={"Content-Disposition": f"attachment; filename={sym}_{feature.replace(':','_')}_{metric}.csv"})
    return {"gene": sym, "feature": feature, "metric": metric, "min_gene_tpm": min_gene_tpm, "contexts": records(s), "comparison": records(comp)}
