import { Fragment } from 'react'
import { useQuery } from '@tanstack/react-query'
import { Link } from 'react-router-dom'
import { api, TYPE_LABELS } from '../api'
import GeneSearch from '../components/GeneSearch'
import { ComponentLegend, Tile } from '../components/ui'

const EXAMPLES = ['ERBB2', 'TACSTD2', 'NECTIN4', 'CLDN18', 'DLL3', 'MSLN', 'CD276', 'ROR1']

export default function Home() {
  const { data } = useQuery({ queryKey: ['meta'], queryFn: api.meta })
  const counts = data?.context_counts || {}
  const n = (k: string) => counts[k] || 0
  return (
    <div className="stack">
      <div className="hero">
        <h1>Find and rank cancer targets</h1>
        <p>Every protein-coding gene scored as a target in every DepMap cell line, lineage and TCGA cancer type, from expression selectivity, normal-tissue safety, localization and clinical precedent.</p>
        <GeneSearch big autoFocus />
        <div className="chips" style={{ justifyContent: 'center', marginTop: 10 }}>{EXAMPLES.map(g => <Link key={g} className="chip" to={`/gene/${g}`}>{g}</Link>)}</div>
      </div>
      <div className="grid3">
        <Link to="/explorer" className="card feature"><h2>Expression explorer →</h2><p className="muted">Compare any two contexts gene-by-gene: a cell line vs its normal counterpart, a TCGA cancer type vs GTEx tissue, or your own uploaded control. Highlight genes, filter to surface proteins, export the differential list.</p></Link>
        <Link to="/context" className="card feature"><h2>Target rankings →</h2><p className="muted">Pick a cell line, lineage or cancer type and get all 19k genes ranked with a transparent score breakdown. Re-weight the components live, swap in a matched control, and download the table.</p></Link>
        <Link to="/controls" className="card feature"><h2>Custom controls →</h2><p className="muted">Upload an expression profile (for example primary HMEC RNA-seq) to use as a comparison context in the explorer and as the matched normal in rankings.</p></Link>
      </div>
      <div className="card">
        <div className="card-head"><h2>What's in this build</h2><span className="faint small">{data ? `${data.n_genes.toLocaleString()} protein-coding genes` : ''}</span></div>
        <div className="tiles">
          <Tile label="Cell lines" value={n('cell_line').toLocaleString()} hint="DepMap, incl. non-cancerous" />
          <Tile label="DepMap groups" value={n('lineage') + n('primary_disease') + n('subtype')} hint="lineages · diseases · subtypes" />
          <Tile label="TCGA / TARGET" value={n('tcga') + n('target')} hint="cancer types (TOIL)" />
          <Tile label="Normal tissues" value={n('gtex_toil') + n('gtex_tissue') + n('tcga_normal')} hint="GTEx, TCGA-adjacent" />
          <Tile label="Scored pairs" value="34 M" hint="gene × context" />
        </div>
        <h3>How the score is built</h3>
        <p className="small muted">Each component is scaled 0–1; the weighted mean is multiplied by <code className="inline">0.25 + 0.75 × S</code> so unselective genes cannot rank on expression alone. Weights are editable on every rankings page.</p>
        {data && <ComponentLegend weights={data.profiles.any_modality} />}
        {data && <div className="kv small" style={{ marginTop: 10 }}>{Object.entries(data.components).map(([k, v]) => <Fragment key={k}><div>{k}</div><div>{v as string}</div></Fragment>)}</div>}
        <h3>Data releases</h3>
        <div className="small muted">{data && Object.entries(data.releases).map(([s, f]) => <span key={s} className="badge outline" style={{ marginRight: 6, marginBottom: 6 }}>{s}: {Array.from(new Set(Object.values(f as any).filter(Boolean))).join(', ') || 'latest'}</span>)}</div>
        <div className="small faint" style={{ marginTop: 8 }}>{Object.entries(counts).map(([t, c]) => `${TYPE_LABELS[t] || t}: ${c}`).join(' · ')}</div>
      </div>
    </div>
  )
}
