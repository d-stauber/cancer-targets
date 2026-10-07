"""Bausch-Fluck 2018 in silico surfaceome + local dark-surfaceome atlas."""
import logging, re
import numpy as np, pandas as pd, openpyxl
from ..paths import RAW
from .util import write, read, exists
from .genes import get_mapper

log = logging.getLogger("ct.surfaceome")
S = RAW / "surfaceome"

def _sheet(path, sheet) -> pd.DataFrame:
    wb = openpyxl.load_workbook(path, read_only=True, data_only=False)
    rows = list(wb[sheet].iter_rows(values_only=True))
    hdr_i = next(i for i, r in enumerate(rows) if r and r[0] == "UniProt name")
    df = pd.DataFrame(rows[hdr_i + 1:], columns=rows[hdr_i])
    return df.dropna(how="all")

def build_surfaceome():
    gm = get_mapper()
    uni = read("uniprot")[["gene_id", "entry_name", "uniprot_acc"]] if exists("uniprot") else None
    by_entry = dict(zip(uni.entry_name, uni.gene_id)) if uni is not None else {}
    df = _sheet(S / "table_S3_surfaceome.xlsx", "SurfaceomeMasterTable")
    acc = df["UniProt accession"].astype(str).str.extract(r"([A-Z][0-9][A-Z0-9]{3}[0-9](?:-\d+)?)")[0]
    df["gene_id"] = df["UniProt name"].map(by_entry).astype("Int32")
    m = df.gene_id.isna(); df.loc[m, "gene_id"] = acc[m].map(gm.uniprot).astype("Int32")
    m = df.gene_id.isna(); df.loc[m, "gene_id"] = df.loc[m, "Ensembl gene"].map(gm.ensembl).astype("Int32")
    m = df.gene_id.isna(); df.loc[m, "gene_id"] = df.loc[m, "UniProt gene"].map(gm.symbol).astype("Int32")
    log.info("surfaceome master table: %d rows, %d mapped", len(df), df.gene_id.notna().sum())
    df = df.dropna(subset=["gene_id"])
    out = pd.DataFrame({
        "gene_id": df.gene_id.astype(np.int32),
        "surfaceome_label": df["Surfaceome Label"].astype(str),
        "surfaceome_source": df["Surfaceome Label Source"].astype(str),
        "ml_score": pd.to_numeric(df["MachineLearning score"], errors="coerce").astype(np.float32),
        "sf_n_tm": pd.to_numeric(df["TM domains"], errors="coerce").astype("Int16"),
        "sf_signal": pd.to_numeric(df["signalpeptide"], errors="coerce").fillna(0).astype(bool),
        "sf_topology": df["topology"].astype(str),
        "cd_number": df["CD number"].astype(str).replace({"None": None, "nan": None}) if "CD number" in df.columns else None,
    })
    ids = set((S / "surfaceome_ids.txt").read_text().split()) if (S / "surfaceome_ids.txt").exists() else set()
    id_genes = {by_entry[e] for e in ids if e in by_entry}
    out["in_surfaceome_ids"] = out.gene_id.isin(id_genes)
    out = out.sort_values(["gene_id", "ml_score"], ascending=[True, False]).drop_duplicates("gene_id")
    # dark surfaceome atlas: collect gene symbols from Protein_atlas sheet
    dark = set()
    p = S / "Dark_Surfaceome_Evidence_Atlas.xlsx"
    if p.exists():
        wb = openpyxl.load_workbook(p, read_only=True, data_only=True)
        for sn in ("Protein_atlas", "Quick_view"):
            if sn not in wb.sheetnames: continue
            rows = list(wb[sn].iter_rows(values_only=True))
            for r in rows:
                for v in r:
                    if isinstance(v, str) and re.fullmatch(r"[A-Z0-9][A-Z0-9-]{1,10}", v):
                        gid = gm.symbol(v)
                        if gid is not None: dark.add(gid)
    out["dark_surfaceome"] = out.gene_id.isin(dark)
    extra = pd.DataFrame({"gene_id": sorted(dark - set(out.gene_id))})
    if len(extra):
        extra["dark_surfaceome"] = True
        out = pd.concat([out, extra], ignore_index=True)
    write(out, "surfaceome", sort_by=["gene_id"])
    log.info("surfaceome: %d genes, %d surface-labelled, %d dark", len(out), (out.surfaceome_label == "surface").sum(), len(dark))
