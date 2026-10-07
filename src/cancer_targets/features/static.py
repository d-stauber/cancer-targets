"""Context-independent gene features: surface accessibility (U), tractability/precedent (R), normal references."""
import logging
import numpy as np, pandas as pd
from ..harmonize.util import read, exists, write
from .normal import normal_reference, hpa_normal_penalty, load_thresholds

log = logging.getLogger("ct.static")

def surface_score(gene_map: pd.DataFrame) -> pd.DataFrame:
    g = gene_map[["gene_id", "symbol"]].copy()
    uni = read("uniprot") if exists("uniprot") else pd.DataFrame(columns=["gene_id"])
    sf = read("surfaceome") if exists("surfaceome") else pd.DataFrame(columns=["gene_id"])
    hpa = read("hpa_subcellular") if exists("hpa_subcellular") else pd.DataFrame(columns=["gene_id"])
    ot = read("ot_target") if exists("ot_target") else pd.DataFrame(columns=["gene_id"])
    d = g.merge(uni, how="left").merge(sf, how="left").merge(hpa, how="left").merge(ot, how="left")
    f = lambda c, default=False: d[c].fillna(default) if c in d.columns else pd.Series(default, index=d.index)
    sf_surface = (f("surfaceome_label", "") == "surface") & (pd.to_numeric(f("ml_score", 0), errors="coerce").fillna(0) >= 0.5)
    sf_ids = f("in_surfaceome_ids").astype(bool)
    has_cd = f("cd_number", "").astype(str).str.match(r"^CD\d")
    tier1 = sf_surface | sf_ids | has_cd
    n_tm = pd.to_numeric(f("n_tm", 0), errors="coerce").fillna(0)
    tier2 = (f("has_signal").astype(bool) & (n_tm >= 1) & f("has_extracellular_topo").astype(bool)) | f("is_gpi").astype(bool)
    main = f("main_location", "").astype(str)
    hpa_pm = main.str.contains("Plasma membrane|Cell Junctions", regex=True) & f("reliability", "").isin(["Enhanced", "Supported"])
    ot_mem = pd.to_numeric(f("ot_isInMembrane", 0), errors="coerce").fillna(0) >= 1
    topo = (n_tm >= 1) | f("has_signal").astype(bool) | f("is_gpi").astype(bool)
    tier3 = (hpa_pm & topo) | (ot_mem & (n_tm >= 1)) | (f("kw_cell_membrane").astype(bool) & (n_tm >= 1))
    tier4 = n_tm >= 1
    secreted = f("kw_secreted").astype(bool) | (pd.to_numeric(f("ot_isSecreted", 0), errors="coerce").fillna(0) >= 1)
    U = np.select([tier1, tier2, tier3, tier4, secreted], [1.0, 0.85, 0.6, 0.4, 0.2], default=0.0).astype(np.float32)
    tier = np.select([tier1, tier2, tier3, tier4, secreted],
                     ["surfaceome", "signal+TM extracellular / GPI", "membrane annotation", "TM only", "secreted"], default="intracellular/unknown")
    out = pd.DataFrame({"gene_id": d.gene_id, "U": U, "U_tier": tier, "is_surface": U >= 0.6, "is_secreted": secreted.values,
                        "n_tm": n_tm.astype(np.int16).values, "has_signal": f("has_signal").astype(bool).values,
                        "surfaceome_label": f("surfaceome_label", None).values if "surfaceome_label" in d else None,
                        "ml_score": pd.to_numeric(f("ml_score", np.nan), errors="coerce").values,
                        "cd_number": f("cd_number", None).values if "cd_number" in d else None,
                        "dark_surfaceome": f("dark_surfaceome").astype(bool).values,
                        "hpa_main_location": main.replace("", None).values,
                        "ot_subcellular": f("ot_subcellular", None).values if "ot_subcellular" in d else None})
    return out

def tractability_score(gene_map: pd.DataFrame) -> pd.DataFrame:
    g = gene_map[["gene_id"]].copy()
    ot = read("ot_target") if exists("ot_target") else pd.DataFrame(columns=["gene_id", "tractability"])
    kd = read("ot_known_drugs") if exists("ot_known_drugs") else pd.DataFrame(columns=["gene_id", "phase", "drug_name"])
    d = g.merge(ot[["gene_id", "tractability", "ot_maxClinicalStage", "n_safety_events"]] if "ot_maxClinicalStage" in ot else ot[["gene_id", "tractability"]], how="left")
    tr = d.tractability.fillna("") if "tractability" in d else pd.Series("", index=d.index)
    def bucket(s, mod):
        # OT 26.x categories: 'Approved Drug','Advanced Clinical','Phase 1 Clinical','Structure with Ligand','High-Quality Ligand',
        # 'High-Quality Pocket','Med-Quality Pocket','Druggable Family' (SM); AB: 'UniProt loc high conf','GO CC high conf',
        # 'UniProt loc med conf','UniProt SigP or TMHMM','GO CC med conf','Human Protein Atlas loc'
        if f"{mod}:Approved Drug" in s: return 1.0
        if f"{mod}:Advanced Clinical" in s: return 0.8
        if f"{mod}:Phase 1 Clinical" in s: return 0.7
        if mod == "AB":
            if "AB:UniProt loc high conf" in s or "AB:GO CC high conf" in s: return 0.5
            if "AB:UniProt loc med conf" in s or "AB:UniProt SigP or TMHMM" in s or "AB:GO CC med conf" in s or "AB:Human Protein Atlas loc" in s: return 0.3
        if mod == "SM":
            if "SM:Structure with Ligand" in s or "SM:High-Quality Ligand" in s: return 0.6
            if "SM:High-Quality Pocket" in s or "SM:Med-Quality Pocket" in s or "SM:Druggable Family" in s: return 0.3
        if mod == "PR" and "PR:" in s: return 0.5
        return 0.0
    R_ab = tr.map(lambda s: bucket(s, "AB")).astype(np.float32)
    R_sm = tr.map(lambda s: bucket(s, "SM")).astype(np.float32)
    R_pr = tr.map(lambda s: bucket(s, "PR")).astype(np.float32)
    ph = kd.groupby("gene_id")["phase"].max().rename("max_phase") if len(kd) else pd.Series(dtype=float, name="max_phase")
    d = d.merge(ph.reset_index(), how="left")
    R_ph = d.max_phase.map({4: 1.0, 3: 0.8, 2: 0.6, 1: 0.4, 0.5: 0.3}).fillna(0).astype(np.float32)
    nd = kd.groupby("gene_id").size().rename("n_known_drugs") if len(kd) else pd.Series(dtype=int, name="n_known_drugs")
    d = d.merge(nd.reset_index(), how="left")
    return pd.DataFrame({"gene_id": d.gene_id, "R": np.maximum.reduce([R_ab, R_sm, R_pr, R_ph]), "R_ab": R_ab, "R_sm": R_sm,
                         "max_phase": d.max_phase.values, "n_known_drugs": d.n_known_drugs.fillna(0).astype(np.int16).values,
                         "tractability": tr.replace("", None).values,
                         "n_safety_events": d.n_safety_events.fillna(0).astype(np.int16).values if "n_safety_events" in d else 0})

def build_static() -> pd.DataFrame:
    th = load_thresholds()["thresholds"]
    g = read("gene_map")
    out = g[["gene_id", "symbol"]].merge(surface_score(g), how="left").merge(tractability_score(g), how="left")
    if exists("contexts"):
        ctx = read("contexts"); s = read("expr_context_summary", columns=["context_id", "gene_id", "qn"])
        for ctype, suffix in (("gtex_tissue", "v10"), ("gtex_toil", "toil")):
            sub = ctx[ctx.context_type == ctype][["context_id", "key"]]
            if len(sub):
                lt = s.merge(sub).rename(columns={"key": "tissue", "qn": "value"})[["gene_id", "tissue", "value"]]
                nr = normal_reference(lt, th["vital_forgiveness"])
                out = out.merge(nr.rename(columns={"n_ref": f"n_ref_{suffix}", "n_vital_max": f"n_vital_max_{suffix}", "n_ref_tissue": f"n_ref_tissue_{suffix}"}), how="left")
    out = out.merge(hpa_normal_penalty(), how="left")
    if exists("common_essentials"):
        out = out.merge(read("common_essentials"), how="left")
        out["is_common_essential"] = out.is_common_essential.fillna(False).astype(bool)
    else:
        out["is_common_essential"] = False
    write(out, "gene_static", sort_by=["gene_id"])
    log.info("gene_static: %d genes, %d surface (U>=0.6)", len(out), int((out.U >= 0.6).sum()))
    return out
