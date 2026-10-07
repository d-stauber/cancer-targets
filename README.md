# Cancer Targets — at-scale target discovery pipeline + web app

Scores every human protein-coding gene as a therapeutic target for every **context**: each DepMap cell line, each DepMap
lineage / primary disease / OncoTree subtype, and each TCGA / TARGET cancer type. The score combines tumor expression,
selectivity vs normal tissue (vital-tissue weighted), tumor protein evidence, surface accessibility, tractability /
clinical precedent and disease association. A FastAPI + React app exposes an expression explorer, per-gene pages and
per-context target rankings with adjustable weights.

## Quick start (with the prebuilt data bundle — recommended)

The code is on GitHub; the data (~5 GB) is shared separately via [Dropbox](https://www.dropbox.com/scl/fo/jhh19v4aeivmwzyi50hnt/APFvghOPwPr9kIfE_u3LeU4?rlkey=e71l7aztf0bou3x6aape5cb4r&st=b36kavdg&dl=0) as two tarballs:

| Bundle | Contents | Size | Needed? |
|---|---|---|---|
| `cancer-targets-processed-<date>.tar` | `data/processed/*.parquet` — harmonised expression, annotations, 34 M gene × context scores | ~2.1 GB | **yes**, to run the app |
| `cancer-targets-raw-<date>.tar` | `data/raw/` — every source file as downloaded (DepMap 24Q4, Xena TOIL, HPA, Open Targets, UniProt, HGNC, surfaceome tables, CCLE proteomics) | ~3.2 GB | only to rebuild / rescore from scratch |

```bash
git clone https://github.com/d-stauber/cancer-targets.git && cd cancer-targets
make setup                                            # venv + python deps + npm install (needs Python ≥3.11, Node ≥18)
tar -xf ~/Downloads/cancer-targets-processed-*.tar -C data/   # creates data/processed/
.venv/bin/ct db                                        # builds data/ct.duckdb views for this machine
make serve                                            # http://localhost:8000
```
Development: `make dev` (API on :8000 with reload, Vite on :5173 proxying `/api`). Tests: `make test`.
To expose the app to other machines: `.venv/bin/ct serve --host 0.0.0.0`.

## Rebuilding from raw data

```bash
tar -xf cancer-targets-raw-*.tar -C data/   # or: make download  (DepMap must then be fetched via figshare/manually)
make build            # harmonize -> data/processed/*.parquet + data/ct.duckdb   (~15 min, Xena streaming dominates)
make score            # gene x context components, composites, ranks; then benchmark
.venv/bin/ct bundle   # re-create the tarballs in data/bundles/ for sharing
```

## Data sources (versions recorded in `data/raw/manifest.json`)
| Source | Used for |
|---|---|
| DepMap Public (figshare; latest mirrored release 24Q4) — `Model.csv`, `OmicsExpressionProteinCodingGenesTPMLogp1.csv`, `CRISPRGeneEffect.csv`, common essentials | cell-line expression (log2 TPM+1), lineages/subtypes, 137 non-cancerous lines (e.g. MCF 10A, MCF12A, HMEL) as matched normals, dependency (display only) |
| UCSC Xena TOIL recompute (`TcgaTargetGtex_rsem_gene_tpm`) | TCGA + TARGET tumors, TCGA adjacent normals and GTEx in one pipeline (tumor-vs-normal comparisons) |
| GTEx v10 median TPM | vital-tissue-weighted normal reference for cell-line contexts |
| Human Protein Atlas v25 (`normal_ihc_data`, `subcellular_location`, `rna_tissue_consensus`) | normal tissue protein levels (IHC), localization, bone marrow / lymphoid RNA |
| Open Targets 26.09 (`target`, `target_tractability`, `target_prioritisation`, `target_safety_event`, `association_overall_direct`, `clinical_target`, `drug_molecule`, `drug_mechanism_of_action`, `disease`) | tractability buckets, known drugs & phases, disease association, safety |
| UniProt (reviewed human) | topology (TM, signal peptide, extracellular domains, GPI), function text |
| HGNC | master gene map (19.3k protein-coding genes) |
| Bausch-Fluck 2018 in silico surfaceome + local dark-surfaceome atlas (from `~/Downloads`) | surface labels, ML score, CD numbers |
| CCLE proteomics (Nusinow 2020) | tumor protein evidence for cell lines |

**Newer DepMap releases**: the DepMap portal blocks scripted downloads; drop the files listed in `config/sources.yaml`
into `data/raw/depmap/` (or run `ct download -s depmap --from <dir>`) and rerun `make build && make score`.

## Scoring (see `config/weights.yaml`)
Components in [0,1]; missing components are dropped and weights renormalised (`evidence` = number present).

* All scoring uses **quantile-normalised** expression: each context's median log2(TPM+1) vector is mapped onto the pooled
  GTEx v10 reference distribution (`qn` column), which removes pipeline scale differences between DepMap, GTEx and TOIL
  while preserving within-context ranks. Raw medians are kept for display (`x_raw`).
* **E** expression: `clip((x − 1)/5)` with x = quantile-normalised log2(TPM+1) (context median).
* **S** selectivity: 0.5·`S_gtex` + 0.25·`S_match` + 0.25·`S_hpa`.
  `S_gtex = clip((x − n_ref)/4)`, where `n_ref = max_t(x_t − (1 − w_t)·2)` over normal tissues with vital weights from
  `config/tissue_weights.csv` (heart/brain/lung/liver/kidney/blood/marrow = 1.0 … breast/prostate/ovary = 0.4, testis exempt).
  The normal reference is TOIL-GTEx (RSEM, the same quantifier as DepMap and TCGA) for every context; GTEx v10
  (RNA-SeQC, unique reads only) under-counts pseudogene-rich genes such as PPIA and ribosomal proteins and is kept for
  display only. `S_match` uses the matched normal (non-cancerous DepMap lines of the same lineage, else the mapped TOIL
  GTEx site; TCGA adjacent normal for TCGA).
  `S_hpa = 1 − max_t(w_t·IHC level/3)`.
* **P** prevalence: fraction of member lines/samples with x ≥ 2 (aggregate contexts only).
* **T** tumor protein: CCLE proteomics percentile (cell lines). HPA cancer IHC is wired but the per-cancer file is no longer
  downloadable from HPA, so T is empty for TCGA contexts unless `cancer_ihc_data.tsv.zip` is placed in `data/raw/hpa/`.
* **U** surface accessibility (tiered): 1.0 surfaceome / CD antigen; 0.85 signal peptide + TM with extracellular domain or GPI;
  0.6 HPA plasma-membrane (enhanced/supported) or OT membrane, each backed by ≥1 TM helix / signal peptide / GPI anchor
  (peripheral membrane proteins such as GAPDH are excluded); 0.4 TM only; 0.2 secreted.
* **R** tractability: max of OT antibody bucket, small-molecule bucket and known-drug max phase.
* **A** Open Targets association score for the context's cancer (`config/context_map.csv`), else 0.5 × pan-cancer.
* **D** CRISPR dependency (display only; weight 0).

The weighted mean is then multiplied by `0.25 + 0.75·S`, so a gene cannot rank highly on expression alone; selectivity is
required. Gates (score 0): x < 1; vital-normal gate (a vital tissue is expressed ≥ ~50 TPM **and** the tumor is more than 4× below
it); surface profile also requires U ≥ 0.6. Percentiles are the fraction of genes in the context with a strictly lower score. Profiles: `any_modality` (default) and `surface`; any weight vector can be supplied at query time
(`weights=E:0.3,S:0.4,...`) and a custom control context can replace the matched normal (`control=<context_id>`).

`ct benchmark` checks known targets (ERBB2 in BT-474/SK-BR-3/BRCA, TROP2, NECTIN4, CD19, MSLN, CLDN18, DLL3, FOLR1, GPC3,
CEACAM5, EGFR, CD20, BCMA, PSMA, CD33, EPCAM) reach the expected percentile (all 25 do, 24Q4/26.09 build) and
housekeeping / cardiac genes are gated or score < 0.25; the report is written to `data/processed/benchmark_report.md`.

## Layout
`config/` (sources, weights, tissue weights, context map, benchmark) · `src/cancer_targets/download` · `harmonize`
(gene map, per-source parsers, contexts + `expr_context_summary`) · `features` (normal references, static gene features) ·
`scoring` (components, ranks, benchmark) · `api` (FastAPI; DuckDB over parquet) · `web/` (Vite + React + Plotly).

## App pages
* **Home** – gene search (⌘K anywhere), example genes, build statistics, scoring legend.
* **Explorer** – two context pickers (grouped, keyboard-navigable), presets, axis swap, quantile-normalised or raw statistics,
  surface filter, gene highlighting, click-to-inspect, sortable differential table with CSV export; state lives in the URL.
* **Gene page** – badges and stat tiles (best context, surface/tractability scores, vital-tissue max, CRISPR), identity &
  function, localization evidence, normal-tissue IHC, known drugs, "where it ranks" table with stacked score breakdowns, and
  expression plots across cell lines, TCGA/TARGET, GTEx and DepMap lineages (tumor = blue, normal = aqua).
* **Target rankings** – profile toggle, matched-control override, filters, collapsible weight sliders with presets
  (selectivity-first, novelty, ADC/antibody, inhibitor/degrader), context tiles, sortable table with breakdown bars, CSV.
* **Custom controls** – drag-and-drop upload of an expression profile.
Light and dark themes (toggle in the nav; follows the OS by default). Chart colors follow a CVD-validated categorical palette.

## API
`/api/meta`, `/api/contexts?type=&q=`, `/api/contexts/{id}/targets?profile=&weights=&surface_only=&control=&format=csv`,
`/api/genes/search?q=`, `/api/genes/{symbol}`, `/api/genes/{symbol}/expression?source=cell_lines|lineages|tcga|gtex`,
`/api/genes/{symbol}/rankings?profile=`, `/api/explorer/scatter?x=&y=&stat=`, `/api/explorer/ranking?x=&y=&format=csv`,
`GET /api/genes/{symbol}/rank_summary`, `POST /api/controls` (upload a custom expression profile; it is quantile-normalised
and scored immediately, 50 MB limit), `GET /api/health`. Ranks and percentiles are always computed over the whole context;
table filters apply afterwards. Weights must be in [0, 1]. Interactive docs at `/docs`.

## Caveats
On macOS the Desktop folder's cloud sync can set the "hidden" flag on files, which makes Python 3.12 skip the venv's
`.pth` files; the venv therefore also has a `sitecustomize.py` that adds `src/` to `sys.path` (recreated by `make setup`).

DepMap, GTEx v10 and TOIL are different RNA-seq pipelines; cross-source fold changes are approximate (use the
"percentile rank" statistic in the explorer). Primary HMEC is not in DepMap; use the immortalized breast lines or upload
an HMEC profile as a custom control.
