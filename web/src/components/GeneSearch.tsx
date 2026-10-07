import { useEffect, useRef, useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { useNavigate } from 'react-router-dom'
import { api } from '../api'

export default function GeneSearch({ autoFocus, big, onPick }: { autoFocus?: boolean; big?: boolean; onPick?: (symbol: string) => void }) {
  const [q, setQ] = useState(''); const [idx, setIdx] = useState(0); const [focus, setFocus] = useState(false)
  const nav = useNavigate(); const ref = useRef<HTMLInputElement>(null)
  const { data } = useQuery({ queryKey: ['gene-search', q], queryFn: () => api.geneSearch(q), enabled: q.length >= 2 })
  useEffect(() => {
    const h = (e: KeyboardEvent) => { if ((e.metaKey || e.ctrlKey) && e.key === 'k') { e.preventDefault(); ref.current?.focus() } }
    document.addEventListener('keydown', h); return () => document.removeEventListener('keydown', h)
  }, [])
  const go = (s: string) => { setQ(''); setFocus(false); ref.current?.blur(); onPick ? onPick(s) : nav(`/gene/${s}`) }
  const list = q.length >= 2 ? data || [] : []
  return (
    <div className="picker" style={{ minWidth: big ? 0 : 280 }}>
      <input ref={ref} type="search" autoFocus={autoFocus} value={q} placeholder={big ? 'Search a gene or protein — e.g. ERBB2, HER2, ENSG00000141736, P04626' : 'Gene search  ⌘K'}
        style={big ? { width: '100%', fontSize: 16, padding: '12px 14px' } : { width: '100%' }}
        onFocus={() => setFocus(true)} onBlur={() => setTimeout(() => setFocus(false), 150)} onChange={e => { setQ(e.target.value); setIdx(0) }}
        onKeyDown={e => { if (e.key === 'ArrowDown') setIdx(i => Math.min(list.length - 1, i + 1)); else if (e.key === 'ArrowUp') setIdx(i => Math.max(0, i - 1)); else if (e.key === 'Enter' && q) go(list[idx]?.symbol || q); else if (e.key === 'Escape') ref.current?.blur() }} />
      {focus && list.length > 0 && (
        <div className="pop"><ul>{list.map((g, i) => <li key={g.gene_id} className={`item ${i === idx ? 'active' : ''}`} onMouseEnter={() => setIdx(i)} onMouseDown={() => go(g.symbol)}><b>{g.symbol}</b><span className="t" style={{ marginLeft: 8 }}>{g.name}</span></li>)}</ul></div>
      )}
    </div>
  )
}
