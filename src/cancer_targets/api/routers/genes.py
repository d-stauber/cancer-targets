from typing import Optional
from fastapi import APIRouter, HTTPException, Query
from ..db import q, records, columnar
from ..scoring_sql import parse_weights, composite_sql, load_cfg

router = APIRouter(tags=["genes"])

def _gene(symbol: str):
    # priority: official symbol / stable ids (1) > previous symbol (2) > alias (3)
    d = q("""select * from (
               select g.*, 1 as tier from gene_map g where upper(g.symbol) = upper(?) or g.ensembl_gene_id = ? or g.uniprot_acc = ? or cast(g.entrez_id as varchar) = ?
               union all
               select g.*, 2 from gene_map g where list_contains(string_split(coalesce(g.prev_symbols,''),'|'), ?)
               union all
               select g.*, 3 from gene_map g where list_contains(string_split(coalesce(g.alias_symbols,''),'|'), ?))
             order by tier, symbol limit 1""", [symbol, symbol, symbol, symbol, symbol, symbol])
    if d.empty:
        raise HTTPException(404, f"gene not found: {symbol}")
    return records(d)[0]

@router.get("/genes/search")
def search(q_: str = Query(..., alias="q"), limit: int = 20):
    s = q_.strip()
    d = q("""select symbol, name, gene_id from gene_map
             where upper(symbol) like upper(?) or upper(coalesce(alias_symbols,'')) like upper(?) or upper(coalesce(prev_symbols,'')) like upper(?) or upper(name) like upper(?)
             order by (upper(symbol) = upper(?)) desc, (upper(symbol) like upper(?)) desc, length(symbol), symbol limit ?""",
          [f"{s}%", f"%{s}%", f"%{s}%", f"%{s}%", s, f"{s}%", limit])
    return records(d)

@router.get("/genes/{symbol}")
def gene(symbol: str):
    g = _gene(symbol)
    gid = g["gene_id"]
    st = records(q("select * from gene_static where gene_id = ?", [gid]))
    uni = records(q("select uniprot_acc, entry_name, protein_name, length, subcellular_location, function, n_tm, has_signal, is_gpi, kw_secreted from uniprot where gene_id = ?", [gid]))
    ot = records(q("select ot_name, ot_subcellular, ot_target_class, function_desc, tractability, ot_isInMembrane, ot_isSecreted, ot_hasSafetyEvent, ot_isCancerDriverGene, ot_maxClinicalStage, n_safety_events, safety_events from ot_target where gene_id = ?", [gid]))
    drugs = records(q("select drug_name, drug_type, phase, action_type, mechanism, diseases from ot_known_drugs where gene_id = ? order by phase desc nulls last, drug_name limit 100", [gid]))
    assoc = records(q("""select l.disease_name, a.score, a.evidenceCount from ot_assoc a join ot_disease_lookup l using(disease_id)
                         where a.gene_id = ? order by a.score desc limit 30""", [gid]))
    sub = records(q("select main_location, additional_location, extracellular_location, reliability from hpa_subcellular where gene_id = ?", [gid]))
    ihc = records(q("select tissue, level_num from hpa_normal_ihc where gene_id = ? order by level_num desc, tissue", [gid]))
    dep = records(q("""select count(*) as n_lines, avg(effect) as mean_effect, sum(case when effect < -0.5 then 1 else 0 end) as n_dependent
                       from crispr_effect where gene_id = ?""", [gid])) if _has("crispr_effect") else []
    return {"gene": g, "static": st[0] if st else None, "uniprot": uni[0] if uni else None, "opentargets": ot[0] if ot else None,
            "known_drugs": drugs, "associations": assoc, "hpa_subcellular": sub[0] if sub else None, "hpa_normal_ihc": ihc,
            "dependency": dep[0] if dep else None}

def _has(view: str) -> bool:
    return not q("select table_name from information_schema.tables where table_name = ?", [view]).empty

@router.get("/genes/{symbol}/expression")
def expression(symbol: str, source: str = "cell_lines"):
    g = _gene(symbol); gid = g["gene_id"]
    if source == "cell_lines":
        d = q("""select c.name, c.key as model_id, c.lineage, c.primary_disease, c.is_normal, s.median as value, s.qn
                 from all_summary s join all_contexts c using(context_id) where s.gene_id = ? and c.context_type in ('cell_line','custom') order by c.lineage, value desc""", [gid])
    else:
        types = {"lineages": "('lineage','normal_lines')", "primary_diseases": "('primary_disease')", "subtypes": "('subtype')",
                 "tcga": "('tcga','target','tcga_normal')", "gtex": "('gtex_tissue')", "gtex_toil": "('gtex_toil')", "hpa_rna": "('hpa_rna_tissue')"}
        d = q(f"""select c.name, c.key, c.context_type, c.n_members, c.is_normal, s.median, s.qn, s.mean, s.q25, s.q75, s.p90, s.max, s.frac_expr, s.n
                  from all_summary s join all_contexts c using(context_id) where s.gene_id = ? and c.context_type in {types.get(source, "('lineage')")}
                  order by c.is_normal, s.median desc""", [gid])
    return {"gene": g["symbol"], "source": source, "rows": records(d)}

@router.get("/genes/{symbol}/rank_summary")
def rank_summary(symbol: str, profile: str = "any_modality", types: Optional[str] = None):
    """Counts of contexts where the gene reaches given percentiles (default weights)."""
    g = _gene(symbol); gid = g["gene_id"]
    p = profile if profile in load_cfg()["profiles"] else "any_modality"
    d = q(f"""select count(*) as n_contexts, count(*) filter (where s.pct_{p} >= 95) as n_ge95, count(*) filter (where s.pct_{p} >= 99) as n_ge99,
                     count(*) filter (where s.rank_{p} <= 10) as n_top10
              from all_scores s join all_contexts c using(context_id) where s.gene_id = ?
              {"and c.context_type in (select unnest(string_split(?, ',')))" if types else ""}""", [gid] + ([types] if types else []))
    return records(d)[0]

@router.get("/genes/{symbol}/rankings")
def rankings(symbol: str, profile: str = "any_modality", weights: Optional[str] = None, min_pct: float = 0, limit: int = 100,
             types: Optional[str] = None):
    g = _gene(symbol); gid = g["gene_id"]
    if weights:
        # Custom weights require re-ranking every gene in every requested context (tens of millions of rows); ~1-3 s.
        cfg = load_cfg(); w = parse_weights(weights, profile)
        scope = "context_id in (select context_id from all_contexts where context_type in (select unnest(string_split(?, ','))))" if types else "true"
        inner = composite_sql(w, profile == "surface", None, cfg["thresholds"], cfg["selectivity_parts"], where=scope)
        sql = f"""with sc as (select context_id, gene_id, score, x, E, S_eff as S, P, T, U, R, A, D, gate,
                              rank() over (partition by context_id order by score desc nulls last) as rank,
                              100.0*percent_rank() over (partition by context_id order by score asc nulls first) as pct from ({inner}))
                  select c.context_id, c.context_type, c.name, c.lineage, c.n_members, sc.* exclude(context_id, gene_id)
                  from sc join all_contexts c using(context_id) where sc.gene_id = ? and sc.pct >= ?
                  {"and c.context_type in (select unnest(string_split(?, ',')))" if types else ""}
                  order by sc.score desc nulls last limit ?"""
        params = ([types] if types else []) + [gid, min_pct] + ([types] if types else []) + [limit]
    else:
        p = profile if profile in load_cfg()["profiles"] else "any_modality"
        sql = f"""select c.context_id, c.context_type, c.name, c.lineage, c.n_members, s.score_{p} as score, s.x, s.E, s.S, s.P, s.T, s.U, s.R, s.A, s.D, s.gate,
                         s.rank_{p} as rank, s.pct_{p} as pct, s.x_matched, s.lfc_matched, s.n_ref, s.n_vital_max
                  from all_scores s join all_contexts c using(context_id) where s.gene_id = ? and s.pct_{p} >= ?
                  {"and c.context_type in (select unnest(string_split(?, ',')))" if types else ""}
                  order by score desc nulls last, pct desc limit ?"""
        params = [gid, min_pct] + ([types] if types else []) + [limit]
    return {"gene": g["symbol"], "profile": profile, "rows": records(q(sql, params))}
