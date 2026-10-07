import json
from fastapi import APIRouter
from ..db import q
from ..scoring_sql import load_cfg
from ...paths import RAW

router = APIRouter(tags=["meta"])

@router.get("/meta")
def meta():
    cfg = load_cfg()
    man = RAW / "manifest.json"
    manifest = json.loads(man.read_text()) if man.exists() else {}
    counts = q("select context_type, count(*) as n from all_contexts group by 1 order by 1")
    ng = q("select count(*) as n from gene_map").n[0]
    return {"profiles": cfg["profiles"], "thresholds": cfg["thresholds"], "components": cfg["component_descriptions"],
            "context_counts": dict(zip(counts.context_type, counts.n.astype(int))), "n_genes": int(ng),
            "releases": {s: {k: v.get("release") for k, v in files.items()} for s, files in manifest.items()}}
