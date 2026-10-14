import { Link } from 'react-router-dom'
import { fmt } from '../api'
import DataTable, { Col } from './DataTable'

export const SENS = -1
export default function DrugTable({ rows, lfcKey = 'lfc', maxHeight = 480, showDelta = true, loading }: { rows: any[]; lfcKey?: string; maxHeight?: number | string; showDelta?: boolean; loading?: boolean }) {
  const cols: Col<any>[] = [
    { key: 'name', label: 'Compound', render: r => <><Link to={`/drug/${encodeURIComponent(r.broad_id)}`}>{r.name}</Link> <span className="gn small muted">{(r.moa || '').toLowerCase()}</span></> },
    { key: 'targets', label: 'Targets', render: r => <span className="small">{(r.targets || '').split(', ').slice(0, 4).map((g: string, i: number) => <Link key={i} to={`/gene/${g}`} style={{ marginRight: 5 }}>{g}</Link>)}{(r.targets || '').split(', ').length > 4 ? '…' : ''}</span> },
    { key: lfcKey, label: 'log2 FC here', num: true, render: r => r[lfcKey] == null ? <span className="faint">–</span> : <b style={{ color: r[lfcKey] < SENS ? 'var(--critical)' : undefined }}>{fmt(r[lfcKey])}</b>, title: 'log2 fold-change viability at 2.5 µM in this context (median over member lines for groups)' },
    { key: 'median_lfc', label: 'All lines', num: true, render: r => fmt(r.median_lfc), title: 'median log2 FC across every screened line' },
    ...(showDelta ? [{ key: 'delta_vs_all_lines', label: 'Δ vs all', num: true, render: (r: any) => fmt(r.delta_vs_all_lines), title: 'more negative = selectively sensitive here' } as Col<any>] : []),
    { key: 'frac_sensitive', label: '% lines sensitive', num: true, render: r => r.frac_sensitive == null ? '–' : `${(r.frac_sensitive * 100).toFixed(0)}%` },
    { key: 'auc', label: 'AUC', num: true, render: r => fmt(r.auc), title: 'dose-response area under curve (19Q4 secondary screen; lower = more sensitive)' },
    { key: 'n_lines', label: 'n', num: true },
  ]
  return <DataTable rows={rows} cols={cols} rowKey={r => r.broad_id} defaultSort={lfcKey} defaultDesc={false} maxHeight={maxHeight} loading={loading} />
}
