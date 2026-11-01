import axios from 'axios'

// Production build: frontend is served from the same FastAPI server on port 8000.
// So API calls use a relative base URL (empty string = same origin).
// Dev mode (VITE_API_URL set, or running on port 3000): proxy handles routing.
const isDev = import.meta.env.DEV
const BASE = import.meta.env.VITE_API_URL || (isDev ? 'http://localhost:8000' : '')

export const api = axios.create({
  baseURL: BASE,
  headers: { 'Content-Type': 'application/json' },
})

// ── Types ─────────────────────────────────────────────────────────────
export interface Company {
  company_id: string
  company_name: string
  ticker: string
  sectors: Array<{ sector: string; sub_sector: string }>
  sectors_display: string
  active_flag: number
}

export interface InputRow {
  company_id: string
  period_label: string
  financial_item: string
  category: string
  value: number | null
  units: string
  parent_item?: string | null
  sort_order?: number
}

export interface KPI {
  value?: number | null
  yoy?: number | null
  margin?: number | null
  unit?: string
}

export interface DashboardData {
  company_id: string
  no_data?: boolean
  message?: string
  latest_year: string
  years: string[]
  kpis: {
    revenue?: KPI
    ebitda?: KPI
    pat?: KPI
    total_assets?: KPI
    net_worth?: KPI
    current_ratio?: { value?: number }
    working_capital?: KPI
    altman_z?: { value?: number; zone?: string }
    ebit?: KPI
    roe?: KPI
    total_equity?: KPI
  }
  trend: Record<string, Array<{ year: string; value: number }>>
  cost_structure: Array<{ item: string; value: number }>
  report_type?: string
}

export interface AltmanDetail {
  year: string
  z_score: number | null
  zone: string
  components: Record<string, { value: number | null; weight: number; name: string }>
  z_trend: Array<{ year: string; value: number }>
}

// ── Company ──────────────────────────────────────────────────────────
export const fetchCompanies = () => api.get<Company[]>('/company').then(r => r.data)
export const fetchCompany   = (id: string) => api.get(`/company/${id}`).then(r => r.data)
export const createCompany  = (data: any) => api.post('/company', data).then(r => r.data)

// ── Peer comparison dedicated endpoints ──────────────────────────────────────
export interface PeerCostRequest {
  companies: string[]; period: string; report_type: string; unit: string;
  company_modes?: Record<string, string>
}
export interface PeerMetricRequest {
  companies: string[]; metrics: string[]; period: string; report_type: string
}
export interface PeerTrendRequest {
  companies: string[]; metric: string; start_year: string; end_year: string; report_type: string
}
export const fetchPeerTrend = (req: PeerTrendRequest) =>
  api.post('/peer/trend', req).then(r => r.data)

export const fetchPeerCostStructure = (req: PeerCostRequest) =>
  api.post('/peer/cost-structure', req).then(r => r.data)

export const fetchPeerMultiMetric = (req: PeerMetricRequest) =>
  api.post('/peer/multi-metric', req).then(r => r.data)

export const exportPeerPNG = (req: any) =>
  api.post('/peer/export/png', req, { responseType: 'arraybuffer', timeout: 120000 }).then(r => r.data)

export const exportPeerPPT = (req: any) =>
  api.post('/peer/export/ppt', req, { responseType: 'arraybuffer', timeout: 120000 }).then(r => r.data)

export const fetchSectors   = () => api.get('/company/sectors/list').then(r => r.data)
export const fetchCompaniesInSector = (sector: string) =>
  api.get(`/company/sector/${sector}/companies`).then(r => r.data)

// ── Financial Input ──────────────────────────────────────────────────
export const fetchTemplate = (companyId: string, mode = 'annual') =>
  api.get(`/financial-input/template/${companyId}?mode=${mode}`).then(r => r.data)

export const fetchWorkspace = (companyId: string, mode = 'annual', reportType = 'consolidated') =>
  api.get(`/financial-input/workspace/${companyId}?mode=${mode}&report_type=${reportType}`).then(r => r.data)

export const invalidateCache = (companyId: string) =>
  api.post(`/calculate/invalidate/${companyId}`).then(r => r.data)
export const fetchInputData = (companyId: string, period: string) =>
  api.get(`/financial-input/${companyId}/${period}`).then(r => r.data)
export const saveRow    = (row: InputRow) => api.post('/financial-input', row).then(r => r.data)
export const bulkSave   = (rows: InputRow[]) =>
  api.post('/financial-input/bulk', { rows }).then(r => r.data)
export const clearInput = (companyId: string, period: string) =>
  api.delete(`/financial-input/${companyId}/${period}`).then(r => r.data)

// ── Calculate ────────────────────────────────────────────────────────
export const calculate        = (companyId: string, period: string) =>
  api.post(`/calculate/${companyId}/${period}`).then(r => r.data)
export const calculateAll     = (companyId: string) =>
  api.post(`/calculate/all/${companyId}`).then(r => r.data)
export const calculateAllCompanies = () =>
  api.post('/calculate/all-companies', {}, { timeout: 600000 }).then(r => r.data)
export const calculateFromWarehouse = (companyId: string) =>
  api.post(`/calculate/warehouse/${companyId}`).then(r => r.data)
export const deleteCompany    = (companyId: string) =>
  api.delete(`/company/${companyId}`).then(r => r.data)

// ── Dashboard ────────────────────────────────────────────────────────
export const fetchDashboardCostTrend = (companyId: string, reportType = 'consolidated') =>
  api.get(`/dashboard/${companyId}/cost-trend`, { params: { report_type: reportType } }).then(r => r.data)

export const fetchDashboard = (companyId: string, period?: string, reportType = 'consolidated') =>
  api.get<DashboardData>(`/dashboard/${companyId}`, {
    params: { period, report_type: reportType }
  }).then(r => r.data)

export const fetchAltmanDetail = (companyId: string, period?: string) =>
  api.get<AltmanDetail>(`/dashboard/${companyId}/altman`, {
    params: { period }
  }).then(r => r.data)

export const fetchMultiPeer = (companies: string[], metrics: string[], period: string) =>
  api.get('/dashboard/peer/multi', {
    params: {
      companies: companies.join(','),
      metrics: metrics.join(','),
      period,
    }
  }).then(r => r.data)

export const fetchSectorRanking = (sector: string, period = 'FY25') =>
  api.get(`/dashboard/sector/${sector}/ranking`, { params: { period } }).then(r => r.data)

export const fetchHealthScore = (companyId: string, period?: string) =>
  api.get(`/dashboard/${companyId}/health-score`, { params: { period } }).then(r => r.data)

export const fetchFinancialRatios = (companyId: string, reportType = 'consolidated') =>
  api.get(`/dashboard/${companyId}/financial-ratios`, { params: { report_type: reportType } }).then(r => r.data)

/** Single-call endpoint: returns {dashboard, altman, cost_trend, financial_ratios} in one round-trip. */
export const fetchDashboardFull = (companyId: string, period?: string, reportType = 'consolidated') =>
  api.get(`/dashboard/${companyId}/full`, {
    params: { period, report_type: reportType }
  }).then(r => r.data)

// ── Notes ────────────────────────────────────────────────────────────
export const fetchNotes = (companyId: string, period?: string) =>
  api.get(`/notes/${companyId}`, { params: period ? { period } : {} }).then(r => r.data)
export const saveNote = (data: { company_id: string; period_label: string; note: string; page?: string }) =>
  api.post('/notes', data).then(r => r.data)
export const deleteNote = (id: number) => api.delete(`/notes/${id}`).then(r => r.data)

// ── Peer multi ───────────────────────────────────────────────────────
export const fetchMultiPeerData = (companies: string[], metrics: string[], period: string) =>
  api.get('/dashboard/peer/multi', {
    params: { companies: companies.join(','), metrics: metrics.join(','), period }
  }).then(r => r.data)

export const fetchPeerComparison = (sector: string, item: string, period: string) =>
  api.get(`/dashboard/peer/${sector}/${item}/${period}`).then(r => r.data)
// ── Export with explicit MIME type on Blob ────────────────────────────
// When axios receives a binary response with responseType:'blob', the Blob
// type is '' unless explicitly set. Adobe and some browsers check Blob.type,
// not just the file extension — an empty-type PDF shows "unsupported format".
// Fix: re-wrap blob with explicit MIME type AFTER validating magic bytes.

async function _downloadExport(
  url: string,
  expectedMime: string,
  magicBytes: number[],
): Promise<Blob> {
  const r = await api.post(url, {}, { responseType: 'arraybuffer', timeout: 90000 })
  const buf = r.data as ArrayBuffer
  const bytes = new Uint8Array(buf)

  // Validate magic bytes (PDF: %PDF = 25 50 44 46, xlsx: PK = 50 4B)
  const ok = magicBytes.every((b, i) => bytes[i] === b)
  if (!ok) {
    // Server returned an error as JSON — parse and throw
    try {
      const text = new TextDecoder().decode(bytes)
      const json = JSON.parse(text)
      throw new Error(json?.detail || 'Export generation failed on server')
    } catch (_) {
      throw new Error(`Invalid ${expectedMime} file received (got ${bytes[0]?.toString(16)} ${bytes[1]?.toString(16)})`)
    }
  }

  // Re-wrap with explicit MIME type so Adobe/browsers recognise it
  return new Blob([buf], { type: expectedMime })
}

export const exportExcel = (companyId: string, period?: string, reportType = 'consolidated') =>
  _downloadExport(
    `/export/excel/${companyId}?${period ? `period=${period}&` : ''}report_type=${reportType}`,
    'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
    [0x50, 0x4B],  // PK zip magic
  )

export const exportPPT = (companyId: string, period?: string, reportType = 'consolidated') =>
  _downloadExport(
    `/export/ppt/${companyId}?${period ? `period=${period}&` : ''}report_type=${reportType}`,
    'application/vnd.openxmlformats-officedocument.presentationml.presentation',
    [0x50, 0x4B],  // PK zip magic
  )

export const exportPDF = (companyId: string, period?: string, reportType = 'consolidated') =>
  _downloadExport(
    `/export/pdf/${companyId}?${period ? `period=${period}&` : ''}report_type=${reportType}`,
    'application/pdf',
    [0x25, 0x50, 0x44, 0x46],  // %PDF magic
  )

export const fetchExportLogs = (companyId: string) =>
  api.get(`/export/logs/${companyId}`).then(r => r.data)

// ── Utility ──────────────────────────────────────────────────────────
export const downloadBlob = (blob: Blob, filename: string) => {
  const url = URL.createObjectURL(blob)
  const a   = document.createElement('a')
  a.href = url; a.download = filename; a.click()
  setTimeout(() => URL.revokeObjectURL(url), 1000)
}
