import { useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { Link, useNavigate, useParams } from 'react-router-dom'
import { api, fmt } from '../api'
import DataTable, { Col } from '../components/DataTable'
import Plot from '../components/Plot'
import { Badge, Empty, Skeleton, Tile } from '../components/ui'
import { plotTheme } from '../theme'

export function DrugSearch({ big }: { big?: boolean }) {
  const [q, setQ] = useState(''); const nav = useNavigate()
  const { data } = useQuery({ queryKey: ['drug-search', q], queryFn: () => api.drugSearch(q), enabled: q.length >= 2 })
  const [focus, setFocus] = useState(false)
  return (
    <div className="picker" style={{ minWidth: big ? 0 : 260 }}>
      <input type="search" value={q} placeholder={big ? 'Search a compound, mechanism or target — e.g. lapatinib, PARP inhibitor, ERBB2' : 'Drug search'}
        style={big ? { width: '100%', fontSize: 16, padding: '12px 14px' } : { width: '100%' }}
        onFocus={() => setFocus(true)} onBlur={() => setTimeout(() => setFocus(false), 150)} onChange={e => setQ(e.target.value)}
        onKeyDown={e => { if (e.key === 'Enter' && data?.[0]) { nav(`/drug/${encodeURIComponent(data[0].broad_id)}`); setQ('') } }} />
      {focus && q.length >= 2 && data && data.length > 0 && (
        <div className="pop"><ul>{data.map(d => <li key={d.broad_id} className="item" onMouseDown={() => { nav(`/drug/${encodeURIComponent(d.broad_id)}`); setQ('') }}>
          <b>{d.name}</b><span className="t" style={{ marginLeft: 8 }}>{d.moa || ''}{d.targets ? ` · ${d.targets}` : ''}</span></li>)}</ul></div>)}
    </div>
  )
}

export default function Drug() {
  const { id = '' } = useParams()
  const { data, isLoading, error } = useQuery({ queryKey: ['drug', id], queryFn: () => api.drug(id) })
  const t = plotTheme()
  if (error) return <div className="error">{String(error)}</div>
  if (isLoading || !data) return <div className="card"><Skeleton rows={8} /></div>
  const c = data.compound; const lines = data.lines as any[]; const thr = data.sens_threshold_lfc
  const nSens = lines.filter(l => l.lfc < thr).length
  const cols: Col<any>[] = [
    { key: 'name', label: 'Cell line', render: r => <Link to={`/context/${r.context_id}`}>{r.name}</Link> },
    { key: 'lineage', label: 'Lineage' }, { key: 'primary_disease', label: 'Disease', render: r => <span className="small muted">{r.primary_disease}</span> },
    { key: 'lfc', label: 'log2 FC viability (2.5 µM)', num: true, render: r => <b style={{ color: r.lfc < thr ? 'var(--critical)' : undefined }}>{fmt(r.lfc)}</b> },
    { key: 'auc', label: 'AUC (dose-response)', num: true, render: r => fmt(r.auc) }, { key: 'ic50_um', label: 'IC50 µM', num: true, render: r => fmt(r.ic50_um) },
  ]
  const byLin = data.by_lineage as any[]
  return (
    <div className="stack">
      <div className="page-head"><div><h1>{c.name} <span className="muted" style={{ fontWeight: 400, fontSize: 15 }}>{c.broad_id}</span></h1>
        <div className="row center" style={{ gap: 6 }}>{c.moa && <Badge kind="type">{c.moa}</Badge>}<Badge kind="outline">{c.screen}{c.dose_um ? ` · ${c.dose_um} µM` : ''}</Badge>
          {data.targets.map((g: any) => <Link key={g.gene_id} to={`/gene/${g.symbol}`} className={`badge ${g.is_surface ? 'surface' : ''}`}>{g.symbol}</Link>)}</div></div></div>
      <div className="tiles">
        <Tile label="Lines screened" value={lines.length} hint="PRISM Repurposing 24Q2, 5-day, 2.5 µM" />
        <Tile label="Sensitive lines" value={nSens} hint={`log2 FC < ${thr} (≈ 50% viability)`} />
        <Tile label="Median log2 FC" value={fmt(c.median_lfc)} hint="across all screened lines" />
        <Tile label="Dose-response" value={c.n_lines_auc ?? 0} hint="lines with AUC / IC50 (19Q4 secondary)" />
      </div>
      <div className="grid2" style={{ gridTemplateColumns: '2fr 3fr' }}>
        <div className="card">
          <h2>Sensitivity by lineage</h2>
          {byLin.length === 0 ? <Empty title="No lineage data" /> : <Plot data={[{ type: 'bar', orientation: 'h', y: byLin.map(b => b.lineage), x: byLin.map(b => b.median_lfc), marker: { color: byLin.map(b => (b.median_lfc < thr ? t.s2 : t.s1)) },
            customdata: byLin.map(b => [b.n, b.frac_sensitive]), hovertemplate: '%{y}<br>median log2 FC %{x:.2f}<br>n=%{customdata[0]} · %{customdata[1]:.0%} sensitive<extra></extra>' }]}
            layout={{ height: Math.max(360, byLin.length * 20 + 70), margin: { l: 160, r: 20, t: 10, b: 50 }, xaxis: { title: { text: 'median log2 FC viability (2.5 µM)' }, zeroline: true, automargin: true }, yaxis: { autorange: 'reversed', tickfont: { size: 10 } }, shapes: [{ type: 'line', x0: thr, x1: thr, y0: -0.5, y1: byLin.length - 0.5, line: { color: t.s2, dash: 'dot', width: 1 } }] }} />}
          <p className="small faint">Orange = lineage median below the sensitivity threshold. Lineages with ≥ 3 screened lines.</p>
        </div>
        <div className="card">
          <h2>Cell lines</h2>
          <DataTable rows={lines} cols={cols} rowKey={r => r.context_id} defaultSort="lfc" defaultDesc={false} maxHeight={520} />
        </div>
      </div>
    </div>
  )
}
