import { Link } from 'react-router-dom'
import { DrugSearch } from './Drug'

const EXAMPLES = [['BRD:BRD-K19687926-379-07-4', 'Lapatinib'], ['BRD:BRD-K02113016-001-15-4', 'Olaparib'], ['BRD:BRD-K85606544-001-09-1', 'Neratinib']]
export default function DrugsHome() {
  return (
    <div className="stack">
      <div className="hero"><h1>Drug sensitivity</h1>
        <p>PRISM Repurposing screens from the Broad: 6,790 compounds × 919 DepMap cell lines at 2.5 µM (log2 fold-change viability), plus 8-point dose-response AUC / IC50 for 1,448 compounds × 489 lines. Look up a compound, compare two contexts in the <Link to="/explorer?mode=drugs">drug explorer</Link>, or open any cell line's "Drug sensitivity" panel on its rankings page.</p>
        <DrugSearch big />
        <div className="chips" style={{ justifyContent: 'center', marginTop: 10 }}>{EXAMPLES.map(([id, n]) => <Link key={id} className="chip" to={`/drug/${encodeURIComponent(id)}`}>{n}</Link>)}</div>
      </div>
      <div className="card small muted">Sensitivity calls use log2 FC &lt; −1 (about 50% viability vs DMSO). "Δ vs all" compares a line or group with the median of every screened line, so negative values flag selective sensitivity rather than general cytotoxicity. Sources: Corsello et al. 2020 (Nat Cancer) and PRISM Repurposing Public 24Q2.</div>
    </div>
  )
}
