import { ReactNode, useState } from 'react'
import { fmt } from '../api'

export const COMP = ['E', 'S', 'P', 'T', 'A', 'R', 'U', 'D'] as const
export type Comp = typeof COMP[number]
export const COMP_NAMES: Record<string, string> = { E: 'Expression', S: 'Selectivity', P: 'Prevalence', T: 'Tumor protein', U: 'Surface', R: 'Tractability', A: 'Association', D: 'Dependency' }
/** Fixed categorical slot order from the validated palette (E..D map to slots 1..8). */
export const COMP_COLOR: Record<string, string> = { E: 'var(--s1)', S: 'var(--s2)', P: 'var(--s3)', T: 'var(--s4)', A: 'var(--s5)', R: 'var(--s6)', U: 'var(--s7)', D: 'var(--s8)' }

export function Badge({ kind, children, title }: { kind?: string; children: ReactNode; title?: string }) {
  return <span className={`badge ${kind || ''}`} title={title}>{children}</span>
}

export function Tile({ label, value, hint }: { label: string; value: ReactNode; hint?: ReactNode }) {
  return <div className="tile"><div className="label">{label}</div><div className="value">{value}</div>{hint && <div className="hint">{hint}</div>}</div>
}

export function Bar({ v, color = 'var(--s1)', max = 1, width = 56 }: { v: number | null | undefined; color?: string; max?: number; width?: number }) {
  if (v === null || v === undefined || Number.isNaN(v)) return <div className="cell-bar"><span className="faint">–</span></div>
  const w = Math.max(0, Math.min(1, v / max)) * width
  return <div className="cell-bar"><i className="bar" style={{ width: w, background: color }} /><span>{fmt(v)}</span></div>
}

/** Stacked bar of weighted components (weights * component value), proportional to the composite. */
export function ScoreStack({ r, weights, width = 150 }: { r: any; weights: Record<string, number>; width?: number }) {
  const parts = COMP.map(c => ({ c, v: (weights[c] || 0) * (r[c] ?? 0) })).filter(p => p.v > 0)
  const total = Object.entries(weights).reduce((a, [c, w]) => a + (r[c] == null ? 0 : w), 0) || 1
  const tip = COMP.map(c => `${c} ${COMP_NAMES[c]}: ${r[c] == null ? '–' : fmt(r[c])}${weights[c] ? ` × ${weights[c]}` : ''}`).join('\n')
  return (
    <div className="stack-bar" style={{ width }} title={tip}>
      {parts.map(p => <i key={p.c} style={{ width: `${(p.v / total) * 100}%`, background: COMP_COLOR[p.c] }} />)}
    </div>
  )
}

export function ComponentLegend({ weights }: { weights?: Record<string, number> }) {
  return <div className="legend">{COMP.filter(c => !weights || weights[c] > 0).map(c => <span key={c}><i style={{ background: COMP_COLOR[c] }} />{c} · {COMP_NAMES[c]}{weights ? ` (${weights[c]})` : ''}</span>)}</div>
}

export function Empty({ title, children }: { title: string; children?: ReactNode }) {
  return <div className="empty"><b>{title}</b>{children}</div>
}

export function Skeleton({ rows = 6 }: { rows?: number }) {
  return <div className="stack" style={{ gap: 8, padding: 8 }}>{Array.from({ length: rows }).map((_, i) => <div key={i} className="skeleton" style={{ width: `${90 - (i % 3) * 12}%` }} />)}</div>
}

export function Expandable({ text, lines = 4 }: { text: string; lines?: number }) {
  const [open, setOpen] = useState(false)
  if (!text) return <span className="faint">–</span>
  const long = text.length > 420
  return <div><div className={`truncate ${open ? 'open' : ''}`} style={{ WebkitLineClamp: lines }}>{text}</div>{long && <button className="btn ghost sm" onClick={() => setOpen(!open)}>{open ? 'Show less' : 'Show more'}</button>}</div>
}

export function Seg<T extends string>({ value, options, onChange }: { value: T; options: { value: T; label: string }[]; onChange: (v: T) => void }) {
  return <div className="seg">{options.map(o => <button key={o.value} className={o.value === value ? 'on' : ''} onClick={() => onChange(o.value)}>{o.label}</button>)}</div>
}
