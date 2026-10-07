"""Master gene map from HGNC (protein-coding genes) and id resolution helpers."""
import logging
import numpy as np, pandas as pd
from ..paths import RAW
from .util import write, read, exists, strip_version

log = logging.getLogger("ct.genes")

def build_gene_map() -> pd.DataFrame:
    h = pd.read_csv(RAW / "hgnc" / "hgnc_complete_set.txt", sep="\t", low_memory=False,
                    usecols=["hgnc_id", "symbol", "name", "locus_group", "locus_type", "entrez_id",
                             "ensembl_gene_id", "uniprot_ids", "prev_symbol", "alias_symbol", "status"])
    h = h[(h.locus_group == "protein-coding gene") & (h.status == "Approved")].copy()
    h = h.sort_values("symbol").reset_index(drop=True)
    h["gene_id"] = np.arange(len(h), dtype=np.int32)
    h["entrez_id"] = h.entrez_id.astype("Int64")
    h["uniprot_acc"] = h.uniprot_ids.fillna("").str.split("|").str[0].replace("", None)
    g = h[["gene_id", "symbol", "name", "hgnc_id", "entrez_id", "ensembl_gene_id", "uniprot_acc",
           "uniprot_ids", "prev_symbol", "alias_symbol", "locus_type"]].rename(
        columns={"prev_symbol": "prev_symbols", "alias_symbol": "alias_symbols"})
    write(g, "gene_map")
    return g

class GeneMapper:
    def __init__(self, g: pd.DataFrame | None = None):
        g = g if g is not None else read("gene_map")
        self.g = g
        self.by_symbol = dict(zip(g.symbol, g.gene_id))
        self.by_entrez = {int(e): i for e, i in zip(g.entrez_id, g.gene_id) if pd.notna(e)}
        self.by_ensembl = {e: i for e, i in zip(g.ensembl_gene_id, g.gene_id) if isinstance(e, str)}
        self.by_uniprot = {}
        for ids, i in zip(g.uniprot_ids, g.gene_id):
            if isinstance(ids, str):
                for u in ids.split("|"):
                    self.by_uniprot.setdefault(u, i)
        self.by_prev, self.by_alias = {}, {}
        for col, d in (("prev_symbols", self.by_prev), ("alias_symbols", self.by_alias)):
            for s, i in zip(g[col], g.gene_id):
                if isinstance(s, str):
                    for x in s.split("|"):
                        d.setdefault(x, i)

    def symbol(self, s):
        if not isinstance(s, str):
            return None
        for d in (self.by_symbol, self.by_prev, self.by_alias):
            if s in d:
                return d[s]
        return None

    def entrez(self, e):
        try:
            return self.by_entrez.get(int(e))
        except (TypeError, ValueError):
            return None

    def ensembl(self, e):
        if not isinstance(e, str):
            return None
        return self.by_ensembl.get(e.split(".")[0])

    def uniprot(self, u):
        return self.by_uniprot.get(u) if isinstance(u, str) else None

    def depmap_column(self, c: str):
        """'TP53 (7157)' -> gene_id via entrez, fallback symbol."""
        sym, _, rest = c.rpartition(" (")
        ent = rest.rstrip(")")
        g = self.entrez(ent)
        return g if g is not None else self.symbol(sym or c)

    def map_series(self, s: pd.Series, kind: str) -> pd.Series:
        f = {"symbol": self.symbol, "entrez": self.entrez, "ensembl": self.ensembl,
             "uniprot": self.uniprot, "depmap": self.depmap_column}[kind]
        return s.map(f).astype("Int32")

def get_mapper() -> GeneMapper:
    if not exists("gene_map"):
        build_gene_map()
    return GeneMapper()
