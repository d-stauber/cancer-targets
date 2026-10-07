"""Per gene x context components and composite scores."""
import logging
import numpy as np, pandas as pd
from ..harmonize.util import read, exists
from ..features.normal import load_thresholds

log = logging.getLogger("ct.components")
SCORED_TYPES = ("cell_line", "lineage", "primary_disease", "subtype", "tcga", "target", "custom")
COMPONENTS = ["E", "S", "P", "T", "U", "R", "A", "D"]

def composite(df: pd.DataFrame, weights: dict) -> pd.Series:
    """Weighted mean over non-null components with weight renormalization."""
    num = np.zeros(len(df), dtype=np.float32); den = np.zeros(len(df), dtype=np.float32)
    for c, w in weights.items():
        if w <= 0 or c not in df.columns: continue
        v = df[c].to_numpy(dtype=np.float32, na_value=np.nan)
        ok = ~np.isnan(v)
        num[ok] += w * v[ok]; den[ok] += w
    with np.errstate(invalid="ignore", divide="ignore"):
        s = np.where(den > 0, num / den, np.nan)
    return pd.Series(s.astype(np.float32), index=df.index)

class Scorer:
    def __init__(self, light: bool = False, extra_contexts: pd.DataFrame | None = None):
        """light=True skips the member-based components (CRISPR, proteomics) - used for custom uploads, which have no members."""
        cfg = load_thresholds()
        self.th = cfg["thresholds"]; self.profiles = cfg["profiles"]; self.sel = cfg["selectivity_parts"]
        self.ctx = read("contexts")
        if extra_contexts is not None and len(extra_contexts):
            self.ctx = pd.concat([self.ctx, extra_contexts[self.ctx.columns.intersection(extra_contexts.columns)]], ignore_index=True)
        self.static = read("gene_static")
        self.summ_cols = ["context_id", "gene_id", "median", "qn", "frac_expr", "n"]
        self.members = read("context_members")
        self.assoc = read("ot_assoc") if exists("ot_assoc") else None
        self.dis = read("ot_disease_lookup") if exists("ot_disease_lookup") else None
        self.cancer_id = None
        if self.dis is not None:
            m = self.dis[self.dis.disease_name.str.lower() == "cancer"]
            self.cancer_id = m.disease_id.iloc[0] if len(m) else None
        self.cancer_ihc = read("hpa_cancer_ihc") if exists("hpa_cancer_ihc") else None
        self.prot = read("ccle_proteomics", columns=["gene_id", "model_id", "pct"]) if (exists("ccle_proteomics") and not light) else None
        self.crispr = read("crispr_effect") if (exists("crispr_effect") and not light) else None
        # matched-normal lookup tables (context_id -> normal context_id)
        self.normal_ctx = self._matched_normal_map()

    def _matched_normal_map(self) -> dict:
        c = self.ctx
        by = {}
        nl = c[c.context_type == "normal_lines"].set_index("key").context_id.to_dict()
        gv = c[c.context_type == "gtex_tissue"].set_index("key").context_id.to_dict()
        tn = c[c.context_type == "tcga_normal"].set_index("key").context_id.to_dict()
        gt = c[c.context_type == "gtex_toil"].set_index("key").context_id.to_dict()
        for r in c[c.context_type.isin(SCORED_TYPES)].itertuples():
            m = None
            if r.context_type in ("tcga", "target"):
                m = tn.get(r.gtex_toil_site) if isinstance(r.gtex_toil_site, str) else None
                m = m if m is not None else (gt.get(r.gtex_toil_site) if isinstance(r.gtex_toil_site, str) else None)
            else:
                m = nl.get(r.lineage) if isinstance(r.lineage, str) else None
                m = m if m is not None else (gt.get(r.gtex_toil_site) if isinstance(r.gtex_toil_site, str) else None)
                m = m if m is not None else (gv.get(r.gtex_v10_tissue) if isinstance(r.gtex_v10_tissue, str) else None)
            by[r.context_id] = m
        return by

    def summary_for(self, context_ids) -> pd.DataFrame:
        s = read("expr_context_summary", columns=self.summ_cols)
        return s[s.context_id.isin(context_ids)]

    def score_contexts(self, context_ids: list[int], summ: pd.DataFrame | None = None, profiles: dict | None = None) -> pd.DataFrame:
        th, sel = self.th, self.sel
        profiles = profiles or self.profiles
        summ = summ if summ is not None else self.summary_for(context_ids)
        summ = summ[summ.context_id.isin(context_ids)].copy()
        ctx = self.ctx.set_index("context_id")
        st = self.static.set_index("gene_id")
        d = summ.rename(columns={"median": "x_raw", "qn": "x"})
        d["context_type"] = d.context_id.map(ctx.context_type)
        is_tcga = d.context_type.isin(["tcga", "target"])
        # --- E
        d["E"] = ((d.x - th["expr_floor"]) / (th["expr_ceiling"] - th["expr_floor"])).clip(0, 1).astype(np.float32)
        # --- P (aggregates only)
        d["P"] = np.where(d.n > 1, d.frac_expr, np.nan).astype(np.float32)
        # --- S: GTEx reference (pipeline-matched), matched normal, HPA IHC
        # TOIL GTEx (RSEM) is the reference for every context: DepMap and TCGA are RSEM-quantified too, whereas GTEx v10
        # (RNA-SeQC, unique reads) under-counts pseudogene-rich genes such as PPIA / ribosomal proteins.
        n_ref = d.gene_id.map(st.n_ref_toil).to_numpy(dtype=np.float32, na_value=np.nan)
        n_vit = d.gene_id.map(st.n_vital_max_toil).to_numpy(dtype=np.float32, na_value=np.nan)
        d["n_ref"] = n_ref.astype(np.float32); d["n_vital_max"] = n_vit.astype(np.float32)
        d["S_gtex"] = ((d.x - d.n_ref) / th["selectivity_scale"]).clip(0, 1).astype(np.float32)
        # matched normal
        mctx = d.context_id.map(self.normal_ctx)
        need = mctx.dropna().unique().astype(int)
        if len(need):
            ns = read("expr_context_summary", columns=["context_id", "gene_id", "qn"])
            ns = ns[ns.context_id.isin(need)].rename(columns={"context_id": "m_ctx", "qn": "x_matched"})
            d["m_ctx"] = mctx.astype("Int32")
            d = d.merge(ns, how="left", left_on=["m_ctx", "gene_id"], right_on=["m_ctx", "gene_id"])
            d["matched_context_id"] = d.m_ctx; d = d.drop(columns=["m_ctx"])
        else:
            d["x_matched"] = np.nan; d["matched_context_id"] = pd.array([None] * len(d), dtype="Int32")
        d["lfc_matched"] = (d.x - d.x_matched).astype(np.float32)
        d["S_match"] = (d.lfc_matched / th["selectivity_scale"]).clip(0, 1).astype(np.float32)
        d["S_hpa"] = d.gene_id.map(st.S_hpa).astype(np.float32) if "S_hpa" in st else np.nan
        parts = pd.DataFrame({"S_gtex": d.S_gtex, "S_match": d.S_match, "S_hpa": d.S_hpa})
        d["S"] = composite(parts, {"S_gtex": sel["gtex"], "S_match": sel["match"], "S_hpa": sel["hpa"]})
        # --- T: HPA cancer IHC by context cancer; CCLE proteomics pct for lines / member mean for depmap aggregates
        d["T_hpa"] = np.nan
        if self.cancer_ihc is not None:
            hc = d.context_id.map(ctx.hpa_cancer)
            ci = self.cancer_ihc.assign(T_hpa=lambda t: ((t.n_high + 0.5 * t.n_medium) / t.n_patients.clip(lower=1)).astype(np.float32))
            tmp = pd.DataFrame({"gene_id": d.gene_id, "cancer": hc}).merge(ci[["gene_id", "cancer", "T_hpa"]], how="left")
            d["T_hpa"] = tmp.T_hpa.values
        d["T_prot"] = np.nan
        if self.prot is not None:
            mem = self.members[self.members.context_id.isin(context_ids)]
            pm = mem.merge(self.prot, how="inner", left_on="sample_id", right_on="model_id")
            agg = pm.groupby(["context_id", "gene_id"])["pct"].mean().rename("T_prot").reset_index()
            d = d.drop(columns=["T_prot"]).merge(agg, how="left")
        d["T"] = composite(d[["T_hpa", "T_prot"]], {"T_hpa": 0.5, "T_prot": 0.5})
        # --- A: OT association
        d["A"] = np.nan
        if self.assoc is not None and self.dis is not None:
            name2id = dict(zip(self.dis.disease_name, self.dis.disease_id))
            rows = []
            for cid in context_ids:
                names = ctx.disease_names.get(cid)
                ids = [name2id[n] for n in str(names).split("|") if n in name2id] if isinstance(names, str) else []
                for i in ids: rows.append((cid, i))
            if rows:
                cd = pd.DataFrame(rows, columns=["context_id", "disease_id"])
                a = cd.merge(self.assoc[["gene_id", "disease_id", "score"]]).groupby(["context_id", "gene_id"])["score"].max().rename("A_dis").reset_index()
                d = d.merge(a, how="left")
            else:
                d["A_dis"] = np.nan
            if self.cancer_id is not None:
                pan = self.assoc[self.assoc.disease_id == self.cancer_id].set_index("gene_id").score
                d["A_pan"] = (d.gene_id.map(pan) * 0.5).astype(np.float32)
            else:
                d["A_pan"] = np.nan
            d["A"] = d.A_dis.fillna(d.A_pan).astype(np.float32)
        # --- D: CRISPR
        d["D"] = np.nan; d["chronos"] = np.nan
        if self.crispr is not None:
            mem = self.members[self.members.context_id.isin(context_ids)]
            cm = mem.merge(self.crispr, how="inner", left_on="sample_id", right_on="model_id")
            agg = cm.groupby(["context_id", "gene_id"])["effect"].mean().rename("chronos").reset_index()
            d = d.drop(columns=["chronos"]).merge(agg, how="left")
            d["D"] = ((-d.chronos - 0.3) / 0.7).clip(0, 1).astype(np.float32)
        # --- static U, R
        d["U"] = d.gene_id.map(st.U).astype(np.float32); d["R"] = d.gene_id.map(st.R).astype(np.float32)
        d["is_surface"] = d.gene_id.map(st.is_surface).astype(bool)
        # --- gates
        gate = np.full(len(d), None, dtype=object)
        low = d.x < th["expr_floor"]
        vital = (d.n_vital_max >= th["vital_gate_level"]) & ((d.x - d.n_vital_max) < th["vital_gate_margin"])
        gate[vital.fillna(False).values] = "vital_normal"
        gate[low.values] = "not_expressed"
        d["gate"] = gate
        # --- composites
        floor = th.get("selectivity_multiplier_floor", 0.25)
        mult = (floor + (1 - floor) * d.S.fillna(0.5)).astype(np.float32)
        for name, w in profiles.items():
            sc = composite(d, w) * mult
            sc[d.gate.notna()] = 0.0
            if name == "surface":
                sc[~d.is_surface] = 0.0
            d[f"score_{name}"] = sc.astype(np.float32)
        d["evidence"] = d[COMPONENTS].notna().sum(axis=1).astype(np.int8)
        return d

def add_ranks(d: pd.DataFrame, profiles) -> pd.DataFrame:
    for name in profiles:
        col = f"score_{name}"
        g = d.groupby("context_id")[col]
        d[f"rank_{name}"] = g.rank(ascending=False, method="min").astype(np.int32)
        n = d.groupby("context_id")[col].transform("size")
        d[f"pct_{name}"] = (100.0 * (g.rank(ascending=True, method="min") - 1) / n).astype(np.float32)
    return d
