"""Open Targets Platform (26.x snake_case parquet layout)."""
import logging, glob
import duckdb, numpy as np, pandas as pd
from ..paths import RAW, CONFIG
from .util import write, log_unmapped
from .genes import get_mapper

log = logging.getLogger("ct.ot")
PHASE = {"APPROVAL": 4.0, "PHASE_4": 4.0, "PHASE_3": 3.0, "PHASE_2_3": 3.0, "PHASE_2": 2.0, "PHASE_1_2": 2.0, "PHASE_1": 1.0,
         "EARLY_PHASE_1": 0.5, "WITHDRAWAL": 4.0, "PRECLINICAL": 0.0, "UNKNOWN": None}
O = RAW / "opentargets"

def _pq(ds: str) -> str:
    files = sorted(glob.glob(str(O / ds / "*.parquet")))
    if not files:
        raise FileNotFoundError(f"no parquet for {ds}")
    return "read_parquet(" + repr(files) + ", union_by_name=true)"

def _join(l) -> str | None:
    try:
        items = list(l)
    except TypeError:
        return None
    items = [str(x) for x in items if x is not None]
    return "|".join(sorted(set(items))) if items else None

def _map_targets(df: pd.DataFrame, col: str, source: str) -> pd.DataFrame:
    gm = get_mapper()
    df["gene_id"] = df[col].map(gm.ensembl).astype("Int32")
    log_unmapped(source, df.loc[df.gene_id.isna(), col].unique())
    return df.dropna(subset=["gene_id"]).assign(gene_id=lambda d: d.gene_id.astype(np.int32))

def resolve_diseases(con) -> pd.DataFrame:
    """Resolve context_map disease_names -> disease ids by exact (case-insensitive) name, then exact synonym."""
    cm = pd.read_csv(CONFIG / "context_map.csv")
    names = sorted({n.strip() for s in cm.disease_names.dropna() for n in s.split("|")} | {"cancer", "neoplasm"})
    dis = con.execute(f"select id, lower(name) as name, exactSynonyms from {_pq('disease')}").df()
    by_name = {}
    for i, n in zip(dis.id, dis.name):
        by_name.setdefault(n, i)
    syn = {}
    for i, ss in zip(dis.id, dis.exactSynonyms):
        if ss is not None:
            for s in list(ss):
                syn.setdefault(str(s).lower(), i)
    rows = []
    for n in names:
        did = by_name.get(n.lower()) or syn.get(n.lower())
        rows.append((n, did))
    res = pd.DataFrame(rows, columns=["disease_name", "disease_id"])
    miss = res[res.disease_id.isna()].disease_name.tolist()
    if miss:
        log.warning("unresolved disease names: %s", miss)
    write(res.dropna(), "ot_disease_lookup")
    return res.dropna()

def build_opentargets() -> None:
    con = duckdb.connect()
    gm = get_mapper()
    # target basics
    t = con.execute(f"""select id, approvedSymbol, approvedName, biotype,
        list_transform(subcellularLocations, x -> x.location) as subcell,
        list_transform(targetClass, x -> x.label) as target_class,
        functionDescriptions[1] as function_desc from {_pq('target')} where biotype='protein_coding'""").df()
    t = _map_targets(t, "id", "ot_target")
    t["ot_subcellular"] = t.subcell.map(_join)
    t["ot_target_class"] = t.target_class.map(_join)
    tgt = t[["gene_id", "id", "approvedSymbol", "approvedName", "ot_subcellular", "ot_target_class", "function_desc"]].rename(
        columns={"id": "ensembl_gene_id", "approvedSymbol": "ot_symbol", "approvedName": "ot_name"}).drop_duplicates("gene_id")
    # tractability: modality (SM/AB/PR/OC), category, value(bool)
    tr = con.execute(f"select targetId, modality, category, value from {_pq('target_tractability')} where value").df()
    tr = _map_targets(tr, "targetId", "ot_tractability")
    tr["cat"] = tr.modality + ":" + tr.category
    trw = tr.groupby("gene_id")["cat"].agg(lambda s: "|".join(sorted(set(s)))).rename("tractability").reset_index()
    # prioritisation
    pr = con.execute(f"select * from {_pq('target_prioritisation')}").df()
    pr = _map_targets(pr, "targetId", "ot_prior").drop(columns=["targetId"]).drop_duplicates("gene_id")
    pr = pr[["gene_id"] + [c for c in pr.columns if c != "gene_id"]]
    pr.columns = ["gene_id"] + ["ot_" + c for c in pr.columns[1:]]
    # safety
    sf = con.execute(f"select targetId, count(*) as n_safety_events, string_agg(distinct event, '|') as safety_events from {_pq('target_safety_event')} group by 1").df()
    sf = _map_targets(sf, "targetId", "ot_safety").drop(columns=["targetId"]).drop_duplicates("gene_id")
    static = tgt.merge(trw, how="left").merge(pr, how="left").merge(sf, how="left")
    write(static, "ot_target", sort_by=["gene_id"])
    # associations for mapped diseases
    dl = resolve_diseases(con)
    ids = tuple(dl.disease_id.unique())
    a = con.execute(f"select targetId, diseaseId, associationScore as score, evidenceCount from {_pq('association_overall_direct')} where diseaseId in {ids}").df()
    a = _map_targets(a, "targetId", "ot_assoc").drop(columns=["targetId"])
    a["score"] = a.score.astype(np.float32)
    write(a.rename(columns={"diseaseId": "disease_id"}), "ot_assoc", sort_by=["gene_id", "disease_id"])
    # known drugs: clinical_target x drug_molecule x mechanism
    kd = con.execute(f"""
        select ct.targetId, ct.drugId, ct.maxClinicalStage as phase, dm.name as drug_name, dm.drugType as drug_type,
               list_transform(ct.diseases, x -> x.diseaseId) as disease_ids
        from {_pq('clinical_target')} ct left join {_pq('drug_molecule')} dm on dm.id = ct.drugId""").df()
    moa = con.execute(f"""select unnest(chemblIds) as drugId, unnest(targets) as targetId, actionType, mechanismOfAction
                          from {_pq('drug_mechanism_of_action')}""").df().drop_duplicates(["drugId", "targetId"])
    kd = kd.merge(moa, how="left", on=["drugId", "targetId"])
    kd = _map_targets(kd, "targetId", "ot_drugs").drop(columns=["targetId"])
    dis_names = con.execute(f"select id, name from {_pq('disease')}").df()
    dn = dict(zip(dis_names.id, dis_names.name))
    kd["diseases"] = kd.disease_ids.map(lambda l: _join([dn.get(x, x) for x in (list(l) if isinstance(l, (list, np.ndarray)) else []) if x]))
    kd = kd.drop(columns=["disease_ids"]).rename(columns={"drugId": "drug_id", "actionType": "action_type", "mechanismOfAction": "mechanism"})
    kd["phase"] = kd.phase.map(PHASE).astype(np.float32)
    write(kd, "ot_known_drugs", sort_by=["gene_id", "phase"])
    log.info("OT: %d targets, %d assoc rows, %d known-drug rows", len(static), len(a), len(kd))
