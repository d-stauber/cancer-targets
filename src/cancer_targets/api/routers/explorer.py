from typing import Optional
import io
from fastapi import APIRouter, HTTPException
from fastapi.responses import StreamingResponse
from ..db import q, columnar, records

router = APIRouter(tags=["explorer"])
STATS = {"qn": "qn", "median": "median", "mean": "mean", "pct_rank": "pct_rank", "p90": "p90", "frac_expr": "frac_expr"}

def _scatter(x: int, y: int, stat: str, surface_only: bool, min_expr: float):
    col = STATS.get(stat, "median")
    lfc_col = "median" if stat in ("median", "mean", "p90") else "qn"
    sql = f"""select g.symbol, g.gene_id, a.{col} as x, b.{col} as y, (a.{lfc_col} - b.{lfc_col})::FLOAT as lfc, st.is_surface, st.U_tier, st.max_phase
              from (select gene_id, median, qn, {col} from all_summary where context_id = ?) a
              join (select gene_id, median, qn, {col} from all_summary where context_id = ?) b using(gene_id)
              join gene_map g using(gene_id) left join gene_static st using(gene_id)
              where greatest(a.qn, b.qn) >= ? {"and st.is_surface" if surface_only else ""}"""
    return q(sql, [x, y, min_expr])

@router.get("/explorer/scatter")
def scatter(x: int, y: int, stat: str = "qn", surface_only: bool = False, min_expr: float = 0.0):
    d = _scatter(x, y, stat, surface_only, min_expr)
    names = q("select context_id, name, context_type from all_contexts where context_id in (?, ?)", [x, y])
    return {"x": records(names[names.context_id == x])[0] if (names.context_id == x).any() else None,
            "y": records(names[names.context_id == y])[0] if (names.context_id == y).any() else None,
            "stat": stat, "n": len(d), "data": columnar(d)}

@router.get("/explorer/ranking")
def ranking(x: int, y: int, sort: str = "lfc", surface_only: bool = False, min_expr: float = 1.0, limit: int = 200, format: str = "json"):
    d = _scatter(x, y, "qn", surface_only, min_expr)
    asc = sort.startswith("-")
    d = d.sort_values(sort.lstrip("-"), ascending=asc)
    if format == "csv":
        buf = io.StringIO(); d.to_csv(buf, index=False)
        return StreamingResponse(iter([buf.getvalue()]), media_type="text/csv", headers={"Content-Disposition": "attachment; filename=ranking.csv"})
    return {"n": len(d), "rows": records(d.head(limit))}
