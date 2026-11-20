"""Transcript-level expression: UCSC Xena TOIL RSEM isoform TPM (TCGA / TARGET / GTEx, GENCODE v23) and, if present,
DepMap transcript TPM. Produces
  isoform_transcripts / isoform_exons      GENCODE v23 structure for transcripts of protein-coding genes
  isoform_exon_bins / isoform_bin_member   exon bins (union of overlapping exons) with labels, transcript membership
  isoform_context_summary                  per context x transcript: log2(TPM+1) median/IQR, mean TPM, pooled fraction
  isoform_detail                           per sample x transcript TPM for genes in config/isoform_genes.yaml
"""
import gzip, logging, re
import numpy as np, pandas as pd, yaml
from ..paths import RAW, CONFIG
from .util import write, read, exists
from .genes import get_mapper
from .xena import sample_groups

log = logging.getLogger("ct.isoforms")
I = RAW / "isoforms"
EXPR_CUTOFF = 1.0  # log2(TPM+1) >= 1 counts as expressed for isoforms

def detail_config() -> dict:
    p = CONFIG / "isoform_genes.yaml"
    return (yaml.safe_load(p.read_text()) or {}).get("genes", {}) if p.exists() else {}

def _attr(a: str, k: str):
    m = re.search(k + r' "?([^";]+)"?;', a)
    return m.group(1) if m else None

def build_structure() -> tuple[pd.DataFrame, pd.DataFrame]:
    gm = get_mapper()
    rows_t, rows_e = [], []
    with gzip.open(I / "gencode.v23.annotation.gtf.gz", "rt") as f:
        for line in f:
            if line.startswith("#"):
                continue
            p = line.rstrip("\n").split("\t")
            if p[2] not in ("transcript", "exon"):
                continue
            a = p[8]
            gid = gm.ensembl(_attr(a, "gene_id"))
            if gid is None:
                continue
            tid = _attr(a, "transcript_id").split(".")[0]
            if p[2] == "transcript":
                tags = re.findall(r'tag "([^"]+)"', a)
                rows_t.append((tid, int(gid), _attr(a, "gene_name"), _attr(a, "transcript_name"), _attr(a, "transcript_type"),
                               p[0], int(p[3]), int(p[4]), p[6], "basic" in tags, "CCDS" in tags, int((re.search(r"level (\d+)", a) or [None, 3])[1])))
            else:
                rows_e.append((tid, int(_attr(a, "exon_number")), int(p[3]), int(p[4])))
    tr = pd.DataFrame(rows_t, columns=["transcript_id", "gene_id", "gtf_gene_name", "transcript_name", "transcript_type",
                                       "chrom", "start", "end", "strand", "is_basic", "is_ccds", "level"])
    ex = pd.DataFrame(rows_e, columns=["transcript_id", "exon_number", "start", "end"])
    ex = ex[ex.transcript_id.isin(tr.transcript_id)]
    ln = ex.assign(l=ex.end - ex.start + 1).groupby("transcript_id").l.sum()
    tr["length"] = tr.transcript_id.map(ln).fillna(0).astype(np.int32)
    tr["n_exons"] = tr.transcript_id.map(ex.groupby("transcript_id").size()).fillna(0).astype(np.int16)
    tr["gene_id"] = tr.gene_id.astype(np.int32)
    write(tr, "isoform_transcripts", sort_by=["gene_id", "transcript_id"])
    write(ex, "isoform_exons", sort_by=["transcript_id", "exon_number"])
    log.info("structure: %d transcripts of %d genes, %d exons", len(tr), tr.gene_id.nunique(), len(ex))
    return tr, ex

def build_bins(tr: pd.DataFrame, ex: pd.DataFrame, genes: dict) -> None:
    """Exon bins for detail genes: union of overlapping exons; labelled from the reference transcript where configured."""
    gm = get_mapper(); out_b, out_m = [], []
    for sym, cfg in genes.items():
        cfg = cfg or {}
        gid = gm.symbol(sym)
        if gid is None:
            log.warning("isoform gene %s not found", sym); continue
        t = tr[tr.gene_id == gid]; e = ex[ex.transcript_id.isin(t.transcript_id)].sort_values("start")
        if e.empty:
            continue
        strand = t.strand.iloc[0]
        bins, cur = [], None
        for s, en in zip(e.start, e.end):
            if cur and s <= cur[1]:
                cur[1] = max(cur[1], en)
            else:
                cur = [s, en]; bins.append(cur)
        bins = sorted(bins, key=lambda b: b[0], reverse=(strand == "-"))
        b = pd.DataFrame(bins, columns=["start", "end"]); b["bin"] = np.arange(1, len(b) + 1)
        b["label"] = "E" + b.bin.astype(str)
        ref = cfg.get("reference_transcript"); labels = cfg.get("exon_labels")
        if ref and labels:
            re_ = ex[ex.transcript_id == ref].sort_values("exon_number")
            if len(re_) != len(labels):
                log.warning("%s: reference %s has %d exons but %d labels; using generic labels", sym, ref, len(re_), len(labels))
            else:
                b["label"] = None
                for (s, en), lab in zip(zip(re_.start, re_.end), labels):
                    hit = (b.start <= en) & (b.end >= s)
                    b.loc[hit & b.label.isna(), "label"] = lab
                k = 0
                for i in b.index[b.label.isna()]:
                    k += 1; b.at[i, "label"] = f"alt{k}"
        variable = set(cfg.get("variable") or [])
        mem = []
        for tid, g in e.groupby("transcript_id"):
            for i, r in b.iterrows():
                if ((g.start <= r.end) & (g.end >= r.start)).any():
                    mem.append((tid, int(gid), int(r.bin)))
        m = pd.DataFrame(mem, columns=["transcript_id", "gene_id", "bin"])
        n_tr = m.transcript_id.nunique()
        b["n_transcripts"] = b.bin.map(m.groupby("bin").size()).fillna(0).astype(int)
        b["is_variable"] = b.label.isin(variable) if variable else (b.n_transcripts < n_tr)
        b["gene_id"] = int(gid); b["symbol"] = sym; b["chrom"] = t.chrom.iloc[0]; b["strand"] = strand
        out_b.append(b); out_m.append(m)
    if out_b:
        write(pd.concat(out_b, ignore_index=True), "isoform_exon_bins", sort_by=["gene_id", "bin"])
        write(pd.concat(out_m, ignore_index=True), "isoform_bin_member", sort_by=["gene_id", "transcript_id"])

def build_xena_isoforms(tr: pd.DataFrame, detail_gene_ids: set[int], chunksize: int = 2500, path=None, max_chunks: int | None = None, out_suffix: str = "") -> None:
    path = path or I / "TcgaTargetGtex_rsem_isoform_tpm.gz"
    if not path.exists():
        log.warning("Xena isoform matrix missing; skipping"); return
    groups, members = sample_groups()
    with gzip.open(path, "rt") as f:
        header = f.readline().rstrip("\n").split("\t")
    samples = header[1:]; pos = {s: i for i, s in enumerate(samples)}
    members = members[members.sample_id.isin(pos)]
    idx = {(t, k): np.array(sorted(pos[s] for s in g.sample_id)) for (t, k), g in members.groupby(["context_type", "key"])}
    ctx = read("contexts")
    cid = {(t, k): int(c) for t, k, c in zip(ctx.context_type, ctx.key, ctx.context_id)}
    keep_t = dict(zip(tr.transcript_id, tr.gene_id))
    detail_t = set(tr[tr.gene_id.isin(detail_gene_ids)].transcript_id)
    in_any = np.array(sorted(set(np.concatenate(list(idx.values())))))
    parts, detail = [], []
    dtypes = {s: np.float32 for s in samples}; dtypes[header[0]] = str
    for ci, chunk in enumerate(pd.read_csv(path, sep="\t", chunksize=chunksize, index_col=0, dtype=dtypes, na_values=["NA"])):
        tid = pd.Series(chunk.index).str.replace(r"\.\d+$", "", regex=True)
        keep = tid.isin(keep_t).values
        if not keep.any():
            continue
        chunk = chunk.loc[keep]; tids = tid[keep].values
        tpm = np.clip(np.power(2.0, chunk.values.astype(np.float64)) - 0.001, 0, None)
        x = np.log2(tpm + 1).astype(np.float32)
        for (t, k), ii in idx.items():
            if (t, k) not in cid:
                continue
            sub = x[:, ii]
            q = np.nanpercentile(sub, [25, 50, 75], axis=1)
            parts.append(pd.DataFrame({"context_id": cid[(t, k)], "transcript_id": tids, "median": q[1], "q25": q[0], "q75": q[2],
                                       "mean_tpm": np.nanmean(tpm[:, ii], axis=1), "frac_expr": np.mean(sub >= EXPR_CUTOFF, axis=1)}))
        dmask = np.isin(tids, list(detail_t))
        if dmask.any():
            d = pd.DataFrame(tpm[dmask][:, in_any].astype(np.float32), index=tids[dmask], columns=[samples[i] for i in in_any])
            dl = d.stack().reset_index(); dl.columns = ["transcript_id", "sample_id", "tpm"]
            detail.append(dl)
        if ci % 10 == 0:
            log.info("isoform chunk %d", ci)
        if max_chunks and ci + 1 >= max_chunks:
            break
    s = pd.concat(parts, ignore_index=True)
    s["gene_id"] = s.transcript_id.map(keep_t).astype(np.int32)
    gene_mean = s.groupby(["context_id", "gene_id"]).mean_tpm.transform("sum")
    s["pooled_frac"] = np.where(gene_mean > 0, s.mean_tpm / gene_mean, np.nan)
    for c in ("median", "q25", "q75", "mean_tpm", "frac_expr", "pooled_frac"):
        s[c] = s[c].astype(np.float32)
    s["source"] = "xena"
    write(s, "isoform_context_summary" + out_suffix, sort_by=["gene_id", "context_id", "transcript_id"])
    if detail:
        write(pd.concat(detail, ignore_index=True), "isoform_detail" + out_suffix, sort_by=["transcript_id", "sample_id"])
    log.info("xena isoforms: %d summary rows, %d transcripts", len(s), s.transcript_id.nunique())

def build_depmap_isoforms(tr: pd.DataFrame, detail_gene_ids: set[int]) -> None:
    """Optional: DepMap OmicsExpressionTranscriptTPMLogp1HumanAllGenes.csv (per profile). Only detail genes are kept,
    per cell line (default profile); aggregates (lineages) are computed at query time from the lines."""
    cands = sorted(I.glob("OmicsExpressionTranscript*TPMLogp1*.csv"))
    cands = [c for c in cands if "Stranded" not in c.name] or cands
    if not cands:
        log.info("DepMap transcript file not present; cell-line isoforms skipped"); return
    path = cands[0]
    header = pd.read_csv(path, nrows=0).columns.tolist()
    want = set(tr[tr.gene_id.isin(detail_gene_ids)].transcript_id)
    def tid_of(c):  # 'CD44 (ENST00000428726)' or 'ENST00000428726.6' style
        m = re.search(r"(ENST\d+)", c); return m.group(1) if m else None
    cols = [c for c in header if tid_of(c) in want]
    meta = [c for c in header if c in ("ModelID", "IsDefaultEntryForModel", "SequencingID")] or [header[0]]
    df = pd.read_csv(path, usecols=meta + cols, low_memory=False)
    if "IsDefaultEntryForModel" in df.columns:
        df = df[df.IsDefaultEntryForModel.astype(str).str.lower().isin(["yes", "true", "1"])]
    idcol = "ModelID" if "ModelID" in df.columns else meta[0]
    long = df.set_index(idcol)[cols].stack().reset_index(); long.columns = ["sample_id", "col", "logtpm"]
    long["transcript_id"] = long.col.map(tid_of)
    long["tpm"] = (np.power(2.0, long.logtpm.astype(float)) - 1).clip(lower=0).astype(np.float32)
    out = long[["transcript_id", "sample_id", "tpm"]]
    prev = read("isoform_detail") if exists("isoform_detail") else None
    if prev is not None:
        prev = prev[~prev.sample_id.str.startswith("ACH-")]
        out = pd.concat([prev, out], ignore_index=True)
    write(out, "isoform_detail", sort_by=["transcript_id", "sample_id"])
    log.info("DepMap transcripts: %d values for %d lines (%s)", len(long), long.sample_id.nunique(), path.name)

def build_isoforms() -> None:
    genes = detail_config()
    tr, ex = build_structure()
    build_bins(tr, ex, genes)
    gm = get_mapper()
    dg = {gm.symbol(s) for s in genes} - {None}
    build_xena_isoforms(tr, dg)
    build_depmap_isoforms(tr, dg)
