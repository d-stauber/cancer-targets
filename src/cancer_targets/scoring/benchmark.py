"""`ct benchmark`: known targets should rank highly in their contexts; housekeeping genes should not."""
import logging
import pandas as pd, duckdb
from ..paths import CONFIG, DB, PROCESSED

log = logging.getLogger("ct.benchmark")
NEG_MAX_SCORE = 0.25

def run() -> pd.DataFrame:
    b = pd.read_csv(CONFIG / "benchmark.csv")
    con = duckdb.connect(str(DB), read_only=True)
    rows = []
    for r in b.itertuples():
        q = f"""select s.pct_{r.profile} as pct, s.rank_{r.profile} as rank, s.score_{r.profile} as score, s.x, s.E, s.S, s.P, s.T, s.U, s.R, s.A, s.gate,
                       c.name as context
                from gene_context_scores s join contexts c using(context_id) join gene_map g using(gene_id)
                where g.symbol = ? and c.context_type = ? and c.name = ?"""
        res = con.execute(q, [r.gene, r.context_type, r.context_key]).df()
        if res.empty:
            # try key match instead of name
            res = con.execute(q.replace("c.name = ?", "c.key = ?"), [r.gene, r.context_type, r.context_key]).df()
        if res.empty:
            rows.append(dict(gene=r.gene, context=r.context_key, profile=r.profile, kind=r.kind, pct=None, passed=False, note="context/gene not found"))
            continue
        x = res.iloc[0]
        # positives must reach the expected percentile; negatives must be gated or score below NEG_MAX_SCORE
        passed = (x.pct >= r.expected_min_percentile) if r.kind == "positive" else (x.pct <= r.expected_min_percentile or x.score < NEG_MAX_SCORE)
        rows.append(dict(gene=r.gene, context=x.context, profile=r.profile, kind=r.kind, expected=r.expected_min_percentile,
                         pct=round(float(x.pct), 1), rank=int(x["rank"]), score=round(float(x.score), 3), x=round(float(x.x), 2),
                         E=x["E"], S=x["S"], P=x["P"], T=x["T"], U=x["U"], R=x["R"], A=x["A"], gate=x["gate"], passed=bool(passed)))
    out = pd.DataFrame(rows)
    rate = out.passed.mean()
    md = ["# Benchmark report", "", f"Pass rate: **{rate:.0%}** ({out.passed.sum()}/{len(out)})", "",
          out.to_markdown(index=False, floatfmt=".2f")]
    (PROCESSED / "benchmark_report.md").write_text("\n".join(md))
    print(out.to_string(index=False))
    print(f"\nPass rate: {rate:.0%}")
    return out
