import { useEffect, useMemo, useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { Link, useNavigate, useParams } from 'react-router-dom'
import { api, fmt, qs } from '../api'
import DataTable, { Col } from '../components/DataTable'
import GeneSearch from '../components/GeneSearch'
import Plot from '../components/Plot'
import { Badge, Empty, Seg, Skeleton, Tile } from '../components/ui'
import { plotTheme } from '../theme'

const shortSite = (s: string) => s?.replace(/^(GTEx \(TOIL\): |TCGA normal: )/, '')

function Structure({ st }: { st: any }) {
  const t = plotTheme()
  const tr = st.transcripts as any[]; const bins = st.bins as any[]
  const varSet = new Set(bins.filter(b => b.is_variable).map(b => b.bin))
  const shapes: any[] = []; const ann: any[] = []
  tr.forEach((x, i) => {
    const y = tr.length - i
    if (x.bins.length) shapes.push({ type: 'line', x0: Math.min(...x.bins), x1: Math.max(...x.bins), y0: y, y1: y, line: { color: t.axis, width: 1 } })
    x.bins.forEach((b: number) => shapes.push({ type: 'rect', x0: b - 0.38, x1: b + 0.38, y0: y - 0.3, y1: y + 0.3, line: { width: 0 }, fillcolor: varSet.has(b) ? t.s2 : t.s1 }))
  })
  const labels = tr.map(x => `${x.transcript_name}${x.variant_summary ? ` · ${x.variant_summary}` : ''}`)
  return <Plot data={[{ x: tr.map(() => 0), y: tr.map((_, i) => tr.length - i), mode: 'markers', marker: { opacity: 0 }, hoverinfo: 'skip', showlegend: false, type: 'scatter' }]}
    layout={{ height: Math.max(220, tr.length * 26 + 80), margin: { l: 300, r: 20, t: 10, b: 50 }, shapes, annotations: ann, showlegend: false,
      xaxis: { tickmode: 'array', tickvals: bins.map(b => b.bin), ticktext: bins.map(b => b.label), range: [0.4, bins.length + 0.6], showgrid: false, zeroline: false, title: { text: `exons (${st.strand === '-' ? 'minus' : 'plus'} strand, transcription order; introns not to scale)` } },
      yaxis: { tickmode: 'array', tickvals: tr.map((_, i) => tr.length - i), ticktext: labels, showgrid: false, zeroline: false, range: [0.3, tr.length + 0.7], tickfont: { size: 11 } } }} />
}

function Composition({ symbol, st }: { symbol: string; st: any }) {
  const [set, setSet] = useState<'tumor' | 'normal'>('tumor')
  const types = set === 'tumor' ? 'tcga,target' : 'gtex_toil,tcga_normal'
  const { data } = useQuery({ queryKey: ['iso-comp', symbol, types], queryFn: () => api.isoformComposition(symbol, types) })
  const t = plotTheme()
  if (!data) return <Skeleton rows={6} />
  const rows = data.rows as any[]
  if (!rows.length) return <Empty title="No isoform expression for this gene" />
  // top 7 transcripts by overall share, rest folded into Other (fixed categorical order, never cycled)
  const share: Record<string, number> = {}; rows.forEach(r => { share[r.transcript_id] = (share[r.transcript_id] || 0) + (r.pooled_frac || 0) })
  const top = Object.entries(share).sort((a, b) => b[1] - a[1]).slice(0, 7).map(([k]) => k)
  const name: Record<string, string> = {}; rows.forEach(r => { name[r.transcript_id] = r.transcript_name })
  const vs: Record<string, string> = {}; (st?.transcripts || []).forEach((x: any) => { vs[x.transcript_id] = x.variant_summary })
  const ctx = Array.from(new Set(rows.map(r => r.name)))
  const byCtx: Record<string, Record<string, number>> = {}; const tot: Record<string, number> = {}
  rows.forEach(r => { (byCtx[r.name] ||= {})[r.transcript_id] = r.pooled_frac || 0; tot[r.name] = (tot[r.name] || 0) + (r.mean_tpm || 0) })
  const firstTop = (c: string) => byCtx[c][top[0]] || 0
  ctx.sort((a, b) => firstTop(b) - firstTop(a))
  const colors = [t.s1, t.s2, t.s3, cssv('--s4'), cssv('--s5'), cssv('--s6'), t.s7]
  const traces: any[] = top.map((id, i) => ({ type: 'bar', orientation: 'h', name: `${name[id]}${vs[id] ? ` (${vs[id]})` : ''}`, y: ctx.map(shortSite), x: ctx.map(c => byCtx[c][id] || 0),
    marker: { color: colors[i], line: { width: 1, color: t.paper } }, hovertemplate: `%{y}<br>${name[id]}: %{x:.0%}<extra></extra>` }))
  traces.push({ type: 'bar', orientation: 'h', name: 'other', y: ctx.map(shortSite), x: ctx.map(c => Math.max(0, 1 - top.reduce((a, id) => a + (byCtx[c][id] || 0), 0))), marker: { color: t.neutral, line: { width: 1, color: t.paper } }, hovertemplate: '%{y}<br>other: %{x:.0%}<extra></extra>' })
  return <>
    <div className="row center" style={{ marginBottom: 8 }}><Seg value={set} onChange={setSet} options={[{ value: 'tumor', label: 'TCGA / TARGET tumors' }, { value: 'normal', label: 'Normal tissues (GTEx + TCGA adjacent)' }]} /><span className="small faint">share of the gene's TPM (mean over samples); sorted by the most abundant isoform</span></div>
    <Plot data={traces} layout={{ barmode: 'stack', height: Math.max(380, ctx.length * 17 + 120), margin: { l: 210, r: 10, t: 10, b: 40 }, legend: { orientation: 'h', y: -0.06, yanchor: 'top', x: 0, font: { size: 11 } },
      xaxis: { tickformat: '.0%', range: [0, 1], title: { text: 'isoform share' } }, yaxis: { autorange: 'reversed', tickfont: { size: 10 } } }} />
  </>
}
function cssv(n: string) { return getComputedStyle(document.documentElement).getPropertyValue(n).trim() }

function Inclusion({ symbol, st }: { symbol: string; st: any }) {
  const [feature, setFeature] = useState(`exon:${st.default_exon}`)
  const [metric, setMetric] = useState<'psi' | 'tpm'>('psi')
  const [minTpm, setMinTpm] = useState(5)
  useEffect(() => { setFeature(`exon:${st.default_exon}`) }, [st.gene])
  const p = { feature, metric, min_gene_tpm: minTpm }
  const { data, isFetching, error } = useQuery({ queryKey: ['iso-inc', symbol, p], queryFn: () => api.isoformInclusion(symbol, p) })
  const t = plotTheme()
  const comp = (data?.comparison || []) as any[]
  const ctxs = (data?.contexts || []) as any[]
  const fname = feature.startsWith('exon:') ? `exon ${feature.slice(5)}` : (st.transcripts.find((x: any) => `transcript:${x.transcript_id}` === feature)?.transcript_name || feature)
  const unit = metric === 'psi' ? `${fname} inclusion (fraction of ${symbol} TPM)` : `log2(TPM+1) of ${fname}-containing transcripts`
  // grouped boxes per tissue site: tumor / adjacent normal / GTEx
  const sites = useMemo(() => Array.from(new Set(comp.map(c => c.site))).filter(Boolean).sort((a, b) => {
    const da = comp.filter(c => c.site === a).map(c => c.delta_vs_gtex ?? -9); const db = comp.filter(c => c.site === b).map(c => c.delta_vs_gtex ?? -9)
    return Math.max(...db) - Math.max(...da) }), [comp])
  const box = (sel: (c: any) => boolean, name: string, color: string, xf: (c: any) => string) => {
    const cs = ctxs.filter(sel).filter(c => sites.includes(c.context_type === 'tcga' || c.context_type === 'target' ? c.lineage : c.key))
    return { type: 'box', name, x: cs.map(xf), q1: cs.map(c => c.q25), median: cs.map(c => c.median), q3: cs.map(c => c.q75), lowerfence: cs.map(c => c.p05), upperfence: cs.map(c => c.p95),
      marker: { color }, line: { width: 1.2, color }, fillcolor: 'rgba(0,0,0,0)', text: cs.map(c => `${c.name} · n=${c.n}`), hovertemplate: '%{text}<br>median %{median:.2f}<extra></extra>' }
  }
  const traces = data ? [
    box(c => c.context_type === 'tcga' || c.context_type === 'target', 'tumor (TCGA / TARGET)', t.s1, c => c.lineage),
    box(c => c.context_type === 'tcga_normal', 'adjacent normal (TCGA)', t.s3, c => c.key),
    box(c => c.context_type === 'gtex_toil', 'normal tissue (GTEx)', t.s7, c => c.key),
  ] : []
  const cols: Col<any>[] = [
    { key: 'tumor', label: 'Tumor type', render: r => <Link to={`/context/${r.context_id}`}>{r.tumor}</Link> },
    { key: 'site', label: 'Tissue' },
    { key: 'tumor_median', label: 'Tumor', num: true, render: r => fmt(r.tumor_median), title: 'median in tumors' },
    { key: 'adj_normal_median', label: 'Adj. normal', num: true, render: r => fmt(r.adj_normal_median) },
    { key: 'gtex_median', label: 'GTEx', num: true, render: r => fmt(r.gtex_median) },
    { key: 'delta_vs_gtex', label: 'Δ vs GTEx', num: true, render: r => <b>{fmt(r.delta_vs_gtex)}</b> },
    { key: 'auroc_vs_gtex', label: 'AUROC vs GTEx', num: true, render: r => fmt(r.auroc_vs_gtex), title: 'probability a random tumor sample exceeds a random GTEx sample of the same tissue (0.5 = no difference)' },
    { key: 'auroc_vs_adj_normal', label: 'AUROC vs adj.', num: true, render: r => fmt(r.auroc_vs_adj_normal) },
    { key: 'n_tumor', label: 'n', num: true, render: r => `${r.n_tumor} / ${r.n_adj_normal} / ${r.n_gtex}`, sort: r => r.n_tumor, title: 'tumor / adjacent normal / GTEx samples' },
  ]
  return <>
    <div className="row">
      <div className="field"><label className="lbl">Feature</label>
        <select value={feature} onChange={e => setFeature(e.target.value)}>
          <optgroup label="Variable exons">{st.variable.map((v: string) => <option key={v} value={`exon:${v}`}>exon {v}</option>)}</optgroup>
          <optgroup label="All exons">{st.bins.filter((b: any) => !st.variable.includes(b.label)).map((b: any) => <option key={b.label} value={`exon:${b.label}`}>exon {b.label}</option>)}</optgroup>
          <optgroup label="Transcripts">{st.transcripts.map((x: any) => <option key={x.transcript_id} value={`transcript:${x.transcript_id}`}>{x.transcript_name}{x.variant_summary ? ` (${x.variant_summary})` : ''}</option>)}</optgroup>
        </select></div>
      <div className="field"><label className="lbl">Measure</label><Seg value={metric} onChange={setMetric} options={[{ value: 'psi', label: 'Inclusion (fraction)' }, { value: 'tpm', label: 'Absolute level (TPM)' }]} /></div>
      {metric === 'psi' && <div className="field"><label className="lbl">Min {symbol} TPM per sample</label><input type="number" value={minTpm} min={0} step={1} style={{ width: 90 }} onChange={e => setMinTpm(+e.target.value)} /></div>}
      {data && <a className="btn secondary sm" style={{ alignSelf: 'flex-end' }} href={`/api/genes/${symbol}/isoforms/inclusion?${qs({ ...p, format: 'csv' })}`}>CSV</a>}
    </div>
    {error && <div className="error" style={{ marginTop: 8 }}>{String(error)}</div>}
    {!data && isFetching && <Skeleton rows={6} />}
    {data && <>
      <Plot data={traces} layout={{ boxmode: 'group', height: 460, margin: { l: 60, r: 10, t: 10, b: 130 }, legend: { orientation: 'h', y: 1.08, x: 0 },
        yaxis: { title: { text: unit }, ...(metric === 'psi' ? { range: [0, 1], tickformat: '.0%' } : {}) }, xaxis: { categoryorder: 'array', categoryarray: sites, tickangle: -45, tickfont: { size: 10 } } }} />
      <p className="small faint">Boxes: interquartile range, whiskers 5th–95th percentile; tissues sorted by the largest tumor-minus-GTEx difference. {metric === 'psi' ? `Samples with ${symbol} below ${minTpm} TPM are excluded (inclusion is undefined when the gene is off).` : ''}</p>
      <h3>Tumor vs normal by tumor type</h3>
      <DataTable rows={comp} cols={cols} rowKey={r => r.context_id} defaultSort="delta_vs_gtex" maxHeight={420} loading={isFetching} />
    </>}
  </>
}

function CellLines({ symbol, st }: { symbol: string; st: any }) {
  const [feature, setFeature] = useState(`exon:${st.default_exon}`)
  const [metric, setMetric] = useState<'psi' | 'tpm'>('psi')
  const [q, setQ] = useState('')
  useEffect(() => { setFeature(`exon:${st.default_exon}`) }, [st.gene])
  const p = { feature, metric, min_gene_tpm: 5, types: 'lineage,normal_lines,cell_line' }
  const { data, isFetching, error } = useQuery({ queryKey: ['iso-lines', symbol, p], queryFn: () => api.isoformInclusion(symbol, p) })
  const t = plotTheme()
  const ctxs = (data?.contexts || []) as any[]
  const lins = ctxs.filter(c => c.context_type !== 'cell_line' && c.n >= 3).sort((a, b) => b.median - a.median)
  const lines = ctxs.filter(c => c.context_type === 'cell_line').map(c => ({ ...c, value: c.median }))
  const shown = q ? lines.filter(l => l.name.toLowerCase().includes(q.toLowerCase()) || (l.lineage || '').toLowerCase().includes(q.toLowerCase())) : lines
  const fname = feature.startsWith('exon:') ? `exon ${feature.slice(5)}` : (st.transcripts.find((x: any) => `transcript:${x.transcript_id}` === feature)?.transcript_name || feature)
  const unit = metric === 'psi' ? `${fname} inclusion` : `log2(TPM+1), ${fname}-containing`
  const cols: Col<any>[] = [
    { key: 'name', label: 'Cell line', render: r => <Link to={`/context/${r.context_id}`}>{r.name}</Link> },
    { key: 'lineage', label: 'Lineage' },
    { key: 'value', label: metric === 'psi' ? 'Inclusion' : 'log2(TPM+1)', num: true, render: r => <b>{metric === 'psi' ? `${(r.value * 100).toFixed(0)}%` : fmt(r.value)}</b> },
  ]
  return <>
    <div className="row">
      <div className="field"><label className="lbl">Feature</label>
        <select value={feature} onChange={e => setFeature(e.target.value)}>
          <optgroup label="Variable exons">{st.variable.map((v: string) => <option key={v} value={`exon:${v}`}>exon {v}</option>)}</optgroup>
          <optgroup label="Transcripts">{st.transcripts.map((x: any) => <option key={x.transcript_id} value={`transcript:${x.transcript_id}`}>{x.transcript_name}{x.variant_summary ? ` (${x.variant_summary})` : ''}</option>)}</optgroup>
        </select></div>
      <div className="field"><label className="lbl">Measure</label><Seg value={metric} onChange={setMetric} options={[{ value: 'psi', label: 'Inclusion (fraction)' }, { value: 'tpm', label: 'Absolute level (TPM)' }]} /></div>
    </div>
    {error && <div className="error" style={{ marginTop: 8 }}>{String(error)}</div>}
    {!data && isFetching && <Skeleton rows={6} />}
    {data && <div className="grid2" style={{ gridTemplateColumns: '3fr 2fr', marginTop: 8 }}>
      <div>
        <Plot data={[{ type: 'box', x: lins.map(c => c.name.replace(' (all lines)', '').replace('Non-cancerous lines: ', 'Normal: ')), q1: lins.map(c => c.q25), median: lins.map(c => c.median), q3: lins.map(c => c.q75),
          lowerfence: lins.map(c => c.p05), upperfence: lins.map(c => c.p95), marker: { color: t.s1 }, line: { width: 1.2, color: t.s1 }, fillcolor: 'rgba(0,0,0,0)', text: lins.map(c => `n=${c.n}`), hovertemplate: '%{x}<br>median %{median:.2f} · %{text}<extra></extra>' }]}
          layout={{ height: 420, margin: { l: 60, r: 10, t: 10, b: 130 }, showlegend: false, yaxis: { title: { text: unit }, ...(metric === 'psi' ? { range: [0, 1], tickformat: '.0%' } : {}) }, xaxis: { tickangle: -50, tickfont: { size: 10 } } }} />
        <p className="small faint">DepMap 26Q3 cell lines (default RNA profile), grouped by lineage; lineages with ≥ 3 lines. {metric === 'psi' ? `Lines with ${symbol} below 5 TPM excluded.` : ''}</p>
      </div>
      <div>
        <input type="text" placeholder="Find a cell line or lineage (e.g. BT-474, Breast)" value={q} onChange={e => setQ(e.target.value)} style={{ width: '100%', marginBottom: 8 }} />
        <DataTable rows={shown} cols={cols} rowKey={r => r.context_id} defaultSort="value" maxHeight={380} loading={isFetching} />
      </div>
    </div>}
  </>
}

export default function Isoforms() {
  const { symbol = 'CD44' } = useParams(); const nav = useNavigate()
  const genes = useQuery({ queryKey: ['iso-genes'], queryFn: api.isoformGenes })
  const { data: st, error, isLoading } = useQuery({ queryKey: ['iso-struct', symbol], queryFn: () => api.isoformStructure(symbol) })
  return (
    <div className="stack">
      <div className="page-head">
        <div><h1>Isoforms · {st?.gene || symbol}</h1><p className="sub">Transcript-level expression in TCGA/TARGET tumors, TCGA adjacent normals and GTEx tissues (UCSC Xena TOIL, RSEM, GENCODE v23), and DepMap 26Q3 cell lines.</p></div>
        <div className="row center"><GeneSearch onPick={s => nav(`/isoforms/${s}`)} />{st && <Link className="btn secondary" to={`/gene/${st.gene}`}>Gene page</Link>}</div>
      </div>
      <div className="row center"><span className="small faint">Genes with exon-level detail:</span><div className="chips">{(genes.data || []).map(g => <Link key={g.symbol} to={`/isoforms/${g.symbol}`} className="chip" style={g.symbol === st?.gene ? { borderColor: 'var(--accent)', color: 'var(--accent)' } : undefined}>{g.symbol}</Link>)}</div></div>
      {error && <div className="error">{String(error)}</div>}
      {isLoading && <div className="card"><Skeleton rows={8} /></div>}
      {st && <>
        {st.note && <div className="card small">{st.note}</div>}
        <div className="tiles">
          <Tile label="Transcripts" value={st.n_transcripts_total} hint={`top ${st.transcripts.length} by expression shown`} />
          <Tile label="Exons" value={st.bins.length} hint={`${st.variable.length} variable`} />
          <Tile label="Per-sample detail" value={st.detail ? 'yes' : 'no'} hint={st.detail ? 'exon inclusion available' : 'composition only'} />
          <Tile label="Cell lines" value={st.n_cell_lines || '–'} hint={st.n_cell_lines ? 'DepMap transcript data' : 'add DepMap transcript file'} />
        </div>
        <div className="card"><div className="card-head"><h2>Transcript structure</h2><span className="small faint">orange = variable exons · rows ordered by expression</span></div><Structure st={st} /></div>
        {st.detail ? <div className="card"><div className="card-head"><h2>Exon inclusion: tumor vs normal</h2></div><Inclusion symbol={st.gene} st={st} /></div>
          : <div className="card"><Empty title="Exon-level comparison not available for this gene">Per-sample isoform data is stored for the genes listed above. Add {st.gene} to <code className="inline">config/isoform_genes.yaml</code> and run <code className="inline">ct build --step isoforms</code>.</Empty></div>}
        {st.detail && st.n_cell_lines > 0 && <div className="card"><div className="card-head"><h2>Cell lines (DepMap)</h2><span className="small faint">{st.n_cell_lines.toLocaleString()} lines</span></div><CellLines symbol={st.gene} st={st} /></div>}
        <div className="card"><div className="card-head"><h2>Isoform composition by context</h2></div><Composition symbol={st.gene} st={st} /></div>
        <p className="small faint">Isoform quantification from short reads is an estimate: transcripts that differ by a single exon share most reads, so exon-level inclusion (summing every transcript that contains the exon) is more robust than any single transcript. Values come from one pipeline, so tumor and normal samples are directly comparable.</p>
      </>}
    </div>
  )
}
