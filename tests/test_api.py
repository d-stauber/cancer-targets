"""End-to-end API tests; skipped when the database has not been built."""
import pytest
from cancer_targets.paths import DB

pytestmark = pytest.mark.skipif(not DB.exists(), reason="data/ct.duckdb not built")

@pytest.fixture(scope="module")
def client():
    from fastapi.testclient import TestClient
    from cancer_targets.api.main import app
    return TestClient(app)

def test_meta(client):
    m = client.get("/api/meta").json()
    assert m["n_genes"] > 18000 and "any_modality" in m["profiles"]

def test_gene_and_rankings(client):
    g = client.get("/api/genes/ERBB2").json()
    assert g["gene"]["symbol"] == "ERBB2" and g["static"]["is_surface"]
    assert any(d["drug_name"].upper() == "TRASTUZUMAB" for d in g["known_drugs"])
    r = client.get("/api/genes/HER2/rankings?profile=surface&limit=5").json()  # alias resolution
    assert r["gene"] == "ERBB2" and len(r["rows"]) == 5 and r["rows"][0]["pct"] > 99

def test_context_targets_and_custom_weights(client):
    bt = client.get("/api/contexts?q=BT-474&type=cell_line").json()[0]
    t = client.get(f"/api/contexts/{bt['context_id']}/targets?profile=surface&limit=20").json()
    syms = [r["symbol"] for r in t["rows"]]
    assert "ERBB2" in syms[:5]
    t2 = client.get(f"/api/contexts/{bt['context_id']}/targets?profile=any_modality&weights=E:0.1,S:0.6&limit=5").json()
    assert t2["weights"]["S"] == 0.6 and len(t2["rows"]) == 5
    csv = client.get(f"/api/contexts/{bt['context_id']}/targets?profile=surface&format=csv&limit=10")
    assert csv.headers["content-type"].startswith("text/csv") and "ERBB2" in csv.text

def test_explorer(client):
    bt = client.get("/api/contexts?q=BT-474&type=cell_line").json()[0]
    br = client.get("/api/contexts?q=Breast&type=gtex_tissue").json()[0]
    s = client.get(f"/api/explorer/scatter?x={bt['context_id']}&y={br['context_id']}&min_expr=1").json()
    assert s["n"] > 5000 and len(s["data"]["symbol"]) == s["n"]
    i = s["data"]["symbol"].index("ERBB2")
    assert s["data"]["lfc"][i] > 3

def test_no_path_traversal(client):
    r = client.get("/../../pyproject.toml")
    assert "[build-system]" not in r.text

def test_ranks_stable_under_filters(client):
    bt = client.get("/api/contexts?q=BT-474&type=cell_line").json()[0]
    full = client.get(f"/api/contexts/{bt['context_id']}/targets?limit=30").json()
    filt = client.get(f"/api/contexts/{bt['context_id']}/targets?limit=30&min_expr=5").json()
    full_rank = {r["symbol"]: r["rank"] for r in full["rows"]}
    for r in filt["rows"]:
        if r["symbol"] in full_rank:
            assert r["rank"] == full_rank[r["symbol"]]
    assert filt["matching"] < filt["total"] == full["total"]

def test_bad_weights_rejected(client):
    bt = client.get("/api/contexts?q=BT-474&type=cell_line").json()[0]
    assert client.get(f"/api/contexts/{bt['context_id']}/targets?weights=E:abc").status_code == 400
    assert client.get(f"/api/contexts/{bt['context_id']}/targets?weights=E:-1").status_code == 400
    assert client.get(f"/api/contexts/{bt['context_id']}/targets?weights=Q:0.5").status_code == 400

def test_lookup_prefers_official_symbol(client):
    assert client.get("/api/genes/TF").json()["gene"]["symbol"] == "TF"   # TF is also an alias of F3
    assert client.get("/api/genes/HER2").json()["gene"]["symbol"] == "ERBB2"

def test_rank_summary_and_health(client):
    s = client.get("/api/genes/ERBB2/rank_summary?profile=surface").json()
    assert s["n_ge95"] > 100 and s["n_contexts"] > 1000
    assert client.get("/api/health").json()["status"] == "ok"

def test_custom_upload_is_scored(client, tmp_path, monkeypatch):
    from cancer_targets.api import db as dbmod
    from cancer_targets.api.routers import controls as ctl
    custom = tmp_path / "custom"; custom.mkdir()
    monkeypatch.setattr(dbmod, "CUSTOM", custom); monkeypatch.setattr(ctl, "CUSTOM", custom)
    genes = client.get("/api/genes/search?q=ERBB").json()
    import pandas as pd
    gm = pd.read_parquet(dbmod.DB.parent / "processed" / "gene_map.parquet")[["symbol"]]
    df = pd.concat([gm.head(3000), gm[gm.symbol == "ERBB2"]]).drop_duplicates()
    df["tpm"] = 5.0; df.loc[df.symbol == "ERBB2", "tpm"] = 5000.0
    csv = df.to_csv(index=False).encode()
    r = client.post("/api/controls", files={"file": ("ctl.csv", csv, "text/csv")}, data={"name": "test control", "units": "tpm"})
    assert r.status_code == 200, r.text
    j = r.json(); assert j["n_scored"] > 2000
    t = client.get(f"/api/contexts/{j['context_id']}/targets?limit=20&gene_filter=ERBB2").json()
    assert t["rows"] and t["rows"][0]["symbol"] == "ERBB2" and t["rows"][0]["rank"] <= 20 and t["total"] > 2000
    sc = client.get(f"/api/explorer/scatter?x={j['context_id']}&y={j['context_id']}").json(); assert sc["n"] > 1000
