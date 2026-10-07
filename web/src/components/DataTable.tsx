import { ReactNode, useEffect, useMemo, useState } from 'react'

export type Col<T> = { key: string; label: string; render?: (r: T, i: number) => ReactNode; num?: boolean; sort?: (r: T) => number | string | null | undefined; width?: number; title?: string }

export default function DataTable<T>({ rows, cols, rowKey, defaultSort, defaultDesc = true, highlight, onRowClick, maxHeight, pageSize = 100, loading }: {
  rows: T[]; cols: Col<T>[]; rowKey: (r: T) => string | number; defaultSort?: string; defaultDesc?: boolean; highlight?: (r: T) => boolean
  onRowClick?: (r: T) => void; maxHeight?: string | number; pageSize?: number; loading?: boolean
}) {
  const [sort, setSort] = useState<string | undefined>(defaultSort)
  const [desc, setDesc] = useState(defaultDesc)
  const [shown, setShown] = useState(pageSize)
  useEffect(() => { setShown(pageSize) }, [rows, pageSize])
  const sorted = useMemo(() => {
    if (!sort) return rows
    const c = cols.find(c => c.key === sort); if (!c) return rows
    const get = c.sort || ((r: any) => r[c.key])
    return [...rows].sort((a, b) => {
      const x = get(a), y = get(b)
      if (x == null && y == null) return 0; if (x == null) return 1; if (y == null) return -1
      const d = typeof x === 'number' && typeof y === 'number' ? x - y : String(x).localeCompare(String(y))
      return desc ? -d : d
    })
  }, [rows, sort, desc, cols])
  const click = (k: string) => {
    if (sort === k) { setDesc(!desc); return }
    const c = cols.find(c => c.key === k); const get = c?.sort || ((r: any) => r[k])
    const sample = rows.map(get).find(v => v != null)
    setSort(k); setDesc(typeof sample !== 'string')  // numbers high->low first, text A->Z first
  }
  return (
    <div>
      <div className="table-wrap" style={{ maxHeight: maxHeight ?? '72vh' }}>
        <table className="dt">
          <thead><tr>{cols.map(c => <th key={c.key} className={`${c.num ? 'num' : ''} ${sort === c.key ? 'sorted' : ''}`} style={{ width: c.width }} title={c.title} onClick={() => click(c.key)}>{c.label}{sort === c.key && <span className="arrow">{desc ? '▼' : '▲'}</span>}</th>)}</tr></thead>
          <tbody>
            {loading && rows.length === 0 && Array.from({ length: 8 }).map((_, i) => <tr key={i}>{cols.map(c => <td key={c.key}><div className="skeleton" /></td>)}</tr>)}
            {sorted.slice(0, shown).map((r, i) => (
              <tr key={rowKey(r)} className={highlight?.(r) ? 'hl' : ''} onClick={onRowClick ? () => onRowClick(r) : undefined} style={onRowClick ? { cursor: 'pointer' } : undefined}>
                {cols.map(c => <td key={c.key} className={c.num ? 'num' : c.key === 'symbol' ? 'gene' : ''}>{c.render ? c.render(r, i) : (r as any)[c.key]}</td>)}
              </tr>
            ))}
          </tbody>
        </table>
        {!loading && rows.length === 0 && <div className="empty">No rows</div>}
      </div>
      {sorted.length > shown && <div style={{ textAlign: 'center', marginTop: 8 }}><button className="btn secondary sm" onClick={() => setShown(shown + pageSize)}>Show more ({sorted.length - shown} remaining)</button></div>}
    </div>
  )
}
