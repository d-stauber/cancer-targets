import { useEffect, useMemo, useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { Link, useSearchParams } from 'react-router-dom'
import { api, Context, fmt, qs } from '../api'
import ContextPicker from '../components/ContextPicker'
import DataTable, { Col } from '../components/DataTable'
import Plot from '../components/Plot'
import { Badge, Empty, Seg } from '../components/ui'
import { plotTheme } from '../theme'

type Row = { symbol: string; x: number; y: number; lfc: number; is_surface: boolean; U_tier: string; max_phase: number | null }
const PRESETS: { label: string; x: [string, string]; y: [string, string] }[] = [
  { label: 'BT-474 vs HMEL (immortalised breast epithelium)', x: ['cell_line', 'BT-474'], y: ['cell_line', 'HMEL'] },
  { label: 'BT-474 vs GTEx breast', x: ['cell_line', 'BT-474'], y: ['gtex_toil', 'GTEx (TOIL): Breast'] },
  { label: 'MDA-MB-231 vs HMEL', x: ['cell_line', 'MDA-MB-231'], y: ['cell_line', 'HMEL'] },
  { label: 'HER2+ breast lines vs GTEx breast', x: ['subtype', 'Breast Invasive Ductal Carcinoma'], y: ['gtex_toil', 'GTEx (TOIL): Breast'] },
  { label: 'TCGA breast vs adjacent normal', x: ['tcga', 'Breast Invasive Carcinoma'], y: ['tcga_normal', 'TCGA normal: Breast'] },
  { label: 'TCGA lung adeno vs GTEx lung', x: ['tcga', 'Lung Adenocarcinoma'], y: ['gtex_toil', 'GTEx (TOIL): Lung'] },
]

export default function Explorer() {
  const [sp, setSp] = useSearchParams()
  const all = useQuery({ queryKey: ['contexts-all'], queryFn: () => api.contexts() })
  const byId = (id: string | null) => all.data?.find(c => String(c.context_id) === id) || null
  const x = byId(sp.get('x')), y = byId(sp.get('y'))
  const setX = (c: Context) => setSp(p => { p.set('x', String(c.context_id)); return p })
  const setY = (c: Context) => setSp(p => { p.set('y', String(c.context_id)); return p })
  const [stat, setStat] = useState('qn'); const [surfaceOnly, setSurfaceOnly] = useState(false); const [minExpr, setMinExpr] = useState(1)
  const [highlight, setHighlight] = useState(''); const [dir, setDir] = useState<'x' | 'y'>('x'); const [sel, setSel] = useState<Row | null>(null)
  const ready = !!x && !!y
  const params = { x: x?.context_id, y: y?.context_id, stat, surface_only: surfaceOnly, min_expr: minExpr }
  const { data, isFetching, error } = useQuery({ queryKey: ['scatter', params], queryFn: () => api.scatter(params), enabled: ready })
  const hl = useMemo(() => new Set(highlight.toUpperCase().split(/[\s,]+/).filter(Boolean)), [highlight])
  const rows: Row[] = useMemo(() => {
    if (!data) return []
    const d = data.data
    return d.symbol.map((s: string, i: number) => ({ symbol: s, x: d.x[i], y: d.y[i], lfc: d.lfc[i], is_surface: d.is_surface[i], U_tier: d.U_tier[i], max_phase: d.max_phase[i] }))
  }, [data])
  useEffect(() => { setSel(null) }, [data])
  const t = plotTheme()
  const traces = useMemo(() => {
    if (!data) return []
    const d = data.data
    const surf = d.is_surface.map((s: boolean, i: number) => (s ? i : -1)).filter((i: number) => i >= 0)
    const other = d.is_surface.map((s: boolean, i: number) => (s ? -1 : i)).filter((i: number) => i >= 0)
    const mk = (idx: number[], name: string, color: string, size: number) => ({ x: idx.map(i => d.x[i]), y: idx.map(i => d.y[i]), text: idx.map(i => d.symbol[i]), customdata: idx.map(i => d.lfc[i]),
      mode: 'markers', type: 'scattergl', name, marker: { size, color, opacity: 0.65, line: { width: 0 } }, hovertemplate: '<b>%{text}</b><br>x %{x:.2f} · y %{y:.2f}<br>log2 FC %{customdata:.2f}<extra></extra>' })
    const tr: any[] = [mk(other, 'other genes', t.neutral, 5), mk(surf, 'surface-accessible (U ≥ 0.6)', t.s1, 6)]
    if (hl.size) {
      const idx = d.symbol.map((s: string, i: number) => (hl.has(s.toUpperCase()) ? i : -1)).filter((i: number) => i >= 0)
      tr.push({ ...mk(idx, 'highlighted', t.s2, 12), type: 'scatter', mode: 'markers+text', textposition: 'top center', textfont: { color: t.textStrong, size: 12 }, marker: { size: 12, color: t.s2, line: { width: 2, color: t.paper } } })
    }
    if (sel) tr.push({ x: [sel.x], y: [sel.y], text: [sel.symbol], mode: 'markers+text', type: 'scatter', name: 'selected', textposition: 'top center', textfont: { color: t.textStrong, size: 12 }, marker: { size: 13, color: t.s2, symbol: 'circle-open', line: { width: 3, color: t.s2 } }, hoverinfo: 'skip' })
    const m = Math.max(...d.x, ...d.y, 1)
    tr.push({ x: [0, m], y: [0, m], mode: 'lines', type: 'scatter', line: { color: t.axis, dash: 'dot', width: 1 }, hoverinfo: 'skip', showlegend: false })
    return tr
  }, [data, hl, sel, t.paper])
  const missing = useMemo(() => { if (!data || !hl.size) return []; const have = new Set(data.data.symbol.map((s: string) => s.toUpperCase())); return [...hl].filter(g => !have.has(g)) }, [data, hl])
  const unit = stat === 'qn' ? 'quantile-normalised log2(TPM+1)' : stat === 'pct_rank' ? 'percentile rank in context' : stat === 'frac_expr' ? 'fraction of samples expressing' : 'log2(TPM+1)'
  const sortedRows = useMemo(() => [...rows].sort((a, b) => (dir === 'x' ? b.lfc - a.lfc : a.lfc - b.lfc)), [rows, dir])
  const cols: Col<Row>[] = [
    { key: 'rank', label: '#', render: (_r, i) => i + 1, width: 40 },
    { key: 'symbol', label: 'Gene', render: r => <Link to={`/gene/${r.symbol}`}>{r.symbol}</Link> },
    { key: 'x', label: x?.name.slice(0, 18) || 'X', num: true, render: r => fmt(r.x), title: x?.name },
    { key: 'y', label: y?.name.slice(0, 18) || 'Y', num: true, render: r => fmt(r.y), title: y?.name },
    { key: 'lfc', label: 'log2 FC', num: true, render: r => <b>{fmt(r.lfc)}</b> },
    { key: 'is_surface', label: 'Surface', render: r => r.is_surface ? <Badge kind="surface">{r.U_tier}</Badge> : null, sort: r => (r.is_surface ? 1 : 0) },
    { key: 'max_phase', label: 'Drugs', render: r => r.max_phase ? <Badge kind="drug">phase {r.max_phase}</Badge> : null },
  ]
  const find = (t: [string, string]) => all.data?.find(c => c.context_type === t[0] && c.name === t[1])
  const presets = useMemo(() => PRESETS.filter(p => find(p.x) && find(p.y)), [all.data])
  const applyPreset = (p: typeof PRESETS[number]) => { const fx = find(p.x), fy = find(p.y); if (fx && fy) setSp({ x: String(fx.context_id), y: String(fy.context_id) }) }
  return (
    <div className="stack">
      <div className="page-head"><div><h1>Expression explorer</h1><p className="sub">Compare two contexts gene by gene. Click a point or row to inspect a gene.</p></div></div>
      <div className="card">
        <div className="row">
          <ContextPicker label="X axis" value={x} onChange={setX} />
          <button className="btn secondary" title="Swap axes" style={{ alignSelf: 'flex-end' }} disabled={!ready} onClick={() => setSp({ x: String(y!.context_id), y: String(x!.context_id) })}>⇄</button>
          <ContextPicker label="Y axis" value={y} onChange={setY} />
          <div className="field"><label className="lbl">Statistic</label>
            <select value={stat} onChange={e => setStat(e.target.value)}>
              <option value="qn">Quantile-normalised log2(TPM+1)</option><option value="median">Raw median log2(TPM+1)</option><option value="p90">90th percentile</option>
              <option value="pct_rank">Percentile rank in context</option><option value="frac_expr">Fraction of samples expressing</option>
            </select></div>
          <div className="field"><label className="lbl">Min expression</label><input type="number" step="0.5" value={minExpr} style={{ width: 80 }} onChange={e => setMinExpr(+e.target.value)} /></div>
          <label className="check"><input type="checkbox" checked={surfaceOnly} onChange={e => setSurfaceOnly(e.target.checked)} />Surface only</label>
          <div className="field" style={{ flex: 1, minWidth: 200 }}><label className="lbl">Highlight genes</label><input type="text" value={highlight} onChange={e => setHighlight(e.target.value)} placeholder="ERBB2 GRB7 TACSTD2" /></div>
        </div>
        {missing.length > 0 && <p className="small" style={{ marginTop: 8, color: 'var(--serious)' }}>Not in this plot (unknown symbol or below the minimum expression on both axes): {missing.join(', ')}</p>}
        <div className="row center" style={{ marginTop: 10 }}><span className="small faint">Presets:</span><div className="chips">{presets.map(p => <button key={p.label} className="chip" onClick={() => applyPreset(p)}>{p.label}</button>)}</div></div>
        {ready && x!.source !== y!.source && stat === 'median' && <p className="small muted" style={{ marginTop: 8 }}>These contexts come from different RNA-seq pipelines; raw values are only approximately comparable. The quantile-normalised statistic is recommended.</p>}
      </div>
      {!ready && <div className="card"><Empty title="Pick two contexts to compare">Any DepMap cell line, lineage or subtype, non-cancerous line group, TCGA/TARGET cancer type, TCGA adjacent normal, GTEx tissue, or a custom upload. Try a preset above.</Empty></div>}
      {error && <div className="error">{String(error)}</div>}
      {ready && (
        <div className="grid-explorer">
          <div className="card">
            <div className="card-head"><h2>{x!.name} vs {y!.name}</h2><span className="small faint">{isFetching ? <span className="spin" /> : `${data?.n.toLocaleString() ?? ''} genes`}</span></div>
            {data && <Plot data={traces} onClick={(e: any) => { const p = e.points?.[0]; if (p?.text) setSel(rows.find(r => r.symbol === p.text) || null) }}
              layout={{ height: 600, hovermode: 'closest', legend: { orientation: 'h', y: 1.06, x: 0, font: { size: 11 } }, dragmode: 'pan',
                xaxis: { title: { text: `${x!.name} · ${unit}` } }, yaxis: { title: { text: `${y!.name} · ${unit}` } } }} config={{ scrollZoom: true }} />}
            {sel && <div className="row center" style={{ marginTop: 8, padding: '8px 10px', background: 'var(--surface-2)', borderRadius: 6 }}>
              <b>{sel.symbol}</b><span className="small muted">x {fmt(sel.x)} · y {fmt(sel.y)} · log2 FC {fmt(sel.lfc)}</span>{sel.is_surface && <Badge kind="surface">{sel.U_tier}</Badge>}{sel.max_phase ? <Badge kind="drug">phase {sel.max_phase}</Badge> : null}
              <Link to={`/gene/${sel.symbol}`} className="btn sm" style={{ marginLeft: 'auto' }}>Open gene page →</Link></div>}
            <p className="small faint" style={{ marginTop: 6 }}>Dotted line = equal expression. Scroll to zoom, drag to pan, double-click to reset.</p>
          </div>
          <div className="card">
            <div className="card-head"><h2>Differential ranking</h2>
              <div className="row center"><Seg value={dir} onChange={setDir} options={[{ value: 'x', label: `↑ in ${x!.name.slice(0, 14)}` }, { value: 'y', label: `↑ in ${y!.name.slice(0, 14)}` }]} />
                <a className="btn secondary sm" href={`/api/explorer/ranking?${qs({ x: x!.context_id, y: y!.context_id, sort: dir === 'x' ? 'lfc' : '-lfc', surface_only: surfaceOnly, min_expr: minExpr, format: 'csv' })}`}>CSV</a></div></div>
            <DataTable rows={sortedRows} cols={cols} rowKey={r => r.symbol} maxHeight={580} loading={isFetching} highlight={r => hl.has(r.symbol.toUpperCase()) || sel?.symbol === r.symbol} onRowClick={r => setSel(r)} />
          </div>
        </div>
      )}
    </div>
  )
}
