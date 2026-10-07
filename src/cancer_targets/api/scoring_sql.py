"""Composite score SQL for custom weights / custom control contexts, evaluated in DuckDB at request time."""
import yaml
from fastapi import HTTPException
from ..paths import CONFIG

def load_cfg():
    return yaml.safe_load((CONFIG / "weights.yaml").read_text())

def parse_weights(spec: str | None, profile: str) -> dict:
    cfg = load_cfg()
    w = dict(cfg["profiles"].get(profile, cfg["profiles"]["any_modality"]))
    if spec:
        for kv in spec.split(","):
            if not kv.strip():
                continue
            if ":" not in kv:
                raise HTTPException(400, f"bad weight '{kv}': expected COMPONENT:value, e.g. E:0.3")
            k, v = kv.split(":", 1)
            k = k.strip()
            if k not in w:
                raise HTTPException(400, f"unknown component '{k}'; valid: {', '.join(w)}")
            try:
                x = float(v)
            except ValueError:
                raise HTTPException(400, f"weight for {k} is not a number: '{v}'")
            if not (0 <= x <= 1):
                raise HTTPException(400, f"weight for {k} must be between 0 and 1")
            w[k] = x
    if sum(w.values()) <= 0:
        raise HTTPException(400, "at least one weight must be > 0")
    return w

def composite_sql(w: dict, surface_only: bool, control_ctx: int | None, th: dict, sel: dict, where: str = "true") -> str:
    """Returns a SELECT producing (context_id, gene_id, score, S_eff, S_match_eff, x_control) from all_scores s.
    If control_ctx given, S_match is recomputed against that context and S re-blended."""
    if control_ctx is not None:
        s_expr = f"""(
          coalesce({sel['gtex']}*s.S_gtex,0) + coalesce({sel['match']}*S_match_eff,0) + coalesce({sel['hpa']}*s.S_hpa,0)
        ) / nullif(
          (case when s.S_gtex is null then 0 else {sel['gtex']} end) + (case when S_match_eff is null then 0 else {sel['match']} end) + (case when s.S_hpa is null then 0 else {sel['hpa']} end), 0)"""
        pre = f"""with ctl as (select gene_id, qn as x_control from all_summary where context_id = {int(control_ctx)}),
        base as (select s.*, ctl.x_control, least(greatest((s.x - ctl.x_control)/{th['selectivity_scale']}, 0), 1)::FLOAT as S_match_eff
                 from (select * from all_scores where {where}) s left join ctl using(gene_id)),
        eff as (select *, ({s_expr})::FLOAT as S_eff from base s)"""
    else:
        pre = f"with eff as (select s.*, s.S as S_eff, s.S_match as S_match_eff, s.x_matched as x_control from (select * from all_scores where {where}) s)"
    comps = {"E": "E", "S": "S_eff", "P": "P", "T": "T", "U": "U", "R": "R", "A": "A", "D": "D"}
    num = " + ".join(f"coalesce({w[c]}*{col},0)" for c, col in comps.items() if w.get(c, 0) > 0) or "0"
    den = " + ".join(f"(case when {col} is null then 0 else {w[c]} end)" for c, col in comps.items() if w.get(c, 0) > 0) or "0"
    gate = "gate is not null" + (" or not is_surface" if surface_only else "")
    floor = th.get("selectivity_multiplier_floor", 0.25)
    return f"""{pre}
    select *, (case when {gate} then 0 else (({num}) / nullif({den}, 0)) * ({floor} + {1 - floor} * coalesce(S_eff, 0.5)) end)::FLOAT as score from eff"""
