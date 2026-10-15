import { useEffect, useMemo, useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { Link } from 'react-router-dom'
import { api, Context, fmt, qs } from '../api'
import DataTable, { Col } from '../components/DataTable'
import Plot from '../components/Plot'
import { Badge, Empty, Seg } from '../components/ui'
import { plotTheme } from '../theme'

type Row = { broad_id: string; name: string; moa: string | null; targets: string | null; x: number; y: number; delta: number; n_x: number; n_y: number; median_lfc: number | null; frac_sensitive: number | null }
const SENS = -1

/** Scatter of per-compound drug sensitivity in context X vs Y (PRISM). Reuses the explorer layout. */
export default function DrugExplorer({ x, y }: { x: Context | null; y: Context | null }) {
  const [metric, setMetric] = useState<'lfc' | 'auc'>('lfc')
  const [highlight, setHighlight] = useState('')
  const [dir, setDir] = useState<'x' | 'y'>('x')
  const [sel, setSel] = useState<Row | null>(null)
  const ready = !!x && !!y
  const params = { x: x?.context_id, y: y?.context_id, metric }
  const { data, isFetching, error } = useQuery({ queryKey: ['drug-scatter', params], queryFn: () => api.drugScatter(params), enabled: ready })
  useEffect(() => { setSel(null) }, [data])
  const rows: Row[] = useMemo(() => {
    if (!data) return []
    const d = data.data
    return d.name.map((_: string, i: number) => ({ broad_id: d.broad_id[i], name: d.name[i], moa: d.moa[i], targets: d.targets[i], x: d.x[i], y: d.y[i], delta: d.delta[i], n_x: d.n_x[i], n_y: d.n_y[i], median_lfc: d.median_lfc[i], frac_sensitive: d.frac_sensitive[i] }))
  }, [data])
  const terms = useMemo(() => highlight.toUpperCase().split(/[,;]+|\s{2,}|\s(?=[A-Z0-9-]+$)/).map(t => t.trim()).filter(Boolean), [highlight])
  const matches = (r: Row) => terms.length > 0 && terms.some(t => r.name.toUpperCase().includes(t) || (r.targets || '').toUpperCase().split(', ').includes(t) || (r.moa || '').toUpperCase().includes(t))
  const t = plotTheme()
  const traces = useMemo(() => {
    if (!rows.length) return []
    const hover = (r: Row) => `<b>${r.name}</b><br>${(r.moa || '').toLowerCase()}${r.targets ? ' · ' + r.targets : ''}<br>x ${fmt(r.x)} · y ${fmt(r.y)} · Δ ${fmt(r.delta)}`
    const base = rows.filter(r => !matches(r)); const hl = rows.filter(matches)
    const mk = (rs: Row[], name: string, color: string, size: number, extra: any = {}) => ({ x: rs.map(r => r.x), y: rs.map(r => r.y), text: rs.map(hover), customdata: rs.map(r => r.broad_id),
      mode: 'markers', type: 'scattergl', name, marker: { size, color, opacity: 0.65, line: { width: 0 } }, hovertemplate: '%{text}<extra></extra>', ...extra })
    const tr: any[] = [mk(base, 'compounds', t.s1, 5)]
    // direct labels only when few are highlighted; otherwise rely on hover (selective labelling)
    if (hl.length) tr.push({ ...mk(hl, `highlighted (${hl.length})`, t.s2, 10), type: 'scatter', mode: hl.length <= 12 ? 'markers+text' : 'markers', text: hl.map(r => r.name), hovertext: hl.map(hover), hovertemplate: '%{hovertext}<extra></extra>', textposition: 'top center', textfont: { size: 11, color: t.textStrong }, marker: { size: 10, color: t.s2, line: { width: 2, color: t.paper } } })
    if (sel) tr.push({ x: [sel.x], y: [sel.y], text: [sel.name], mode: 'markers+text', type: 'scatter', name: 'selected', textposition: 'top center', textfont: { size: 12, color: t.textStrong }, marker: { size: 13, color: t.s2, symbol: 'circle-open', line: { width: 3, color: t.s2 } }, hoverinfo: 'skip' })
    const lo = Math.min(...rows.map(r => Math.min(r.x, r.y))), hi = Math.max(...rows.map(r => Math.max(r.x, r.y)))
    tr.push({ x: [lo, hi], y: [lo, hi], mode: 'lines', type: 'scatter', line: { color: t.axis, dash: 'dot', width: 1 }, hoverinfo: 'skip', showlegend: false })
    return tr
  }, [rows, terms, sel, t.paper])
  const unit = metric === 'lfc' ? 'log2 FC viability at 2.5 µM' : 'dose-response AUC'
  const shapes = metric === 'lfc' ? [{ type: 'line', x0: SENS, x1: SENS, yref: 'paper', y0: 0, y1: 1, line: { color: t.s2, dash: 'dot', width: 1 } }, { type: 'line', y0: SENS, y1: SENS, xref: 'paper', x0: 0, x1: 1, line: { color: t.s2, dash: 'dot', width: 1 } }] : []
  const sorted = useMemo(() => [...rows].sort((a, b) => (dir === 'x' ? a.delta - b.delta : b.delta - a.delta)), [rows, dir])
  // default axis range trimmed to the 0.5th-99.5th percentile so a handful of extreme cytotoxic values don't squash the plot (zoom/double-click to see all)
  const range = useMemo(() => {
    if (!rows.length) return undefined
    const v = rows.flatMap(r => [r.x, r.y]).filter(Number.isFinite).sort((a, b) => a - b)
    const lo = v[Math.floor(v.length * 0.005)], hi = v[Math.ceil(v.length * 0.995) - 1]
    const pad = (hi - lo) * 0.05; return [lo - pad, hi + pad]
  }, [rows])
  const cols: Col<Row>[] = [
    { key: 'rank', label: '#', render: (_r, i) => i + 1, width: 40 },
    { key: 'name', label: 'Compound', render: r => <><Link to={`/drug/${encodeURIComponent(r.broad_id)}`}>{r.name}</Link> <span className="gn small muted">{(r.moa || '').toLowerCase()}</span></> },
    { key: 'targets', label: 'Targets', render: r => <span className="small">{(r.targets || '').split(', ').filter(Boolean).slice(0, 3).map((g, i) => <Link key={i} to={`/gene/${g}`} style={{ marginRight: 5 }}>{g}</Link>)}</span> },
    { key: 'x', label: x?.name.slice(0, 16) || 'X', num: true, render: r => <span style={{ color: metric === 'lfc' && r.x < SENS ? 'var(--critical)' : undefined }}>{fmt(r.x)}</span>, title: x?.name },
    { key: 'y', label: y?.name.slice(0, 16) || 'Y', num: true, render: r => <span style={{ color: metric === 'lfc' && r.y < SENS ? 'var(--critical)' : undefined }}>{fmt(r.y)}</span>, title: y?.name },
    { key: 'delta', label: 'Δ (X − Y)', num: true, render: r => <b>{fmt(r.delta)}</b>, title: 'negative = more sensitive in X' },
    { key: 'frac_sensitive', label: '% all lines', num: true, render: r => r.frac_sensitive == null ? '–' : `${(r.frac_sensitive * 100).toFixed(0)}%`, title: 'fraction of all screened lines sensitive (pan-cytotoxicity)' },
  ]
  return (
    <>
      <div className="card">
        <div className="row">
          <div className="field"><label className="lbl">Metric</label><Seg value={metric} onChange={setMetric} options={[{ value: 'lfc', label: 'log2 FC viability (2.5 µM, 6.8k compounds)' }, { value: 'auc', label: 'Dose-response AUC (1.4k compounds)' }]} /></div>
          <div className="field" style={{ flex: 1, minWidth: 240 }}><label className="lbl">Highlight compounds, targets or mechanisms (comma-separated)</label><input type="text" value={highlight} onChange={e => setHighlight(e.target.value)} placeholder="lapatinib, ERBB2, PARP inhibitor" /></div>
        </div>
        {ready && data && (data.n_lines_x === 0 || data.n_lines_y === 0) && <p className="small" style={{ marginTop: 8, color: 'var(--serious)' }}>{data.n_lines_x === 0 ? x!.name : y!.name} has no PRISM-screened lines.</p>}
      </div>
      {!ready && <div className="card"><Empty title="Pick two contexts to compare">Drug sensitivity is available for 914 DepMap cell lines and for lineages, diseases and subtypes (median over their screened lines).</Empty></div>}
      {error && <div className="error">{String(error)}</div>}
      {ready && (
        <div className="grid-explorer">
          <div className="card">
            <div className="card-head"><h2>{x!.name} vs {y!.name}</h2><span className="small faint">{isFetching ? <span className="spin" /> : data ? `${data.n.toLocaleString()} compounds · ${data.n_lines_x} vs ${data.n_lines_y} screened lines` : ''}</span></div>
            {data && <Plot data={traces} onClick={(e: any) => { const p = e.points?.[0]; const id = p?.customdata; setSel(rows.find(r => r.broad_id === id) || null) }}
              layout={{ height: 600, hovermode: 'closest', legend: { orientation: 'h', y: 1.06, x: 0, font: { size: 11 } }, dragmode: 'pan', shapes,
                xaxis: { title: { text: `${x!.name} · ${unit}` }, range }, yaxis: { title: { text: `${y!.name} · ${unit}` }, range } }} config={{ scrollZoom: true }} />}
            {sel && <div className="row center" style={{ marginTop: 8, padding: '8px 10px', background: 'var(--surface-2)', borderRadius: 6 }}>
              <b>{sel.name}</b>{sel.moa && <Badge kind="type">{sel.moa.toLowerCase()}</Badge>}<span className="small muted">x {fmt(sel.x)} · y {fmt(sel.y)} · Δ {fmt(sel.delta)}{sel.targets ? ` · ${sel.targets}` : ''}</span>
              <Link to={`/drug/${encodeURIComponent(sel.broad_id)}`} className="btn sm" style={{ marginLeft: 'auto' }}>Open drug page →</Link></div>}
            <p className="small faint" style={{ marginTop: 6 }}>Dotted diagonal = equal effect; {metric === 'lfc' ? 'orange dotted lines mark the sensitivity threshold (log2 FC −1). Points below/left are sensitive in that context.' : 'lower AUC = more sensitive.'} Scroll to zoom, drag to pan, click a point to inspect.</p>
          </div>
          <div className="card">
            <div className="card-head"><h2>Differential sensitivity</h2>
              <div className="row center"><Seg value={dir} onChange={setDir} options={[{ value: 'x', label: `more sensitive in ${x!.name.slice(0, 12)}` }, { value: 'y', label: `more sensitive in ${y!.name.slice(0, 12)}` }]} />
                <a className="btn secondary sm" href={`/api/explorer/drugs/ranking?${qs({ x: x!.context_id, y: y!.context_id, metric, sort: dir === 'x' ? 'delta' : '-delta', format: 'csv' })}`}>CSV</a></div></div>
            <DataTable rows={sorted} cols={cols} rowKey={r => r.broad_id} maxHeight={580} loading={isFetching} highlight={r => matches(r) || sel?.broad_id === r.broad_id} onRowClick={r => setSel(r)} />
          </div>
        </div>
      )}
    </>
  )
}
