import numpy as np, pandas as pd
from cancer_targets.scoring.components import composite
from cancer_targets.features.normal import normal_reference, weight_for
from cancer_targets.harmonize.genes import GeneMapper

def test_composite_renormalizes_missing():
    df = pd.DataFrame({"E": [1.0, 0.5], "S": [np.nan, 0.5]})
    s = composite(df, {"E": 0.5, "S": 0.5})
    assert abs(s[0] - 1.0) < 1e-6 and abs(s[1] - 0.5) < 1e-6

def test_tissue_weights():
    assert weight_for("Heart_Left_Ventricle")[1] == 1.0
    assert weight_for("Brain_Cortex")[1] == 1.0
    assert weight_for("Testis")[1] == 0.0
    assert weight_for("Breast_Mammary_Tissue")[1] == 0.4
    assert weight_for("bone marrow")[1] == 1.0

def test_normal_reference_forgives_non_vital():
    long = pd.DataFrame({"gene_id": [1, 1, 1], "tissue": ["Liver", "Breast_Mammary_Tissue", "Testis"], "value": [3.0, 4.0, 10.0]})
    r = normal_reference(long, forgiveness=2.0)
    # breast (w=0.4) is forgiven 1.2 -> 2.8; liver (w=1) -> 3.0 wins
    assert abs(r.n_ref.iloc[0] - 3.0) < 1e-6 and r.n_ref_tissue.iloc[0] == "Liver"
    assert abs(r.n_vital_max.iloc[0] - 3.0) < 1e-6

def test_gene_mapper_depmap_column():
    g = pd.DataFrame({"gene_id": np.array([0, 1], dtype=np.int32), "symbol": ["TP53", "ERBB2"], "entrez_id": pd.array([7157, 2064], dtype="Int64"),
                      "ensembl_gene_id": ["ENSG00000141510", "ENSG00000141736"], "uniprot_ids": ["P04637", "P04626"],
                      "prev_symbols": [None, "NGL"], "alias_symbols": ["p53|LFS1", "HER2|NEU"]})
    gm = GeneMapper(g)
    assert gm.depmap_column("TP53 (7157)") == 0
    assert gm.depmap_column("HER2 (99999)") == 1
    assert gm.ensembl("ENSG00000141736.12") == 1
    assert gm.symbol("NEU") == 1
