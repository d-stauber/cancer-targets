import { useState } from 'react'
import { useQuery, useQueryClient } from '@tanstack/react-query'
import { Link } from 'react-router-dom'
import { api } from '../api'
import { Empty } from '../components/ui'

export default function Controls() {
  const qc = useQueryClient()
  const { data } = useQuery({ queryKey: ['controls'], queryFn: api.controls })
  const [name, setName] = useState(''); const [units, setUnits] = useState('tpm'); const [file, setFile] = useState<File | null>(null)
  const [msg, setMsg] = useState<{ ok: boolean; text: string } | null>(null); const [busy, setBusy] = useState(false); const [over, setOver] = useState(false)
  const submit = async () => {
    if (!file || !name) return
    setBusy(true)
    const fd = new FormData(); fd.append('file', file); fd.append('name', name); fd.append('units', units)
    const r = await fetch('/api/controls', { method: 'POST', body: fd }); const j = await r.json()
    setMsg(r.ok ? { ok: true, text: `Uploaded "${j.name}" as context ${j.context_id}: ${j.n_genes.toLocaleString()} genes mapped (columns ${j.gene_col} / ${j.value_col}).` } : { ok: false, text: j.detail })
    setBusy(false); setFile(null); setName('')
    qc.invalidateQueries({ queryKey: ['controls'] }); qc.invalidateQueries({ queryKey: ['contexts-all'] })
  }
  return (
    <div className="stack">
      <div className="page-head"><div><h1>Custom controls</h1><p className="sub">Add your own expression profiles as contexts — for example primary HMEC RNA-seq from GEO, which DepMap does not carry.</p></div></div>
      <div className="grid2">
        <div className="card">
          <h2>Upload a profile</h2>
          <div className={`dropzone ${over ? 'over' : ''}`} onDragOver={e => { e.preventDefault(); setOver(true) }} onDragLeave={() => setOver(false)}
            onDrop={e => { e.preventDefault(); setOver(false); setFile(e.dataTransfer.files?.[0] || null) }} onClick={() => document.getElementById('ctl-file')?.click()}>
            {file ? <b>{file.name}</b> : <>Drop a CSV / TSV here or click to choose<br /><span className="small faint">gene column (symbol or Ensembl id) + one numeric expression column</span></>}
            <input id="ctl-file" type="file" accept=".csv,.tsv,.txt" style={{ display: 'none' }} onChange={e => setFile(e.target.files?.[0] || null)} />
          </div>
          <div className="row" style={{ marginTop: 12 }}>
            <div className="field" style={{ flex: 1 }}><label className="lbl">Name</label><input type="text" value={name} onChange={e => setName(e.target.value)} placeholder="HMEC (GSE12345)" /></div>
            <div className="field"><label className="lbl">Units</label><select value={units} onChange={e => setUnits(e.target.value)}><option value="tpm">TPM</option><option value="log2tpm1">log2(TPM+1)</option></select></div>
            <button className="btn" onClick={submit} disabled={!file || !name || busy}>{busy ? <span className="spin" /> : 'Upload'}</button>
          </div>
          {msg && <p className={`small ${msg.ok ? 'muted' : 'error'}`} style={{ marginTop: 10 }}>{msg.text}</p>}
          <h3>Format</h3>
          <p className="small muted">First column = gene identifier, the first numeric column = expression. Values are mapped to the HGNC gene set, log-transformed, and quantile-normalised onto the GTEx reference so they are comparable with DepMap and TCGA contexts.</p>
          <pre className="small" style={{ background: 'var(--surface-2)', padding: 10, borderRadius: 6, margin: 0 }}>gene,tpm{'\n'}ERBB2,12.4{'\n'}TACSTD2,310.2{'\n'}ENSG00000141510,45.1</pre>
        </div>
        <div className="card">
          <h2>Your uploads</h2>
          {(data || []).length === 0 ? <Empty title="No uploads yet">Uploaded profiles appear here and in every context picker.</Empty> : (
            <table className="dt"><thead><tr><th>Name</th><th className="num">Context id</th><th>Use</th></tr></thead>
              <tbody>{data!.map(c => <tr key={c.context_id}><td><b>{c.name}</b></td><td className="num">{c.context_id}</td><td><Link to={`/explorer?y=${c.context_id}`}>compare in explorer</Link></td></tr>)}</tbody></table>
          )}
        </div>
      </div>
    </div>
  )
}
