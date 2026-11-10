import { ReactNode, useEffect, useMemo, useRef, useState } from 'react'
import { createPortal } from 'react-dom'
// @ts-ignore
import Plotly from 'plotly.js-dist-min'

type Bg = 'white' | 'transparent' | 'dark'
type Opts = {
  title: string; xTitle: string; yTitle: string
  font: string; titleSize: number; axisTitleSize: number; tickSize: number; labelSize: number
  xGrid: boolean; yGrid: boolean; zeroLine: boolean; axisLines: boolean; ticksOutside: boolean; showTickLabels: boolean
  xMin: string; xMax: string; yMin: string; yMax: string; xDtick: string; yDtick: string; xLog: boolean; yLog: boolean; xTickAngle: number
  markerScale: number; showLegend: boolean; legendPos: 'top' | 'right' | 'inside' | 'bottom'
  bg: Bg; width: number; height: number; scale: number; format: 'png' | 'svg' | 'jpeg'; filename: string
}
const KEY = 'ct-export-prefs'
const PERSIST: (keyof Opts)[] = ['font', 'titleSize', 'axisTitleSize', 'tickSize', 'labelSize', 'xGrid', 'yGrid', 'zeroLine', 'axisLines', 'ticksOutside', 'bg', 'scale', 'format']
const FONTS = ['Arial', 'Helvetica', 'Times New Roman', 'Inter', 'Courier New']

const txt = (t: any) => (typeof t === 'string' ? t : t?.text || '')
const slug = (s: string) => s.replace(/<[^>]+>/g, '').replace(/[^\w.-]+/g, '_').replace(/^_+|_+$/g, '').slice(0, 80) || 'figure'
const num = (s: string) => (s.trim() === '' || Number.isNaN(Number(s)) ? null : Number(s))
const fmtR = (v: any) => (typeof v === 'number' && Number.isFinite(v) ? String(+v.toPrecision(4)) : '')

function loadPrefs(): Partial<Opts> { try { return JSON.parse(localStorage.getItem(KEY) || '{}') } catch { return {} } }
function savePrefs(o: Opts) { try { localStorage.setItem(KEY, JSON.stringify(Object.fromEntries(PERSIST.map(k => [k, o[k]])))) } catch {} }

/** Customise-and-export dialog for any Plotly graph div. */
export default function ExportDialog({ gd, onClose }: { gd: any; onClose: () => void }) {
  const full = gd._fullLayout || {}; const lay = gd.layout || {}
  const xType = full.xaxis?.type, yType = full.yaxis?.type
  const xNum = xType === 'linear' || xType === 'log', yNum = yType === 'linear' || yType === 'log'
  const view = { xMin: xNum ? fmtR(full.xaxis.range?.[0]) : '', xMax: xNum ? fmtR(full.xaxis.range?.[1]) : '', yMin: yNum ? fmtR(full.yaxis.range?.[0]) : '', yMax: yNum ? fmtR(full.yaxis.range?.[1]) : '' }
  const data = useMemo(() => JSON.parse(JSON.stringify(gd.data || [])), [gd])
  const [o, setO] = useState<Opts>(() => ({
    title: txt(lay.title), xTitle: txt(full.xaxis?.title), yTitle: txt(full.yaxis?.title),
    font: 'Arial', titleSize: 16, axisTitleSize: 14, tickSize: 12, labelSize: 11,
    xGrid: full.xaxis?.showgrid ?? true, yGrid: full.yaxis?.showgrid ?? true, zeroLine: true, axisLines: false, ticksOutside: false, showTickLabels: true,
    ...view, xDtick: '', yDtick: '', xLog: xType === 'log', yLog: yType === 'log', xTickAngle: full.xaxis?.tickangle === 'auto' ? 0 : (full.xaxis?.tickangle ?? 0),
    markerScale: 1, showLegend: full.showlegend ?? false, legendPos: 'top',
    bg: 'white', width: Math.round(full.width || 800), height: Math.round(full.height || 600), scale: 3, format: 'png',
    filename: slug(txt(lay.title) || [txt(full.xaxis?.title), txt(full.yaxis?.title)].filter(Boolean).join('_vs_')),
    ...loadPrefs(),
  }))
  const set = <K extends keyof Opts>(k: K, v: Opts[K]) => setO(p => ({ ...p, [k]: v }))
  const prev = useRef<HTMLDivElement>(null); const box = useRef<HTMLDivElement>(null)
  const [fit, setFit] = useState(1); const [busy, setBusy] = useState(false); const [msg, setMsg] = useState('')

  const fig = useMemo(() => {
    const dark = o.bg === 'dark'
    const ink = dark ? '#ffffff' : '#111111', grid = dark ? '#3a3a37' : '#e2e1dc', zero = dark ? '#6b6a65' : '#9a9994'
    const bg = o.bg === 'transparent' ? 'rgba(0,0,0,0)' : dark ? '#1a1a19' : '#ffffff'
    const axis = (orig: any, a: 'x' | 'y') => {
      const isNum = a === 'x' ? xNum : yNum
      const lo = num(a === 'x' ? o.xMin : o.yMin), hi = num(a === 'x' ? o.xMax : o.yMax)
      const log = a === 'x' ? o.xLog : o.yLog
      const dt = num(a === 'x' ? o.xDtick : o.yDtick)
      const out: any = {
        ...orig, title: { ...(typeof orig?.title === 'object' ? orig.title : {}), text: a === 'x' ? o.xTitle : o.yTitle, font: { size: o.axisTitleSize, color: ink, family: o.font } },
        tickfont: { size: o.tickSize, color: ink, family: o.font }, showgrid: a === 'x' ? o.xGrid : o.yGrid, gridcolor: grid,
        zeroline: o.zeroLine, zerolinecolor: zero, showline: o.axisLines, linecolor: ink, mirror: o.axisLines ? 'ticks' : false,
        ticks: o.ticksOutside ? 'outside' : '', tickcolor: ink, showticklabels: o.showTickLabels, automargin: true,
      }
      if (a === 'x') out.tickangle = o.xTickAngle
      if (isNum) {
        out.type = log ? 'log' : 'linear'
        if (lo !== null && hi !== null && !log) { out.range = [lo, hi]; out.autorange = false }
        else if (lo !== null && hi !== null && log && lo > 0 && hi > 0) { out.range = [Math.log10(lo), Math.log10(hi)]; out.autorange = false }
        else { delete out.range; out.autorange = orig?.autorange === 'reversed' ? 'reversed' : true }
        if (dt !== null && dt > 0 && !log) { out.dtick = dt; out.tick0 = 0 } else delete out.dtick
      }
      return out
    }
    const legend: any = { top: { orientation: 'h', x: 0, y: 1.02, yanchor: 'bottom' }, bottom: { orientation: 'h', x: 0, y: -0.15, yanchor: 'top' },
      right: { orientation: 'v', x: 1.02, y: 1, xanchor: 'left' }, inside: { orientation: 'v', x: 0.98, y: 0.98, xanchor: 'right', yanchor: 'top', bgcolor: dark ? 'rgba(26,26,25,.8)' : 'rgba(255,255,255,.8)' } }[o.legendPos]
    const scaleSize = (s: any) => (Array.isArray(s) ? s.map((v: number) => v * o.markerScale) : typeof s === 'number' ? s * o.markerScale : s)
    const isBgLine = (c: any) => typeof c === 'string' && /^(#fff|#ffffff|#1a1a19|#fcfcfb)$/i.test(c)
    const traces = data.map((t: any) => {
      const out: any = { ...t }
      if (t.marker) {
        out.marker = { ...t.marker, size: scaleSize(t.marker.size) }
        if (t.marker.line) out.marker.line = { ...t.marker.line, ...(isBgLine(t.marker.line.color) ? { color: bg } : {}) }
      }
      if (t.textfont) out.textfont = { ...t.textfont, size: o.labelSize, color: ink, family: o.font }
      return out
    })
    const layout: any = {
      ...lay, width: o.width, height: o.height, paper_bgcolor: bg, plot_bgcolor: bg,
      font: { family: o.font, size: o.tickSize, color: ink }, title: o.title ? { text: o.title, x: 0.02, xanchor: 'left', font: { size: o.titleSize, color: ink, family: o.font } } : { text: '' },
      margin: { l: 70, r: o.showLegend && o.legendPos === 'right' ? 140 : 24, t: (o.title ? 56 : 24) + (o.showLegend && o.legendPos === 'top' ? 28 : 0), b: 64 },
      xaxis: axis(lay.xaxis || {}, 'x'), yaxis: axis(lay.yaxis || {}, 'y'), showlegend: o.showLegend, legend: { ...legend, font: { size: o.tickSize, color: ink, family: o.font } },
      shapes: (lay.shapes || []), dragmode: false, hovermode: false,
    }
    return { traces, layout }
  }, [o, data])

  // live preview at true pixel size, scaled to fit the preview pane
  useEffect(() => {
    const id = setTimeout(() => { if (prev.current) Plotly.react(prev.current, fig.traces, fig.layout, { staticPlot: true, displayModeBar: false }) }, 120)
    return () => clearTimeout(id)
  }, [fig])
  useEffect(() => {
    const r = () => { const b = box.current; if (b) setFit(Math.min(1, (b.clientWidth - 16) / o.width, (b.clientHeight - 16) / o.height)) }
    r(); window.addEventListener('resize', r); return () => window.removeEventListener('resize', r)
  }, [o.width, o.height])
  useEffect(() => { const k = (e: KeyboardEvent) => { if (e.key === 'Escape') onClose() }; document.addEventListener('keydown', k); return () => { document.removeEventListener('keydown', k); if (prev.current) Plotly.purge(prev.current) } }, [onClose])

  const download = async () => {
    if (!prev.current) return
    setBusy(true); savePrefs(o)
    try {
      await Plotly.react(prev.current, fig.traces, fig.layout, { staticPlot: true })
      await Plotly.downloadImage(prev.current, { format: o.format, filename: o.filename || 'figure', width: o.width, height: o.height, scale: o.format === 'svg' ? 1 : o.scale })
      setMsg(`Saved ${o.filename}.${o.format}`)
    } catch (e: any) { setMsg(`Export failed: ${e?.message || e}`) } finally { setBusy(false) }
  }
  const copy = async () => {
    if (!prev.current) return
    try {
      const url = await Plotly.toImage(prev.current, { format: 'png', width: o.width, height: o.height, scale: o.scale })
      const blob = await (await fetch(url)).blob()
      await navigator.clipboard.write([new ClipboardItem({ 'image/png': blob })]); setMsg('Copied PNG to clipboard')
    } catch (e: any) { setMsg(`Copy failed: ${e?.message || e}`) }
  }
  const dpi = Math.round(96 * o.scale)

  return createPortal(
    <div className="modal-backdrop" onMouseDown={e => { if (e.target === e.currentTarget) onClose() }}>
      <div className="modal export" role="dialog" aria-label="Export figure">
        <div className="modal-head"><h2>Export figure</h2><button className="icon-btn" onClick={onClose} title="Close (Esc)">✕</button></div>
        <div className="export-body">
          <div className="export-preview" ref={box}>
            <div style={{ width: o.width * fit, height: o.height * fit }}>
              <div ref={prev} style={{ width: o.width, height: o.height, transform: `scale(${fit})`, transformOrigin: '0 0', boxShadow: '0 0 0 1px var(--border)', background: o.bg === 'transparent' ? 'repeating-conic-gradient(#ddd 0 25%, #fff 0 50%) 0 0/16px 16px' : undefined }} />
            </div>
            <div className="small faint" style={{ marginTop: 6 }}>Preview at {Math.round(fit * 100)}% · output {o.width * (o.format === 'svg' ? 1 : o.scale)} × {o.height * (o.format === 'svg' ? 1 : o.scale)} px{o.format !== 'svg' ? ` (≈ ${dpi} dpi at ${o.width} px wide)` : ' (vector)'}</div>
          </div>
          <div className="export-controls">
            <Section title="Text">
              <Field label="Title"><input type="text" value={o.title} onChange={e => set('title', e.target.value)} placeholder="(none)" /></Field>
              <Field label="X-axis title"><input type="text" value={o.xTitle} onChange={e => set('xTitle', e.target.value)} /></Field>
              <Field label="Y-axis title"><input type="text" value={o.yTitle} onChange={e => set('yTitle', e.target.value)} /></Field>
              <Field label="Font"><select value={o.font} onChange={e => set('font', e.target.value)}>{FONTS.map(f => <option key={f}>{f}</option>)}</select></Field>
              <div className="grid4">
                <NumField label="Title size" v={o.titleSize} on={v => set('titleSize', v)} min={6} max={48} />
                <NumField label="Axis title" v={o.axisTitleSize} on={v => set('axisTitleSize', v)} min={6} max={40} />
                <NumField label="Tick labels" v={o.tickSize} on={v => set('tickSize', v)} min={5} max={36} />
                <NumField label="Point labels" v={o.labelSize} on={v => set('labelSize', v)} min={5} max={36} />
              </div>
            </Section>
            <Section title="Axes">
              <div className="grid4">
                <Field label={`X min${!xNum ? ' (categorical)' : ''}`}><input type="text" disabled={!xNum} value={o.xMin} onChange={e => set('xMin', e.target.value)} placeholder="auto" /></Field>
                <Field label="X max"><input type="text" disabled={!xNum} value={o.xMax} onChange={e => set('xMax', e.target.value)} placeholder="auto" /></Field>
                <Field label={`Y min${!yNum ? ' (categorical)' : ''}`}><input type="text" disabled={!yNum} value={o.yMin} onChange={e => set('yMin', e.target.value)} placeholder="auto" /></Field>
                <Field label="Y max"><input type="text" disabled={!yNum} value={o.yMax} onChange={e => set('yMax', e.target.value)} placeholder="auto" /></Field>
                <Field label="X tick spacing"><input type="text" disabled={!xNum} value={o.xDtick} onChange={e => set('xDtick', e.target.value)} placeholder="auto" /></Field>
                <Field label="Y tick spacing"><input type="text" disabled={!yNum} value={o.yDtick} onChange={e => set('yDtick', e.target.value)} placeholder="auto" /></Field>
                <NumField label="X label angle" v={o.xTickAngle} on={v => set('xTickAngle', v)} min={-90} max={90} step={15} />
              </div>
              <div className="row" style={{ gap: 6, marginTop: 6 }}>
                <button className="btn secondary sm" disabled={!xNum && !yNum} onClick={() => setO(p => ({ ...p, ...view }))}>Use current zoom</button>
                <button className="btn secondary sm" onClick={() => setO(p => ({ ...p, xMin: '', xMax: '', yMin: '', yMax: '' }))}>Auto range</button>
              </div>
              <div className="checks">
                <Check label="Log X" v={o.xLog} on={v => set('xLog', v)} disabled={!xNum} />
                <Check label="Log Y" v={o.yLog} on={v => set('yLog', v)} disabled={!yNum} />
                <Check label="Tick labels" v={o.showTickLabels} on={v => set('showTickLabels', v)} />
                <Check label="Tick marks" v={o.ticksOutside} on={v => set('ticksOutside', v)} />
              </div>
            </Section>
            <Section title="Grid & frame">
              <div className="checks">
                <Check label="Vertical grid" v={o.xGrid} on={v => set('xGrid', v)} />
                <Check label="Horizontal grid" v={o.yGrid} on={v => set('yGrid', v)} />
                <Check label="Zero lines" v={o.zeroLine} on={v => set('zeroLine', v)} />
                <Check label="Axis box" v={o.axisLines} on={v => set('axisLines', v)} />
              </div>
            </Section>
            <Section title="Markers & legend">
              <div className="grid4">
                <NumField label="Marker size ×" v={o.markerScale} on={v => set('markerScale', v)} min={0.25} max={5} step={0.25} />
                <Field label="Legend"><select value={o.showLegend ? o.legendPos : 'none'} onChange={e => e.target.value === 'none' ? set('showLegend', false) : setO(p => ({ ...p, showLegend: true, legendPos: e.target.value as Opts['legendPos'] }))}>
                  <option value="none">hidden</option><option value="top">top</option><option value="right">right</option><option value="inside">inside, top-right</option><option value="bottom">bottom</option></select></Field>
                <Field label="Background"><select value={o.bg} onChange={e => set('bg', e.target.value as Bg)}><option value="white">white</option><option value="transparent">transparent</option><option value="dark">dark</option></select></Field>
              </div>
            </Section>
            <Section title="Output">
              <div className="grid4">
                <NumField label="Width (px)" v={o.width} on={v => set('width', v)} min={200} max={4000} step={50} />
                <NumField label="Height (px)" v={o.height} on={v => set('height', v)} min={150} max={4000} step={50} />
                <Field label="Resolution"><select value={o.scale} disabled={o.format === 'svg'} onChange={e => set('scale', +e.target.value)}><option value={1}>1× (96 dpi)</option><option value={2}>2× (192 dpi)</option><option value={3}>3× (288 dpi)</option><option value={4}>4× (384 dpi)</option></select></Field>
                <Field label="Format"><select value={o.format} onChange={e => set('format', e.target.value as Opts['format'])}><option value="png">PNG</option><option value="svg">SVG (vector)</option><option value="jpeg">JPEG</option></select></Field>
              </div>
              <div className="row" style={{ gap: 6, marginTop: 6 }}>
                {[[3.5, 3], [7, 4.5], [7, 7]].map(([w, h]) => <button key={`${w}x${h}`} className="chip" onClick={() => setO(p => ({ ...p, width: Math.round(w * 96), height: Math.round(h * 96) }))}>{w}″ × {h}″</button>)}
              </div>
              <Field label="File name"><input type="text" value={o.filename} onChange={e => set('filename', e.target.value)} /></Field>
            </Section>
          </div>
        </div>
        <div className="modal-foot">
          <span className="small muted">{msg}</span>
          <div className="row" style={{ gap: 8 }}>
            {o.format === 'png' && typeof ClipboardItem !== 'undefined' && <button className="btn secondary" onClick={copy}>Copy PNG</button>}
            <button className="btn secondary" onClick={onClose}>Cancel</button>
            <button className="btn" onClick={download} disabled={busy}>{busy ? <span className="spin" /> : `Download ${o.format.toUpperCase()}`}</button>
          </div>
        </div>
      </div>
    </div>, document.body)
}

function Section({ title, children }: { title: string; children: ReactNode }) { return <div className="export-section"><h3>{title}</h3>{children}</div> }
function Field({ label, children }: { label: string; children: ReactNode }) { return <div className="field"><label className="lbl">{label}</label>{children}</div> }
function NumField({ label, v, on, min, max, step = 1 }: { label: string; v: number; on: (v: number) => void; min: number; max: number; step?: number }) {
  return <Field label={label}><input type="number" value={v} min={min} max={max} step={step} onChange={e => { const n = Number(e.target.value); if (Number.isFinite(n)) on(Math.min(max, Math.max(min, n))) }} /></Field>
}
function Check({ label, v, on, disabled }: { label: string; v: boolean; on: (v: boolean) => void; disabled?: boolean }) {
  return <label className="check" style={{ opacity: disabled ? 0.5 : 1 }}><input type="checkbox" checked={v} disabled={disabled} onChange={e => on(e.target.checked)} />{label}</label>
}
