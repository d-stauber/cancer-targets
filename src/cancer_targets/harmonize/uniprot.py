"""UniProt human reviewed proteome: localization/topology features."""
import logging, re
import numpy as np, pandas as pd
from ..paths import RAW
from .util import write, col, log_unmapped
from .genes import get_mapper

log = logging.getLogger("ct.uniprot")

def build_uniprot() -> pd.DataFrame:
    gm = get_mapper()
    df = pd.read_csv(RAW / "uniprot" / "uniprot_human_reviewed.tsv.gz", sep="\t", low_memory=False)
    acc = col(df, "Entry"); name = col(df, "Entry Name")
    gp = col(df, "Gene Names (primary)"); gn = col(df, "Gene Names")
    df["gene_id"] = df[acc].map(gm.uniprot).astype("Int32")
    m = df.gene_id.isna(); df.loc[m, "gene_id"] = df.loc[m, gp].map(gm.symbol).astype("Int32")
    m = df.gene_id.isna()
    ens = col(df, "Ensembl")
    df.loc[m, "gene_id"] = df.loc[m, ens].astype(str).str.extract(r"(ENSG\d+)")[0].map(gm.ensembl).astype("Int32")
    log_unmapped("uniprot", df.loc[df.gene_id.isna(), acc])
    df = df.dropna(subset=["gene_id"])
    tm = df[col(df, "Transmembrane")].fillna("")
    topo = df[col(df, "Topological domain")].fillna("")
    sig = df[col(df, "Signal peptide")].fillna("")
    kw = df[col(df, "Keywords")].fillna("")
    sc = df[col(df, "Subcellular location [CC]")].fillna("")
    out = pd.DataFrame({
        "gene_id": df.gene_id.astype(np.int32),
        "uniprot_acc": df[acc], "entry_name": df[name],
        "protein_name": df[col(df, "Protein names")], "length": df[col(df, "Length")],
        "n_tm": tm.str.count("TRANSMEM").astype(np.int16),
        "has_signal": sig.str.contains("SIGNAL"),
        "has_extracellular_topo": topo.str.contains("Extracellular"),
        "is_gpi": kw.str.contains("GPI-anchor"),
        "kw_cell_membrane": kw.str.contains("Cell membrane"),
        "kw_secreted": kw.str.contains("Secreted"),
        "kw_membrane": kw.str.contains("Membrane"),
        "subcellular_location": sc.str.replace("SUBCELLULAR LOCATION: ", "").str.slice(0, 500),
        "function": df[col(df, "Function [CC]")].fillna("").str.replace("FUNCTION: ", "").str.slice(0, 1500),
    })
    # prefer canonical (shortest accession per gene, reviewed) -> first by n_tm desc to keep membrane isoform info
    out = out.sort_values(["gene_id", "n_tm"], ascending=[True, False]).drop_duplicates("gene_id")
    write(out, "uniprot", sort_by=["gene_id"])
    return out
