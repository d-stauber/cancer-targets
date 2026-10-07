"""`ct build`: run harmonization steps in dependency order."""
import logging, time
from ..paths import RAW
from . import genes, depmap, gtex, hpa, uniprot, surfaceome, opentargets, proteomics, xena, contexts
from .util import exists

log = logging.getLogger("ct.build")

STEPS = [
    ("genes", genes.build_gene_map),
    ("models", depmap.build_models),
    ("depmap_expr", depmap.build_expression),
    ("crispr", depmap.build_crispr),
    ("gtex", gtex.build_gtex),
    ("hpa", hpa.build_all),
    ("uniprot", uniprot.build_uniprot),
    ("surfaceome", surfaceome.build_surfaceome),
    ("opentargets", opentargets.build_opentargets),
    ("proteomics", proteomics.build_proteomics),
    ("xena", xena.build_xena),
    ("contexts", contexts.build_contexts_and_summary),
]

def run(steps: list[str] | None = None):
    for name, fn in STEPS:
        if steps and name not in steps:
            continue
        t0 = time.time()
        log.info("=== build step: %s ===", name)
        fn()
        log.info("=== %s done in %.0fs ===", name, time.time() - t0)
    from .db import build_db
    build_db()
