import { Fragment, useEffect, useMemo, useRef, useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { api, Context, TYPE_LABELS } from '../api'

const ORDER = ['custom', 'cell_line', 'lineage', 'primary_disease', 'subtype', 'normal_lines', 'tcga', 'target', 'tcga_normal', 'gtex_toil', 'gtex_tissue', 'hpa_rna_tissue']
export const SHORT: Record<string, string> = { cell_line: 'line', lineage: 'lineage', primary_disease: 'disease', subtype: 'subtype', normal_lines: 'normal lines', tcga: 'TCGA', target: 'TARGET', tcga_normal: 'TCGA normal', gtex_toil: 'GTEx', gtex_tissue: 'GTEx v10', hpa_rna_tissue: 'HPA RNA', custom: 'custom' }

export default function ContextPicker({ value, onChange, label, types, placeholder = 'Search cell line, lineage, cancer type, tissue…', autoFocus }: {
  value: Context | null; onChange: (c: Context) => void; label?: string; types?: string[]; placeholder?: string; autoFocus?: boolean }) {
  const { data } = useQuery({ queryKey: ['contexts-all'], queryFn: () => api.contexts() })
  const [q, setQ] = useState(''); const [open, setOpen] = useState(false); const [idx, setIdx] = useState(0)
  const ref = useRef<HTMLDivElement>(null); const inp = useRef<HTMLInputElement>(null)
  useEffect(() => { if (open) { setQ(''); setIdx(0); setTimeout(() => inp.current?.focus(), 0) } }, [open])
  useEffect(() => { if (autoFocus) setOpen(true) }, [autoFocus])
  useEffect(() => {
    const h = (e: MouseEvent) => { if (ref.current && !ref.current.contains(e.target as Node)) setOpen(false) }
    document.addEventListener('mousedown', h); return () => document.removeEventListener('mousedown', h)
  }, [])
  const items = useMemo(() => {
    const all = (data || []).filter(c => !types || types.includes(c.context_type))
    const s = q.trim().toLowerCase()
    const hits = s ? all.filter(c => c.name.toLowerCase().includes(s) || (c.lineage || '').toLowerCase().includes(s) || c.key.toLowerCase().includes(s) || (c.primary_disease || '').toLowerCase().includes(s)) : all
    const score = (c: Context) => (s && c.name.toLowerCase().startsWith(s) ? 0 : 1) + ORDER.indexOf(c.context_type) * 0.01
    return hits.sort((a, b) => score(a) - score(b) || a.name.localeCompare(b.name)).slice(0, 80)
  }, [data, q, types])
  const grouped = useMemo(() => {
    const g: { type: string; items: { c: Context; i: number }[] }[] = []
    items.forEach((c, i) => { let gr = g.find(x => x.type === c.context_type); if (!gr) { gr = { type: c.context_type, items: [] }; g.push(gr) } gr.items.push({ c, i }) })
    return g
  }, [items])
  const pick = (c: Context) => { onChange(c); setOpen(false) }
  const key = (e: React.KeyboardEvent) => {
    if (e.key === 'ArrowDown') { e.preventDefault(); setIdx(i => Math.min(items.length - 1, i + 1)) }
    else if (e.key === 'ArrowUp') { e.preventDefault(); setIdx(i => Math.max(0, i - 1)) }
    else if (e.key === 'Enter' && items[idx]) pick(items[idx])
    else if (e.key === 'Escape') setOpen(false)
  }
  return (
    <div className="field picker" ref={ref}>
      {label && <label className="lbl">{label}</label>}
      <button type="button" className="select-btn" onClick={() => setOpen(!open)}>
        {value ? <><span>{value.name}</span><span className="badge type">{SHORT[value.context_type] || value.context_type}</span>{value.n_members > 1 && <span className="faint small">n={value.n_members}</span>}</> : <span className="ph">{placeholder}</span>}
        <span className="caret">▼</span>
      </button>
      {open && (
        <div className="pop">
          <input ref={inp} value={q} placeholder="Type to filter… (↑↓ Enter)" onChange={e => { setQ(e.target.value); setIdx(0) }} onKeyDown={key} />
          <ul>
            {grouped.map(g => (<Fragment key={g.type}>
              <li className="group">{TYPE_LABELS[g.type] || g.type}</li>
              {g.items.map(({ c, i }) => (
                <li key={c.context_id} className={`item ${i === idx ? 'active' : ''}`} onMouseEnter={() => setIdx(i)} onMouseDown={() => pick(c)}>
                  <span>{c.name}</span>{c.is_normal && <span className="badge normal">normal</span>}
                  <span className="t">{c.lineage && c.lineage !== c.name ? c.lineage : ''}{c.n_members > 1 ? ` · n=${c.n_members}` : ''}</span>
                </li>
              ))}
            </Fragment>))}
            {items.length === 0 && <li className="empty">No matches</li>}
          </ul>
        </div>
      )}
    </div>
  )
}
