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
| `cancer-targets-processed-<date>.tar` | `data/processed/*.parquet` — harmonised expression, annotations, PRISM drug data, 44 M gene × context scores | ~3.5 GB | **yes**, to run the app |
| `cancer-targets-raw-<date>.tar` | `data/raw/` — every source file as downloaded (DepMap 26Q3, Xena TOIL, HPA v26, Open Targets 26.09, UniProt 2026_04, HGNC, PRISM, surfaceome tables, CCLE proteomics) | ~3.7 GB | only to rebuild / rescore from scratch |

```bash
git clone https://github.com/d-stauber/cancer-targets.git && cd cancer-targets
make setup                                            # venv + python deps + npm install (needs Python ≥3.11, Node ≥18)
tar -xf ~/Downloads/cancer-targets-processed-*.tar -C data/   # creates data/processed/
.venv/bin/ct db                                        # builds data/ct.duckdb views for this machine
make serve                                            # http://localhost:8000
```
Development: `make dev` (API on :8000 with reload, Vite on :5173 proxying `/api`). Tests: `make test`.
To expose the app to other machines: `.venv/bin/ct serve --host 0.0.0.0`.

## Windows

**WSL2 (recommended).** Inside an Ubuntu WSL shell the instructions above work unchanged, including `make`.

**Native Windows (PowerShell).** The code is portable (pure Python + Node; DuckDB, pandas, pyarrow and FastAPI all ship
Windows wheels; Windows 10/11 include `tar.exe`), only the `Makefile` is Unix-specific. Requirements: Python 3.11+ from
python.org (tick "Add to PATH"), Node.js 18+, Git.

```powershell
git clone https://github.com/d-stauber/cancer-targets.git; cd cancer-targets
powershell -ExecutionPolicy Bypass -File scripts\setup.ps1        # venv, Python deps, npm install, frontend build
tar -xf $HOME\Downloads\cancer-targets-processed-<date>.tar -C data\
.\.venv\Scripts\ct db
.\.venv\Scripts\ct serve                                        # http://localhost:8000
```
Wherever this README says `.venv/bin/<cmd>`, use `.venv\Scripts\<cmd>` on Windows (`ct`, `pytest`, `uvicorn`).
For development run the two servers in separate terminals: `.venv\Scripts\uvicorn cancer_targets.api.main:app --reload`
and `cd web; npm run dev`.

Caveats: stop the server before `ct db`, `ct build` or `ct score` — Windows locks the open database file and the rebuild
replaces it (on macOS/Linux this is not necessary). The `.claude/launch.json` entry is macOS-specific and only used by the
Claude desktop preview.

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
| DepMap Public 26Q3 — `Model.csv`, `OmicsExpressionTPMLogp1HumanProteinCodingGenes.csv` (default profile per model), `CRISPRGeneEffect.csv`, `CRISPRInferredCommonEssentials.csv`, `OmicsProfiles.csv` | expression for 2,130 lines (log2 TPM+1), lineages/subtypes, non-cancerous lines (e.g. HMEL) as matched normals, CRISPR dependency for 1,361 lines (display only) |
| UCSC Xena TOIL recompute (`TcgaTargetGtex_rsem_gene_tpm`) | TCGA + TARGET tumors, TCGA adjacent normals and GTEx in one pipeline (tumor-vs-normal comparisons) |
| GTEx v10 median TPM | vital-tissue-weighted normal reference for cell-line contexts |
| Human Protein Atlas v26.0 (`normal_ihc_data`, `subcellular_location`, `rna_tissue_consensus`) | normal tissue protein levels (IHC), localization, bone marrow / lymphoid RNA |
| Open Targets 26.09 (`target`, `target_tractability`, `target_prioritisation`, `target_safety_event`, `association_overall_direct`, `clinical_target`, `drug_molecule`, `drug_mechanism_of_action`, `disease`) | tractability buckets, known drugs & phases, disease association, safety |
| UniProt (reviewed human) | topology (TM, signal peptide, extracellular domains, GPI), function text |
| HGNC | master gene map (19.3k protein-coding genes) |
| Bausch-Fluck 2018 in silico surfaceome + local dark-surfaceome atlas (from `~/Downloads`) | surface labels, ML score, CD numbers |
| CCLE proteomics (Nusinow 2020) | tumor protein evidence for cell lines |
| UCSC Xena TOIL isoform TPM (`TcgaTargetGtex_rsem_isoform_tpm`, RSEM, GENCODE v23) + GENCODE v23 GTF | transcript-level expression in TCGA/TARGET tumors, TCGA adjacent normals and GTEx; exon structures; exon inclusion for genes in `config/isoform_genes.yaml` (CD44 v2–v10, ERBB2 Δ16, FGFR2 IIIb/IIIc, MET ex14, CD19 ex2, FN1 EDA/EDB, TNC, VEGFA, BCL2L1) |
| PRISM Repurposing (Broad; Public 24Q2 extended primary: 6,790 compounds × 919 lines at 2.5 µM; 19Q4 secondary: dose-response AUC/IC50 for 1,448 compounds × 489 lines) | drug sensitivity per cell line and per lineage; compound ↔ target links |

**Newer DepMap releases**: the portal is behind a Cloudflare check, so download `Model.csv`, `CRISPRGeneEffect.csv`,
`CRISPRInferredCommonEssentials.csv`, `OmicsProfiles.csv` and the protein-coding expression TPM file from the release page,
then `ct download -s depmap --from ~/Downloads --release "DepMap Public 26Q4"` (file names are matched by pattern, older files
should first be moved out of `data/raw/depmap/`), and rerun `make build && make score`.

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
* **Isoforms** – for any gene: transcript structure (exons in transcription order) and isoform composition per tumor type
  and normal tissue. For genes in `config/isoform_genes.yaml` (CD44 by default, with variant exons labelled v2–v10): per-sample
  exon inclusion (share of the gene's TPM from transcripts containing the exon) or absolute TPM, shown as tumor vs TCGA adjacent
  normal vs GTEx per tissue, with a table of medians, differences and AUROC. Add a gene to the YAML and run
  `ct build --step isoforms` to get the same view for it. Optional: put DepMap's
  `OmicsExpressionTranscriptTPMLogp1HumanAllGenes.csv` in `data/raw/isoforms/` to add cell lines.
* **Drugs** – compound search and drug pages (sensitivity by lineage and per cell line, targets); a "Drug sensitivity (PRISM)"
  panel on every cell-line / lineage rankings page (sort by sensitivity, selectivity vs all lines, or AUC; filter by target);
  and "compounds annotated against this gene" on gene pages. Sensitivity call: log2 FC viability < −1 at 2.5 µM.
Every chart's camera button opens an **export dialog** with a live preview: edit title and axis labels, font and sizes, grid
lines, axis box and tick marks, axis ranges / tick spacing / log scale, marker size, legend position, background (white,
transparent, dark), pixel size or journal presets (3.5″, 7″), resolution (1–4×) and format (PNG, SVG, JPEG); style choices are
remembered between exports.
Light and dark themes (toggle in the nav; follows the OS by default). Chart colors follow a CVD-validated categorical palette.

## API
`/api/meta`, `/api/contexts?type=&q=`, `/api/contexts/{id}/targets?profile=&weights=&surface_only=&control=&format=csv`,
`/api/genes/search?q=`, `/api/genes/{symbol}`, `/api/genes/{symbol}/expression?source=cell_lines|lineages|tcga|gtex`,
`/api/genes/{symbol}/rankings?profile=`, `/api/explorer/scatter?x=&y=&stat=`, `/api/explorer/ranking?x=&y=&format=csv`,
`GET /api/genes/{symbol}/rank_summary`, `GET /api/drugs/search?q=`, `GET /api/drugs/{broad_id}`,
`GET /api/contexts/{id}/drugs?sort=lfc|selectivity|auc&target=`, `GET /api/genes/{symbol}/drugs`, `POST /api/controls` (upload a custom expression profile; it is quantile-normalised
and scored immediately, 50 MB limit), `GET /api/health`. Ranks and percentiles are always computed over the whole context;
table filters apply afterwards. Weights must be in [0, 1]. Interactive docs at `/docs`.

## Caveats
On macOS the Desktop folder's cloud sync can set the "hidden" flag on files, which makes Python 3.12 skip the venv's
`.pth` files; the venv therefore also has a `sitecustomize.py` that adds `src/` to `sys.path` (recreated by `make setup`).

DepMap, GTEx v10 and TOIL are different RNA-seq pipelines; cross-source fold changes are approximate (use the
"percentile rank" statistic in the explorer). Primary HMEC is not in DepMap; use the immortalized breast lines or upload
an HMEC profile as a custom control.
