"""`ct score`: compute components + composites + ranks for all scored contexts, in batches."""
import logging, time
import numpy as np, pandas as pd
from ..paths import PROCESSED
from ..harmonize.util import read, write
from ..harmonize.db import build_db
from ..features.static import build_static
from .components import Scorer, add_ranks, SCORED_TYPES

log = logging.getLogger("ct.score")
OUT_COLS = ["context_id", "gene_id", "x", "x_raw", "E", "S", "S_gtex", "S_match", "S_hpa", "P", "T", "T_hpa", "T_prot", "U", "R", "A", "D",
            "chronos", "n_ref", "n_vital_max", "x_matched", "lfc_matched", "matched_context_id", "is_surface", "gate", "evidence"]

def run(batch: int = 150):
    build_static()
    sc = Scorer()
    ctx = sc.ctx
    todo = ctx[ctx.context_type.isin(SCORED_TYPES) & ~ctx.is_normal.astype(bool)].context_id.tolist()
    log.info("scoring %d contexts", len(todo))
    summ = read("expr_context_summary", columns=sc.summ_cols)
    summ = summ[summ.context_id.isin(todo)]
    parts = []
    t0 = time.time()
    for i in range(0, len(todo), batch):
        ids = todo[i:i + batch]
        d = sc.score_contexts(ids, summ[summ.context_id.isin(ids)])
        d = add_ranks(d, sc.profiles)
        cols = OUT_COLS + [c for c in d.columns if c.startswith(("score_", "rank_", "pct_"))]
        parts.append(d[cols])
        log.info("scored %d/%d contexts (%.0fs)", min(i + batch, len(todo)), len(todo), time.time() - t0)
    out = pd.concat(parts, ignore_index=True)
    for c in ("E", "S", "P", "T", "U", "R", "A", "D"):
        out[c] = out[c].astype(np.float32)
    write(out, "gene_context_scores", sort_by=["context_id", "gene_id"])
    # gene -> best contexts summary for quick lookup
    build_db()
    log.info("done: %d rows", len(out))
