from typing import Optional
from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import StreamingResponse
import io
from ..db import q, records
from ..scoring_sql import parse_weights, composite_sql, load_cfg

router = APIRouter(tags=["contexts"])
CTX_COLS = "context_id, context_type, key, name, n_members, lineage, primary_disease, subtype, is_normal, source, gtex_v10_tissue, gtex_toil_site, hpa_cancer, disease_names"

@router.get("/contexts")
def list_contexts(type: Optional[str] = None, q_: Optional[str] = Query(None, alias="q"), limit: int = 5000):
    where, params = [], []
    if type:
        where.append("context_type in (select unnest(string_split(?, ',')))"); params.append(type)
    if q_:
        where.append("(lower(name) like ? or lower(key) like ? or lower(lineage) like ?)"); params += [f"%{q_.lower()}%"] * 3
    sql = f"select {CTX_COLS} from all_contexts" + (" where " + " and ".join(where) if where else "") + " order by context_type, name limit ?"
    return records(q(sql, params + [limit]))

@router.get("/contexts/{context_id}")
def get_context(context_id: int):
    d = q(f"select {CTX_COLS} from all_contexts where context_id = ?", [context_id])
    if d.empty:
        raise HTTPException(404, "context not found")
    r = records(d)[0]
    mem = q("select sample_id from context_members where context_id = ? limit 5000", [context_id])
    r["members"] = mem.sample_id.tolist()
    return r

@router.get("/contexts/{context_id}/targets")
def targets(context_id: int, profile: str = "any_modality", weights: Optional[str] = None, surface_only: bool = False,
            min_expr: float = 0.0, min_selectivity: float = 0.0, exclude_essential: bool = False, control: Optional[int] = None,
            gene_filter: Optional[str] = None, limit: int = 200, offset: int = 0, format: str = "json"):
    """Rank every gene for one context. Ranks/percentiles are computed over the whole context; filters apply afterwards."""
    if q("select 1 from all_contexts where context_id = ?", [context_id]).empty:
        raise HTTPException(404, "context not found")
    cfg = load_cfg()
    w = parse_weights(weights, profile)
    inner = composite_sql(w, surface_only or profile == "surface", control, cfg["thresholds"], cfg["selectivity_parts"], where=f"context_id = {int(context_id)}")
    where, params = ["true"], []
    if min_expr > 0: where.append("x >= ?"); params.append(min_expr)
    if min_selectivity > 0: where.append("S >= ?"); params.append(min_selectivity)
    if exclude_essential: where.append("not coalesce(is_common_essential, false)")
    if gene_filter: where.append("lower(symbol) like ?"); params.append(f"%{gene_filter.lower()}%")
    ranked = f"""with ranked as (
        select g.symbol, g.name as gene_name, e.gene_id, e.score, e.x, e.E, e.S_eff as S, e.S_gtex, e.S_match_eff as S_match, e.S_hpa, e.P, e.T, e.U, e.R, e.A, e.D,
               e.n_ref, e.n_vital_max, e.x_control, e.matched_context_id, e.gate, e.is_surface, st.U_tier, st.max_phase, st.n_known_drugs, st.is_common_essential,
               rank() over (order by e.score desc nulls last) as rank,
               100.0 * percent_rank() over (order by e.score asc nulls first) as pct
        from ({inner}) e join gene_map g using(gene_id) left join gene_static st using(gene_id))"""
    d = q(f"{ranked} select * from ranked where {' and '.join(where)} order by score desc nulls last, symbol limit ? offset ?",
          params + [limit if format == "json" else 100000, offset])
    if format == "csv":
        buf = io.StringIO(); d.to_csv(buf, index=False)
        return StreamingResponse(iter([buf.getvalue()]), media_type="text/csv",
                                 headers={"Content-Disposition": f"attachment; filename=targets_{context_id}.csv"})
    counts = q(f"{ranked} select count(*) as total, count(*) filter (where {' and '.join(where)}) as matching from ranked", params).iloc[0]
    return {"context_id": context_id, "profile": profile, "weights": w, "total": int(counts.total), "matching": int(counts.matching), "rows": records(d)}
