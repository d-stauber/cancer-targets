import { useEffect, useMemo, useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { Link, useNavigate, useParams } from 'react-router-dom'
import { api, Context as Ctx, fmt, qs, TYPE_LABELS } from '../api'
import ContextPicker, { SHORT } from '../components/ContextPicker'
import DataTable, { Col } from '../components/DataTable'
import { Badge, COMP, COMP_COLOR, COMP_NAMES, ComponentLegend, Empty, ScoreStack, Seg, Tile } from '../components/ui'

const WEIGHT_PRESETS: Record<string, Record<string, number>> = {
  'Selectivity-first': { E: 0.2, S: 0.45, P: 0.1, T: 0.05, U: 0, R: 0.1, A: 0.1, D: 0 },
  'Novelty (ignore precedent)': { E: 0.35, S: 0.4, P: 0.15, T: 0.1, U: 0, R: 0, A: 0, D: 0 },
  'ADC / antibody': { E: 0.25, S: 0.3, P: 0.1, T: 0.1, U: 0.2, R: 0.05, A: 0, D: 0 },
  'Inhibitor / degrader (with dependency)': { E: 0.2, S: 0.25, P: 0.1, T: 0.05, U: 0, R: 0.15, A: 0.05, D: 0.2 },
}

export default function ContextPage() {
  const { id } = useParams(); const nav = useNavigate()
  const meta = useQuery({ queryKey: ['meta'], queryFn: api.meta })
  const all = useQuery({ queryKey: ['contexts-all'], queryFn: () => api.contexts() })
  const ctx = useMemo(() => all.data?.find(c => c.context_id === Number(id)) || null, [all.data, id])
  const [profile, setProfile] = useState<'any_modality' | 'surface'>('any_modality')
  const [w, setW] = useState<Record<string, number> | null>(null)
  const [surfaceOnly, setSurfaceOnly] = useState(false); const [minExpr, setMinExpr] = useState(0); const [minSel, setMinSel] = useState(0)
  const [exclEss, setExclEss] = useState(false); const [control, setControl] = useState<Ctx | null>(null); const [filter, setFilter] = useState(''); const [limit, setLimit] = useState(300)
  useEffect(() => { if (meta.data) setW({ ...meta.data.profiles[profile] }) }, [meta.data, profile])
  const [wOpen, setWOpen] = useState(false)
  const weights = w ? Object.entries(w).map(([k, v]) => `${k}:${v}`).join(',') : undefined
  const params = { profile, weights, surface_only: surfaceOnly, min_expr: minExpr, min_selectivity: minSel, exclude_essential: exclEss, control: control?.context_id, gene_filter: filter, limit }
  const { data, isFetching, error } = useQuery({ queryKey: ['targets', id, params], queryFn: () => api.targets(Number(id), params), enabled: !!id && !!w })
  const rows = data?.rows || []
  const isDefault = !!w && !!meta.data && JSON.stringify(w) === JSON.stringify(meta.data.profiles[profile])
  useEffect(() => { if (w && !isDefault) setWOpen(true) }, [isDefault])
  const matched = useMemo(() => all.data?.find(c => c.context_id === rows[0]?.matched_context_id) || null, [all.data, rows])
  const cols: Col<any>[] = [
    { key: 'rank', label: '#', num: true, width: 44 },
    { key: 'symbol', label: 'Gene', render: r => <><Link to={`/gene/${r.symbol}`}>{r.symbol}</Link><span className="gn">{(r.gene_name || '').slice(0, 34)}</span></> },
    { key: 'score', label: 'Score', num: true, render: r => <span className="score">{fmt(r.score, 3)}</span> },
    { key: 'stack', label: 'Breakdown', render: r => <ScoreStack r={r} weights={w || {}} />, sort: r => r.score },
    { key: 'x', label: 'Expr', num: true, render: r => fmt(r.x), title: 'quantile-normalised log2(TPM+1) in this context' },
    { key: 'x_control', label: control ? 'Control' : 'Matched', num: true, render: r => fmt(r.x_control), title: 'expression in the matched normal / control context' },
    { key: 'n_vital_max', label: 'Vital max', num: true, render: r => fmt(r.n_vital_max), title: 'highest expression in a vital normal tissue (TOIL GTEx)' },
    { key: 'S', label: 'S', num: true, render: r => fmt(r.S), title: COMP_NAMES.S },
    { key: 'E', label: 'E', num: true, render: r => fmt(r.E), title: COMP_NAMES.E },
    { key: 'P', label: 'P', num: true, render: r => fmt(r.P), title: COMP_NAMES.P },
    { key: 'U', label: 'U', num: true, render: r => fmt(r.U), title: COMP_NAMES.U },
    { key: 'R', label: 'R', num: true, render: r => fmt(r.R), title: COMP_NAMES.R },
    { key: 'A', label: 'A', num: true, render: r => fmt(r.A), title: COMP_NAMES.A },
    { key: 'D', label: 'D', num: true, render: r => fmt(r.D), title: COMP_NAMES.D },
    { key: 'flags', label: 'Flags', render: r => <>{r.is_surface && <Badge kind="surface">{r.U_tier}</Badge>} {r.max_phase ? <Badge kind="drug">ph {r.max_phase}</Badge> : null} {r.is_common_essential && <Badge kind="warn">essential</Badge>} {r.gate && <span className="gate">{r.gate.replace('_', ' ')}</span>}</>, sort: r => (r.max_phase || 0) },
  ]
  return (
    <div className="stack">
      <div className="page-head"><div><h1>Target rankings</h1><p className="sub">All protein-coding genes ranked as targets for one context, with an editable score breakdown.</p></div>
        {ctx && <a className="btn secondary" href={`/api/contexts/${ctx.context_id}/targets?${qs({ ...params, format: 'csv' })}`}>Download CSV</a>}</div>
      <div className="card">
        <div className="row">
          <ContextPicker label="Context" value={ctx} onChange={c => nav(`/context/${c.context_id}`)} types={['cell_line', 'lineage', 'primary_disease', 'subtype', 'tcga', 'target', 'custom']} autoFocus={!id} />
          <div className="field"><label className="lbl">Profile</label><Seg value={profile} onChange={setProfile} options={[{ value: 'any_modality', label: 'Any modality' }, { value: 'surface', label: 'Surface (Ab / ADC / CAR)' }]} /></div>
          <ContextPicker label="Matched control override" value={control} onChange={setControl} placeholder="default matched normal" types={['custom', 'normal_lines', 'cell_line', 'gtex_toil', 'gtex_tissue', 'tcga_normal', 'hpa_rna_tissue']} />
          {control && <button className="btn ghost" onClick={() => setControl(null)}>clear</button>}
        </div>
        <div className="row" style={{ marginTop: 10 }}>
          <label className="check"><input type="checkbox" checked={surfaceOnly} onChange={e => setSurfaceOnly(e.target.checked)} />Surface only</label>
          <label className="check"><input type="checkbox" checked={exclEss} onChange={e => setExclEss(e.target.checked)} />Exclude common-essential</label>
          <div className="field"><label className="lbl">Min expression</label><input type="number" step="0.5" value={minExpr} style={{ width: 80 }} onChange={e => setMinExpr(+e.target.value)} /></div>
          <div className="field"><label className="lbl">Min selectivity S</label><input type="number" step="0.1" min="0" max="1" value={minSel} style={{ width: 80 }} onChange={e => setMinSel(+e.target.value)} /></div>
          <div className="field"><label className="lbl">Gene filter</label><input type="text" value={filter} onChange={e => setFilter(e.target.value)} style={{ width: 130 }} placeholder="e.g. CLDN" /></div>
          <div className="field"><label className="lbl">Rows</label><select value={limit} onChange={e => setLimit(+e.target.value)}><option>100</option><option>300</option><option>1000</option><option>3000</option></select></div>
        </div>
        <details className="panel" style={{ marginTop: 12 }} open={wOpen} onToggle={e => setWOpen((e.target as HTMLDetailsElement).open)}>
          <summary>Weights {isDefault ? <span className="faint small">(defaults)</span> : <Badge kind="type">custom</Badge>}</summary>
          {w && <div style={{ marginTop: 10 }}>
            <div className="sliders">{COMP.map(c => (
              <div key={c} className="slider"><div className="top"><b><i className="bar" style={{ width: 10, height: 10, background: COMP_COLOR[c], marginRight: 6 }} />{c} {COMP_NAMES[c]}</b><span>{(w[c] ?? 0).toFixed(2)}</span></div>
                <input type="range" min="0" max="1" step="0.05" value={w[c] ?? 0} onChange={e => setW({ ...w, [c]: +e.target.value })} /></div>))}</div>
            <div className="row center" style={{ marginTop: 10 }}><span className="small faint">Presets:</span><div className="chips">
              <button className="chip" onClick={() => setW({ ...meta.data.profiles[profile] })}>Defaults</button>
              {Object.entries(WEIGHT_PRESETS).map(([k, v]) => <button key={k} className="chip" onClick={() => setW({ ...v })}>{k}</button>)}</div></div>
          </div>}
        </details>
      </div>
      {!ctx && <div className="card"><Empty title="Choose a context">Any DepMap cell line, lineage, primary disease or subtype, or a TCGA / TARGET cancer type.</Empty></div>}
      {error && <div className="error">{String(error)}</div>}
      {ctx && (
        <div className="card">
          <div className="tiles" style={{ marginBottom: 12 }}>
            <Tile label="Context" value={ctx.name} hint={<>{TYPE_LABELS[ctx.context_type]}{ctx.lineage && ctx.lineage !== ctx.name ? ` · ${ctx.lineage}` : ''}{ctx.primary_disease && ctx.primary_disease !== ctx.name ? ` · ${ctx.primary_disease}` : ''}</>} />
            <Tile label="Members" value={ctx.n_members.toLocaleString()} hint={ctx.n_members > 1 ? 'samples / lines aggregated' : 'single cell line'} />
            <Tile label="Matched normal" value={control ? control.name : matched ? matched.name : (ctx.gtex_toil_site || '–')} hint={control ? 'override' : matched ? SHORT[matched.context_type] : ''} />
            <Tile label="OT disease" value={(ctx.disease_names || '–').split('|')[0]} hint="association component A" />
            <Tile label="Genes scored" value={data ? data.total.toLocaleString() : '–'} hint={isFetching ? 'updating…' : data && data.matching !== data.total ? `${data.matching.toLocaleString()} match filters · ${rows.length} shown` : `${rows.length} shown`} />
          </div>
          <ComponentLegend weights={w || undefined} />
          <div style={{ marginTop: 10 }}><DataTable rows={rows} cols={cols} rowKey={r => r.gene_id} defaultSort="score" loading={isFetching} pageSize={150} /></div>
        </div>
      )}
    </div>
  )
}
