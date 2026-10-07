export type Context = {
  context_id: number; context_type: string; key: string; name: string; n_members: number
  lineage?: string | null; primary_disease?: string | null; subtype?: string | null; is_normal: boolean; source: string
  gtex_v10_tissue?: string | null; gtex_toil_site?: string | null; hpa_cancer?: string | null; disease_names?: string | null
}

export const TYPE_LABELS: Record<string, string> = {
  cell_line: 'Cell lines (DepMap)', lineage: 'Lineages (DepMap)', primary_disease: 'Primary diseases (DepMap)', subtype: 'Subtypes (DepMap)',
  normal_lines: 'Non-cancerous lines (DepMap)', tcga: 'TCGA cancer types', target: 'TARGET pediatric', tcga_normal: 'TCGA adjacent normal',
  gtex_toil: 'GTEx tissues (TOIL, TCGA-matched pipeline)', gtex_tissue: 'GTEx v10 tissues (median TPM)', hpa_rna_tissue: 'HPA RNA tissue consensus',
  custom: 'Custom uploads',
}

async function get<T>(url: string): Promise<T> {
  const r = await fetch(url)
  if (!r.ok) throw new Error(`${r.status} ${await r.text()}`)
  return r.json()
}

export const api = {
  meta: () => get<any>('/api/meta'),
  contexts: (type?: string, q?: string) => get<Context[]>(`/api/contexts?${type ? `type=${encodeURIComponent(type)}&` : ''}${q ? `q=${encodeURIComponent(q)}` : ''}`),
  context: (id: number) => get<any>(`/api/contexts/${id}`),
  targets: (id: number, p: Record<string, any>) => get<any>(`/api/contexts/${id}/targets?${qs(p)}`),
  geneSearch: (q: string) => get<{ symbol: string; name: string; gene_id: number }[]>(`/api/genes/search?q=${encodeURIComponent(q)}`),
  gene: (s: string) => get<any>(`/api/genes/${encodeURIComponent(s)}`),
  geneExpr: (s: string, source: string) => get<any>(`/api/genes/${encodeURIComponent(s)}/expression?source=${source}`),
  geneRankSummary: (s: string, p: Record<string, any>) => get<any>(`/api/genes/${encodeURIComponent(s)}/rank_summary?${qs(p)}`),
  geneRank: (s: string, p: Record<string, any>) => get<any>(`/api/genes/${encodeURIComponent(s)}/rankings?${qs(p)}`),
  scatter: (p: Record<string, any>) => get<any>(`/api/explorer/scatter?${qs(p)}`),
  ranking: (p: Record<string, any>) => get<any>(`/api/explorer/ranking?${qs(p)}`),
  controls: () => get<Context[]>('/api/controls'),
}

export function qs(p: Record<string, any>) {
  return Object.entries(p).filter(([, v]) => v !== undefined && v !== null && v !== '').map(([k, v]) => `${k}=${encodeURIComponent(v)}`).join('&')
}

export const fmt = (v: any, d = 2) => (v === null || v === undefined || Number.isNaN(v) ? '–' : typeof v === 'number' ? v.toFixed(d) : String(v))
