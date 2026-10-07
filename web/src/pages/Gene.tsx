import { useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { Link, useParams } from 'react-router-dom'
import { api, fmt, TYPE_LABELS } from '../api'
import Plot from '../components/Plot'
import DataTable, { Col } from '../components/DataTable'
import { Badge, ComponentLegend, Expandable, ScoreStack, Seg, Skeleton, Tile } from '../components/ui'
import { SHORT } from '../components/ContextPicker'
import { plotTheme } from '../theme'

const LEVEL = ['not detected', 'low', 'medium', 'high']
const short = (n: string) => n.replace(/^(GTEx \(TOIL\): |TCGA normal: |GTEx v10: |HPA RNA: |Non-cancerous lines: |TARGET )/, '').replace(/ \(all lines\)$/, '')
function median(a: number[]) { const s = [...a].sort((x, y) => x - y); return s.length ? s[Math.floor(s.length / 2)] : 0 }

function ExprPlot({ symbol, source, title }: { symbol: string; source: string; title: string }) {
  const { data } = useQuery({ queryKey: ['expr', symbol, source], queryFn: () => api.geneExpr(symbol, source) })
  const t = plotTheme()
  if (!data) return <Skeleton rows={5} />
  const rows = data.rows as any[]
  const common = { title: { text: title, font: { size: 13, color: t.textStrong }, x: 0 }, height: 400, margin: { l: 48, r: 10, t: 34, b: 140 }, showlegend: true,
    legend: { orientation: 'h', y: 1.12, x: 1, xanchor: 'right', font: { size: 11 } }, yaxis: { title: { text: 'log2(TPM+1)' } }, xaxis: { tickangle: -50, tickfont: { size: 10 }, automargin: true } }
  if (source === 'cell_lines') {
    const byLin: Record<string, any[]> = {}
    rows.forEach(r => { const k = r.is_normal ? `Normal: ${r.lineage}` : r.lineage || 'Other'; (byLin[k] ||= []).push(r) })
    const order = Object.entries(byLin).sort((a, b) => median(b[1].map(r => r.value)) - median(a[1].map(r => r.value)))
    const mk = (normal: boolean) => ({ type: 'box', name: normal ? 'non-cancerous lines' : 'cancer lines', legendgroup: normal ? 'n' : 'c',
      x: order.filter(([k]) => k.startsWith('Normal') === normal).flatMap(([k, v]) => v.map(() => k)), y: order.filter(([k]) => k.startsWith('Normal') === normal).flatMap(([, v]) => v.map(r => r.value)),
      text: order.filter(([k]) => k.startsWith('Normal') === normal).flatMap(([, v]) => v.map(r => r.name)), boxpoints: 'all', jitter: 0.5, pointpos: 0,
      marker: { size: 3, color: normal ? t.s3 : t.s1, opacity: 0.6 }, line: { width: 1, color: normal ? t.s3 : t.s1 }, fillcolor: 'rgba(0,0,0,0)', hovertemplate: '%{text}: %{y:.2f}<extra></extra>' })
    return <Plot data={[mk(false), mk(true)]} layout={{ ...common, boxmode: 'overlay', xaxis: { ...common.xaxis, categoryorder: 'array', categoryarray: order.map(([k]) => k) } }} />
  }
  const sorted = [...rows].sort((a, b) => b.median - a.median)
  const hasBox = sorted.some(r => r.n > 1)
  const mk = (normal: boolean) => {
    const s = sorted.filter(r => !!r.is_normal === normal)
    const base = { name: normal ? 'normal' : 'tumor', x: s.map(r => short(r.name)), customdata: s.map(r => r.name), marker: { color: normal ? t.s3 : t.s1 }, line: { width: 1, color: normal ? t.s3 : t.s1 } }
    return hasBox ? { ...base, type: 'box', q1: s.map(r => r.q25), median: s.map(r => r.median), q3: s.map(r => r.q75), lowerfence: s.map(r => Math.max(0, r.q25 - 1.5 * (r.q75 - r.q25))), upperfence: s.map(r => r.max), fillcolor: 'rgba(0,0,0,0)', text: s.map(r => `n=${r.n}`), hovertemplate: '%{customdata}<br>median %{median:.2f} · %{text}<extra></extra>' }
      : { ...base, type: 'bar', y: s.map(r => r.median), hovertemplate: '%{customdata}: %{y:.2f}<extra></extra>', marker: { color: normal ? t.s3 : t.s1, cornerradius: 3 } }
  }
  const traces = [mk(false), mk(true)].filter(tr => (tr as any).x.length)
  return <Plot data={traces} layout={{ ...common, showlegend: traces.length > 1, xaxis: { ...common.xaxis, categoryorder: 'array', categoryarray: sorted.map(r => short(r.name)) }, bargap: 0.3 }} />
}

export default function Gene() {
  const { symbol = '' } = useParams()
  const { data, error, isLoading } = useQuery({ queryKey: ['gene', symbol], queryFn: () => api.gene(symbol) })
  const meta = useQuery({ queryKey: ['meta'], queryFn: api.meta })
  const [profile, setProfile] = useState<'any_modality' | 'surface'>('any_modality')
  const [types, setTypes] = useState('cell_line,lineage,primary_disease,subtype,tcga,target')
  const rk = useQuery({ queryKey: ['rank', symbol, profile, types], queryFn: () => api.geneRank(symbol, { profile, min_pct: 0, limit: 80, types }) })
  const rs = useQuery({ queryKey: ['rank-summary', symbol, profile, types], queryFn: () => api.geneRankSummary(symbol, { profile, types }) })
  const weights = meta.data?.profiles[profile] || {}
  const best = rk.data?.rows?.[0]
  if (error) return <div className="error">{String(error)}</div>
  if (isLoading || !data) return <div className="card"><Skeleton rows={8} /></div>
  const g = data.gene, st = data.static || {}, u = data.uniprot || {}, ot = data.opentargets || {}
  const cols: Col<any>[] = [
    { key: 'name', label: 'Context', render: r => <><Link to={`/context/${r.context_id}`}>{r.name}</Link> <Badge kind="type">{SHORT[r.context_type]}</Badge></> },
    { key: 'rank', label: 'Rank', num: true },
    { key: 'pct', label: 'Pctl', num: true, render: r => fmt(r.pct, 1) },
    { key: 'score', label: 'Score', num: true, render: r => <span className="score">{fmt(r.score, 3)}</span> },
    { key: 'stack', label: 'Breakdown', render: r => <ScoreStack r={r} weights={weights} width={130} /> },
    { key: 'x', label: 'Expr', num: true, render: r => fmt(r.x), title: 'quantile-normalised log2(TPM+1)' },
    { key: 'S', label: 'S', num: true, render: r => fmt(r.S), title: 'selectivity' },
    { key: 'gate', label: '', render: r => r.gate ? <span className="gate">{r.gate.replace('_', ' ')}</span> : null },
  ]
  return (
    <div className="stack">
      <div className="page-head">
        <div>
          <h1>{g.symbol} <span className="muted" style={{ fontWeight: 400, fontSize: 17 }}>{g.name}</span></h1>
          <div className="row center" style={{ gap: 6 }}>
            {st.is_surface ? <Badge kind="surface">surface · {st.U_tier}</Badge> : <Badge>{st.U_tier || 'localization unknown'}</Badge>}
            {st.is_secreted && <Badge>secreted</Badge>}
            {st.max_phase ? <Badge kind="drug">clinical phase {st.max_phase} · {st.n_known_drugs} drugs</Badge> : <Badge kind="outline">no known drugs</Badge>}
            {st.is_common_essential && <Badge kind="warn">common essential</Badge>}
            {st.n_safety_events > 0 && <Badge kind="warn">{st.n_safety_events} safety events (OT)</Badge>}
            {ot.ot_isCancerDriverGene ? <Badge kind="outline">cancer driver</Badge> : null}
            {st.dark_surfaceome && <Badge kind="outline">dark surfaceome atlas</Badge>}
          </div>
        </div>
        <div className="row"><Link className="btn secondary" to={`/explorer`}>Compare contexts</Link></div>
      </div>
      <div className="tiles">
        <Tile label="Best context" value={best ? best.name : '–'} hint={best ? `rank ${best.rank} · ${fmt(best.pct, 1)}th pctl` : ''} />
        <Tile label="Contexts ≥ 95th pctl" value={rs.data ? rs.data.n_ge95.toLocaleString() : '–'} hint={rs.data ? `of ${rs.data.n_contexts.toLocaleString()} · top-10 in ${rs.data.n_top10}` : ''} />
        <Tile label="Surface score U" value={fmt(st.U)} hint={st.U_tier} />
        <Tile label="Tractability R" value={fmt(st.R)} hint={`antibody ${fmt(st.R_ab)} · small mol. ${fmt(st.R_sm)}`} />
        <Tile label="Normal-tissue max" value={fmt(st.n_vital_max_toil)} hint={`vital tissue · ref ${fmt(st.n_ref_toil)} (${(st.n_ref_tissue_toil || '').replace(/_/g, ' ')})`} />
        <Tile label="CRISPR" value={data.dependency ? fmt(data.dependency.mean_effect) : '–'} hint={data.dependency ? `dependent in ${data.dependency.n_dependent}/${data.dependency.n_lines} lines` : 'no data'} />
      </div>
      <div className="grid-gene">
        <div className="stack">
          <div className="card">
            <h2>Identity & function</h2>
            <div className="kv">
              <div>Ensembl</div><div className="mono">{g.ensembl_gene_id}</div><div>Entrez</div><div className="mono">{g.entrez_id}</div>
              <div>UniProt</div><div className="mono">{u.uniprot_acc || g.uniprot_acc}{u.entry_name ? ` · ${u.entry_name} · ${u.length} aa` : ''}</div>
              <div>Aliases</div><div>{[g.prev_symbols, g.alias_symbols].filter(Boolean).join(' | ').replace(/\|/g, ' · ') || '–'}</div>
              <div>Target class</div><div>{ot.ot_target_class || '–'}</div>
            </div>
            <h3>Function</h3><Expandable text={u.function || ot.function_desc || ''} />
          </div>
          <div className="card">
            <h2>Localization</h2>
            <div className="kv">
              <div>Surfaceome</div><div>{st.surfaceome_label ? `${st.surfaceome_label}${st.ml_score != null ? ` (ML ${fmt(st.ml_score)})` : ''}${st.cd_number && st.cd_number !== 'None' ? ` · ${st.cd_number}` : ''}` : '–'}</div>
              <div>Topology</div><div>{u.n_tm ?? st.n_tm ?? 0} TM helices{u.has_signal ? ' · signal peptide' : ''}{u.is_gpi ? ' · GPI anchor' : ''}{u.kw_secreted ? ' · secreted' : ''}</div>
              <div>HPA subcellular</div><div>{data.hpa_subcellular ? `${data.hpa_subcellular.main_location || ''}${data.hpa_subcellular.additional_location ? ` (+ ${data.hpa_subcellular.additional_location})` : ''} · ${data.hpa_subcellular.reliability}` : '–'}</div>
              <div>Open Targets</div><div>{ot.ot_subcellular || '–'}</div>
              <div>UniProt</div><div><Expandable text={u.subcellular_location || ''} lines={3} /></div>
            </div>
            <h3>Normal tissue protein (HPA IHC)</h3>
            <div className="chips">{data.hpa_normal_ihc.filter((r: any) => r.level_num > 0).sort((a: any, b: any) => b.level_num - a.level_num).map((r: any) =>
              <span key={r.tissue} className="badge" style={{ background: `color-mix(in srgb, var(--s2) ${r.level_num * 12}%, var(--surface-2))` }}>{r.tissue}: {LEVEL[r.level_num]}</span>)}
              {data.hpa_normal_ihc.length === 0 && <span className="faint small">no IHC data</span>}
              {data.hpa_normal_ihc.length > 0 && data.hpa_normal_ihc.every((r: any) => r.level_num === 0) && <span className="faint small">not detected in any normal tissue</span>}</div>
          </div>
          <div className="card">
            <h2>Tractability & precedent</h2>
            <div className="kv"><div>OT buckets</div><div className="small">{(st.tractability || '').split('|').filter(Boolean).join(' · ') || '–'}</div>
              <div>Associations</div><div className="small">{data.associations.slice(0, 8).map((a: any) => `${a.disease_name} ${fmt(a.score)}`).join(' · ') || '–'}</div></div>
            <h3>Known drugs ({data.known_drugs.length})</h3>
            {data.known_drugs.length === 0 ? <span className="faint small">none in Open Targets</span> : (
              <div className="table-wrap" style={{ maxHeight: 220 }}><table className="dt"><thead><tr><th>Drug</th><th>Type</th><th className="num">Phase</th><th>Mechanism</th></tr></thead>
                <tbody>{data.known_drugs.slice(0, 60).map((d: any, i: number) => <tr key={i}><td><b>{d.drug_name}</b></td><td className="small muted">{d.drug_type}</td><td className="num">{fmt(d.phase, 0)}</td><td className="small muted" title={d.diseases || ''}>{d.mechanism || d.action_type || ''}</td></tr>)}</tbody></table></div>)}
          </div>
        </div>
        <div className="card">
          <div className="card-head"><h2>Where {g.symbol} ranks as a target</h2>
            <div className="row center"><Seg value={profile} onChange={setProfile} options={[{ value: 'any_modality', label: 'Any modality' }, { value: 'surface', label: 'Surface' }]} />
              <select value={types} onChange={e => setTypes(e.target.value)}><option value="cell_line,lineage,primary_disease,subtype,tcga,target">All contexts</option><option value="cell_line">Cell lines</option><option value="lineage,primary_disease,subtype">DepMap groups</option><option value="tcga,target">TCGA / TARGET</option></select></div></div>
          <ComponentLegend weights={weights} />
          <div style={{ marginTop: 10 }}><DataTable rows={rk.data?.rows || []} cols={cols} rowKey={r => r.context_id} defaultSort="score" maxHeight="64vh" loading={rk.isFetching} /></div>
        </div>
      </div>
      <div className="card"><ExprPlot symbol={symbol} source="cell_lines" title="DepMap cell lines by lineage (each point is a line)" /></div>
      <div className="grid2">
        <div className="card"><ExprPlot symbol={symbol} source="tcga" title="TCGA / TARGET tumors and TCGA adjacent normals" /></div>
        <div className="card"><ExprPlot symbol={symbol} source="gtex_toil" title="GTEx normal tissues (TOIL)" /></div>
      </div>
      <div className="card"><ExprPlot symbol={symbol} source="lineages" title="DepMap lineages and non-cancerous line groups" /></div>
      <p className="small faint">Expression plots show raw per-source log2(TPM+1); rankings use quantile-normalised values. Type badges: {Object.entries(SHORT).slice(0, 6).map(([k, v]) => `${v} = ${TYPE_LABELS[k]}`).join(', ')}.</p>
    </div>
  )
}
