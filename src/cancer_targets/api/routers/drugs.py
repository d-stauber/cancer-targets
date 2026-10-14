"""PRISM drug sensitivity: per cell line / aggregate context, per drug, and per gene (compounds against the target)."""
from typing import Optional
import io
from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import StreamingResponse
from ..db import q, records

router = APIRouter(tags=["drugs"])
SENS_LFC = -1.0  # log2 fold-change viability at 2.5 uM below which a line is called sensitive (~50% viability)

def _has(view: str) -> bool:
    return not q("select table_name from information_schema.tables where table_name = ?", [view]).empty

@router.get("/drugs/search")
def search(q_: str = Query(..., alias="q"), limit: int = 20):
    if not _has("prism_compounds"):
        return []
    s = q_.strip().upper()
    return records(q("""select broad_id, name, moa, targets, screen, n_lines, median_lfc, frac_sensitive from prism_compounds
                        where name_upper like ? or upper(coalesce(synonyms,'')) like ? or upper(coalesce(targets,'')) like ? or upper(coalesce(moa,'')) like ?
                        order by (name_upper = ?) desc, (name_upper like ?) desc, n_lines desc, name limit ?""",
                     [f"{s}%", f"%{s}%", f"%{s}%", f"%{s}%", s, f"{s}%", limit]))

@router.get("/drugs/{broad_id}")
def drug(broad_id: str):
    c = q("select * exclude(name_upper) from prism_compounds where broad_id = ?", [broad_id])
    if c.empty:
        raise HTTPException(404, "compound not found")
    targets = records(q("""select t.gene_id, g.symbol, st.U_tier, st.is_surface from prism_targets t join gene_map g using(gene_id) left join gene_static st using(gene_id)
                           where t.broad_id = ? order by g.symbol""", [broad_id]))
    lines = records(q("""select c.context_id, c.name, c.lineage, c.primary_disease, l.lfc,
                                a.auc, a.ic50_um
                         from prism_lfc l join prism_compounds p using(broad_id) join all_contexts c on c.context_type = 'cell_line' and c.key = l.model_id
                         left join prism_auc a on a.model_id = l.model_id and a.core_id = p.core_id
                         where l.broad_id = ? order by l.lfc""", [broad_id])) if _has("prism_auc") else \
            records(q("""select c.context_id, c.name, c.lineage, c.primary_disease, l.lfc from prism_lfc l join all_contexts c on c.context_type='cell_line' and c.key = l.model_id
                         where l.broad_id = ? order by l.lfc""", [broad_id]))
    by_lineage = records(q("""select c.lineage, count(*) as n, median(l.lfc) as median_lfc, avg(case when l.lfc < ? then 1 else 0 end) as frac_sensitive
                              from prism_lfc l join all_contexts c on c.context_type = 'cell_line' and c.key = l.model_id
                              where l.broad_id = ? and c.lineage is not null group by 1 having count(*) >= 3 order by median_lfc""", [SENS_LFC, broad_id]))
    return {"compound": records(c)[0], "targets": targets, "lines": lines, "by_lineage": by_lineage, "sens_threshold_lfc": SENS_LFC}

@router.get("/contexts/{context_id}/drugs")
def context_drugs(context_id: int, sort: str = "lfc", limit: int = 200, moa: Optional[str] = None, target: Optional[str] = None, format: str = "json"):
    """Drug sensitivity for a cell line (its own PRISM profile) or an aggregate context (median over member lines)."""
    if not _has("prism_lfc"):
        raise HTTPException(404, "PRISM data not built")
    ctx = q("select context_type, key, name from all_contexts where context_id = ?", [context_id])
    if ctx.empty:
        raise HTTPException(404, "context not found")
    where, params = [], []
    if moa: where.append("upper(coalesce(p.moa,'')) like ?"); params.append(f"%{moa.upper()}%")
    if target: where.append("upper(coalesce(p.targets,'')) like ?"); params.append(f"%{target.upper()}%")
    w = (" and " + " and ".join(where)) if where else ""
    order = {"lfc": "lfc asc", "-lfc": "lfc desc", "selectivity": "(lfc - median_lfc) asc", "auc": "auc asc nulls last", "name": "name"}.get(sort, "lfc asc")
    if ctx.context_type[0] == "cell_line":
        sql = f"""select p.broad_id, p.name, p.moa, p.targets, p.screen, l.lfc, p.median_lfc, (l.lfc - p.median_lfc) as delta_vs_all_lines,
                         p.frac_sensitive, a.auc, a.ic50_um, 1 as n_lines
                  from prism_lfc l join prism_compounds p using(broad_id)
                  {"left join prism_auc a on a.model_id = l.model_id and a.core_id = p.core_id" if _has("prism_auc") else "left join (select null as model_id, null as core_id, null as auc, null as ic50_um) a on false"}
                  where l.model_id = ? {w} order by {order}, p.name limit ?"""
        params = [ctx.key[0]] + params + [limit if format == "json" else 100000]
    else:
        sql = f"""select p.broad_id, p.name, p.moa, p.targets, p.screen, median(l.lfc) as lfc, p.median_lfc, (median(l.lfc) - p.median_lfc) as delta_vs_all_lines,
                         p.frac_sensitive, median(a.auc) as auc, median(a.ic50_um) as ic50_um, count(*) as n_lines
                  from context_members m join prism_lfc l on l.model_id = m.sample_id join prism_compounds p using(broad_id)
                  {"left join prism_auc a on a.model_id = l.model_id and a.core_id = p.core_id" if _has("prism_auc") else "left join (select null as model_id, null as core_id, null as auc, null as ic50_um) a on false"}
                  where m.context_id = ? {w} group by 1,2,3,4,5,7,9 having count(*) >= 2 order by {order}, p.name limit ?"""
        params = [context_id] + params + [limit if format == "json" else 100000]
    d = q(sql, params)
    if format == "csv":
        buf = io.StringIO(); d.to_csv(buf, index=False)
        return StreamingResponse(iter([buf.getvalue()]), media_type="text/csv", headers={"Content-Disposition": f"attachment; filename=drugs_{context_id}.csv"})
    n_lines = int(q("select count(distinct l.model_id) as n from context_members m join prism_lfc l on l.model_id = m.sample_id where m.context_id = ?", [context_id]).n[0]) if ctx.context_type[0] != "cell_line" else int(len(d) > 0)
    return {"context_id": context_id, "name": ctx.name[0], "screened": n_lines > 0, "n_lines_screened": n_lines, "sens_threshold_lfc": SENS_LFC, "rows": records(d)}

@router.get("/genes/{symbol}/drugs")
def gene_drugs(symbol: str, context_id: Optional[int] = None):
    """Compounds annotated against this gene, with (optionally) their effect in one context."""
    if not _has("prism_targets"):
        return {"rows": []}
    g = q("select gene_id, symbol from gene_map where upper(symbol) = upper(?)", [symbol])
    if g.empty:
        raise HTTPException(404, "gene not found")
    gid = int(g.gene_id[0])
    if context_id is not None:
        ctx = q("select context_type, key from all_contexts where context_id = ?", [context_id])
        if not ctx.empty and ctx.context_type[0] == "cell_line":
            d = q("""select p.broad_id, p.name, p.moa, p.targets, p.n_lines, p.median_lfc, p.frac_sensitive, l.lfc as lfc_in_context
                     from prism_targets t join prism_compounds p using(broad_id) left join prism_lfc l on l.broad_id = p.broad_id and l.model_id = ?
                     where t.gene_id = ? order by l.lfc nulls last, p.name""", [ctx.key[0], gid])
            return {"gene": g.symbol[0], "context_id": context_id, "rows": records(d)}
        if not ctx.empty:
            d = q("""select p.broad_id, p.name, p.moa, p.targets, p.n_lines, p.median_lfc, p.frac_sensitive, median(l.lfc) as lfc_in_context
                     from prism_targets t join prism_compounds p using(broad_id)
                     left join (select l.* from prism_lfc l join context_members m on m.sample_id = l.model_id where m.context_id = ?) l on l.broad_id = p.broad_id
                     where t.gene_id = ? group by 1,2,3,4,5,6,7 order by lfc_in_context nulls last, p.name""", [context_id, gid])
            return {"gene": g.symbol[0], "context_id": context_id, "rows": records(d)}
    d = q("""select p.broad_id, p.name, p.moa, p.targets, p.n_lines, p.median_lfc, p.frac_sensitive, null as lfc_in_context
             from prism_targets t join prism_compounds p using(broad_id) where t.gene_id = ? order by p.frac_sensitive desc nulls last, p.name""", [gid])
    return {"gene": g.symbol[0], "context_id": None, "rows": records(d)}
