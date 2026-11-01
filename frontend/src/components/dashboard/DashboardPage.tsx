import React, { useState, useEffect, useRef } from 'react'
import Plot from 'react-plotly.js'
import {
  Box, Grid, Card, CardContent, Typography, Stack, Chip, CircularProgress,
  Alert, Paper, Button, ToggleButton, ToggleButtonGroup, Table, TableHead,
  TableRow, TableCell, TableBody, Tooltip, IconButton, FormControl,
  InputLabel, Select, MenuItem, Divider
} from '@mui/material'
import DownloadIcon from '@mui/icons-material/Download'
import RefreshIcon from '@mui/icons-material/Refresh'
import { useFilter, useThemeMode } from '../../App'
import { api,
  fetchDashboardFull, fetchDashboardCostTrend,
  DashboardData, AltmanDetail
} from '../../api/client'
import CostStructureChart, { STACK_ORDER } from '../charts/CostStructureChart'

const CRORE = 10

// ── KPI Card ──────────────────────────────────────────────────────────────────
function KPICard({ label, value, sub, unit = 'INR Mn', color = '#FCD535', yoy, div = 1, themeMode, decimals = 1 }: any) {
  const fmt = (v: any) => v == null ? '—' : Number(v / div).toLocaleString('en-IN', { maximumFractionDigits: decimals })
  const isLight = themeMode === 'light'
  const cardBg   = isLight ? '#ffffff' : '#1e2329'
  const cardBdr  = isLight ? '#e0e0e0' : '#2b3139'
  const accent   = isLight ? '#0066cc' : color
  const labelClr = isLight ? '#6e6e73' : '#707a8a'
  const valClr   = isLight ? '#1d1d1f' : '#ffffff'
  const posClr   = isLight ? '#1d8348' : '#0ecb81'
  const negClr   = isLight ? '#d0021b' : '#f6465d'
  return (
    <Card sx={{ height:'100%', borderTop:`3px solid ${accent}`,
      bgcolor: cardBg, border: `1px solid ${cardBdr}`, borderTopColor: accent,
      boxShadow: 'none', borderRadius: 2 }}>
      <CardContent sx={{ pb: '12px !important', pt: 1.5, px: 1.5 }}>
        <Typography variant="caption" sx={{ color: labelClr, letterSpacing: 0.5, fontSize: 10 }}>
          {String(label).toUpperCase()}
        </Typography>
        <Typography variant="h5" fontWeight={700} sx={{ color: valClr }} mt={0.3} fontSize={20}>
          {fmt(value)}
        </Typography>
        <Stack direction="row" alignItems="center" spacing={0.5} mt={0.3} flexWrap="wrap">
          {unit && <Typography variant="caption" sx={{ color: labelClr, fontSize: 10 }}>{unit}</Typography>}
          {sub != null && (
            <Chip label={typeof sub === 'number' ? `${sub.toFixed(1)}%` : sub} size="small"
              sx={{ bgcolor: `${accent}22`, color: accent, fontWeight: 600, height: 16, fontSize: 9, borderRadius: '4px' }} />
          )}
          {yoy != null && (
            <Typography variant="caption" fontWeight={600} fontSize={9}
              sx={{ color: yoy >= 0 ? posClr : negClr }}>
              {`${yoy >= 0 ? '+' : ''}${Number(yoy).toFixed(1)}% YoY`}
            </Typography>
          )}
        </Stack>
      </CardContent>
    </Card>
  )
}

// ── Altman Z Gauge ────────────────────────────────────────────────────────────
function ZGauge({ value, zone }: { value?: number; zone?: string }) {
  const color = zone === 'safe' ? '#059669' : zone === 'grey' ? '#D97706' : '#DC2626'
  const label = zone === 'safe' ? 'SAFE ZONE' : zone === 'grey' ? 'GREY ZONE' : 'DISTRESS'
  return (
    <Box sx={{ textAlign: 'center', pt: 1 }}>
      <Typography variant="caption" fontWeight={700} color="text.secondary"
        sx={{ letterSpacing: 0.5, fontSize: 10, display: 'block', mb: 0.5 }}>
        ALTMAN Z SCORE
      </Typography>
      {!value ? (
        <Box sx={{ height: 160, display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
          <Typography color="text.secondary" fontSize={12}>No Z Score data for this company</Typography>
        </Box>
      ) : (
        <>
          <Plot data={[{
            type: 'indicator', mode: 'gauge+number', value,
            number: { font: { size: 24, color }, valueformat: '.2f' },
            gauge: {
              axis: { range: [0, 5], tickwidth: 1, tickfont: { size: 9 } },
              bar: { color },
              steps: [
                { range: [0, 1.81],  color: '#FEE2E2' },
                { range: [1.81, 2.99], color: '#FEF9C3' },
                { range: [2.99, 5],  color: '#DCFCE7' },
              ],
              threshold: { line: { color, width: 4 }, thickness: 0.75, value },
            },
          } as any]}
            layout={{ width: 280, height: 175, margin: { t: 15, b: 0, l: 25, r: 25 },
              paper_bgcolor: 'transparent', font: { family: 'Inter, -apple-system, sans-serif', size: 10, color: '#707a8a' } } as any}
            config={{ displayModeBar: false, responsive: true } as any}
          />
          <Stack direction="row" spacing={0.8} justifyContent="center" alignItems="center" mt={-0.5}>
            <Chip label={label}
              sx={{ bgcolor: color, color: '#fff', fontWeight: 700, fontSize: 10 }} size="small" />
            <Chip label={`Z = ${Number(value).toFixed(2)}`}
              sx={{ bgcolor: `${color}18`, color, fontWeight: 700, fontSize: 10,
                border: `1px solid ${color}40` }} size="small" />
          </Stack>
        </>
      )}
    </Box>
  )
}

// ── Main Component ────────────────────────────────────────────────────────────
export default function DashboardPage() {
  const { filter }  = useFilter()
  const { mode: themeMode } = useThemeMode()
  const { company: companyId, period, reportType } = filter

  // Theme-aware palette — all hardcoded dark values go through T
  const T = themeMode === 'light' ? {
    bg:       '#ffffff',
    bgAlt:    '#f5f5f7',
    bgHead:   '#f0f0f5',
    border:   '#e0e0e0',
    text:     '#1d1d1f',
    textSub:  '#6e6e73',
    accent:   '#0066cc',
    accentBg: 'rgba(0,102,204,0.10)',
    gridClr:  '#e0e0e0',
    green:    '#1d8348',
    red:      '#d0021b',
    chartFont:'#6e6e73',
    legendFont:'#6e6e73',
  } : {
    bg:       '#1e2329',
    bgAlt:    '#2b3139',
    bgHead:   '#181a20',
    border:   '#2b3139',
    text:     '#eaecef',
    textSub:  '#707a8a',
    accent:   '#FCD535',
    accentBg: 'rgba(252,213,53,0.10)',
    gridClr:  '#2b3139',
    green:    '#0ecb81',
    red:      '#f6465d',
    chartFont:'#707a8a',
    legendFont:'#929aa5',
  }

  const [data,      setData]      = useState<DashboardData | null>(null)
  const [altman,    setAltman]    = useState<AltmanDetail  | null>(null)
  const [costTrend, setCostTrend] = useState<any>(null)
  const [loading,   setLoading]   = useState(false)
  const [costLoading, setCostLoading] = useState(false)
  const [error,     setError]     = useState('')
  const [dispUnit,  setDispUnit]  = useState<'million' | 'crore'>('million')
  const [nYears, setNYears] = useState<number>(5)
  const [costReportType, setCostReportType] = useState<'consolidated'|'standalone'>(
    (reportType as any) || 'consolidated'
  )
  const [pptExporting, setPptExporting] = useState(false)
  const [ratios,        setRatios]        = useState<any>(null)
  const [ratioFrom,     setRatioFrom]     = useState<string>('')
  const [ratioTo,       setRatioTo]       = useState<string>('')
  // Guard: prevents "No Financial Data" from flashing before the first fetch
  // completes. False on mount; set to true after every load() attempt finishes.
  const [dataReady,     setDataReady]     = useState(false)
  // SVG ref — must be before any early returns (Rules of Hooks)
  const costSvgRef = useRef<SVGSVGElement>(null)
  // Tracks the LATEST company requested so stale async responses from a previous
  // company don't overwrite the current company's data. The naive pattern
  // `const requestedFor = companyId; if (requestedFor !== companyId) return` is
  // broken because both values come from the same closure and are always equal.
  const reqCompanyRef = useRef<string>('')

  const div       = dispUnit === 'crore' ? CRORE : 1
  const unitLabel = dispUnit === 'crore' ? 'INR Cr' : 'INR Mn'

  const load = () => {
    if (!companyId) return
    // Pin the company this load is for. reqCompanyRef.current always holds the
    // LATEST requested company, so callbacks from older loads can detect they're stale.
    reqCompanyRef.current = companyId
    const loadedFor = companyId   // closure capture — identifies THIS load's company

    // Clear stale data immediately so the previous company never lingers
    setData(null); setAltman(null); setCostTrend(null); setRatios(null)
    setDataReady(false); setError('')
    // Sync the cost-structure toggle to the top-bar report type on every company switch
    setCostReportType((reportType as 'consolidated' | 'standalone') || 'consolidated')
    setLoading(true); setCostLoading(false)

    // Single round-trip: backend runs all 4 computations in parallel and returns
    // {dashboard, altman, cost_trend, financial_ratios} atomically.
    fetchDashboardFull(companyId, period, reportType)
      .then((full: any) => {
        // Guard: if the user switched companies while this was in flight, discard.
        // reqCompanyRef.current = latest requested; loadedFor = this load's company.
        if (reqCompanyRef.current !== loadedFor) return

        const dash = full.dashboard || {}
        const altm = full.altman    || null
        const ct   = full.cost_trend || null
        const fr   = full.financial_ratios || null

        if (!dash.kpis && !dash.company_id) {
          setError('Dashboard data failed to load')
        }
        setData(dash as DashboardData)
        setAltman(altm as AltmanDetail)
        setCostTrend(ct)
        setRatios(fr)
        if (fr?.years?.length) {
          setRatioTo(fr.years[0])
          // Default the "From" to the oldest year that actually has data, so an empty
          // FY19 stays selectable in the dropdown but isn't shown by default. Both
          // lists are sorted newest→oldest, so the last item is the oldest.
          const dataYears: string[] = fr.data_years?.length ? fr.data_years : fr.years
          setRatioFrom(dataYears[dataYears.length - 1])
        }
      })
      .catch((e: any) => {
        if (reqCompanyRef.current !== loadedFor) return
        setError(e?.response?.data?.detail || e?.message || 'Dashboard data failed to load')
      })
      .finally(() => {
        // Only update loading state if this is still the active company
        if (reqCompanyRef.current === loadedFor) {
          setLoading(false)
          setDataReady(true)
        }
      })
  }

  const loadCostTrend = (rt?: string) => {
    if (!companyId) return
    const loadedFor = companyId   // closure capture for stale check
    setCostLoading(true)
    fetchDashboardCostTrend(companyId, rt || costReportType)
      .then(ct => {
        if (reqCompanyRef.current !== loadedFor) return
        setCostTrend(ct)
      })
      .catch(() => {
        if (reqCompanyRef.current !== loadedFor) return
        setCostTrend(null)
      })
      .finally(() => {
        if (reqCompanyRef.current === loadedFor) setCostLoading(false)
      })
  }

  useEffect(() => { load() }, [companyId, period, reportType])

  if (!companyId) return (
    <Box sx={{ display: 'flex', alignItems: 'center', justifyContent: 'center', height: 400 }}>
      <Typography color="text.secondary">Select a company in the top bar</Typography>
    </Box>
  )
  if (loading) return <Box sx={{ display: 'flex', justifyContent: 'center', py: 10 }}><CircularProgress /></Box>

  const kpis  = data?.kpis  || {}
  const trend = data?.trend  || {}
  const sortYr = (arr: any[]) => [...arr].sort((a, b) => a.year.localeCompare(b.year))
  const revData = sortYr(trend['Revenue from Operations'] || [])
  const ebdData = sortYr(trend['EBITDA'] || [])
  const patData = sortYr(trend['PAT']    || [])
  const years   = revData.map(d => d.year)

  // ── Cost structure display years ─────────────────────────────────────────
  const allYears: string[]   = costTrend?.years  || []
  // Annual years only (exclude any backend-provided Avg keys for slicing)
  const annualYears = allYears.filter(y => y !== '5Y Avg' && !y.endsWith('Y Avg'))
  const slicedYears = annualYears.slice(-nYears)

  // ── Dynamic N-Year Avg — always shown, computed from slicedYears ────────────
  // Never uses the backend's fixed "5Y Avg" — always accurate for any N
  const avgLabel = `${slicedYears.length}Y Avg`
  const avgSegments: Record<string, number> = {}
  // Revenue-weighted average: each year contributes proportionally to its revenue
  const _totalRevForAvg = slicedYears.reduce((s, yr) => s + (costTrend?.revenue?.[yr] ?? 0), 0)
  if (slicedYears.length > 0 && costTrend?.segments) {
    for (const [segKey, yearMap] of Object.entries(costTrend.segments || {})) {
      if (_totalRevForAvg > 0) {
        avgSegments[segKey] = slicedYears.reduce((s, yr) => {
          const pct = (yearMap as any)?.[yr] ?? 0
          const rev = costTrend?.revenue?.[yr] ?? 0
          return s + pct * rev
        }, 0) / _totalRevForAvg
      } else {
        const vals = slicedYears.map(yr => (yearMap as any)?.[yr] ?? 0)
        avgSegments[segKey] = vals.length > 0
          ? vals.reduce((a: number, b: number) => a + b, 0) / vals.length : 0
      }
    }
  }
  // Display average annual revenue (total / n) as the bar's revenue label
  const avgRevenue = slicedYears.length > 0
    ? _totalRevForAvg / slicedYears.length
    : 0
  // Revenue-weighted EBITDA margin average
  const avgEbitda = slicedYears.length > 0
    ? (() => {
        const yrsWithData = slicedYears.filter(yr => costTrend?.ebitda_margin?.[yr] != null)
        const wRev = yrsWithData.reduce((s, yr) => s + (costTrend?.revenue?.[yr] ?? 0), 0)
        if (wRev > 0) {
          return yrsWithData.reduce((s, yr) => {
            return s + (costTrend!.ebitda_margin![yr] as number) * (costTrend?.revenue?.[yr] ?? 0)
          }, 0) / wRev
        }
        const vals = yrsWithData.map(yr => costTrend!.ebitda_margin![yr] as number)
        return vals.length > 0 ? vals.reduce((a, b) => a + b, 0) / vals.length : undefined
      })()
    : undefined

  const displayYears = slicedYears  // avg bar added explicitly below

  // ── Auto-generated Cost Structure insight (mirrors PPT insight) ────────────
  const dashCostInsight = (() => {
    if (!costTrend || slicedYears.length === 0) return ''
    const seg = (k: string, yr: string) => (costTrend.segments?.[k] as any)?.[yr] ?? 0
    const segRaw = (k: string, yr: string): number | null => {
      const v = (costTrend.segments?.[k] as any)?.[yr]
      return (v != null && v !== undefined) ? Number(v) : null
    }
    // Revenue-weighted RM cost average — matches the 5Y Avg bar
    const rmEntries = slicedYears
      .map(yr => ({ v: segRaw('Raw Material Cost', yr), rev: (costTrend.revenue as any)?.[yr] ?? 0 }))
      .filter((e): e is { v: number; rev: number } => e.v !== null && e.v > 0)
    const _rmRevSum = rmEntries.reduce((s, e) => s + e.rev, 0)
    const rmAvg = rmEntries.length > 0
      ? (_rmRevSum > 0
          ? rmEntries.reduce((s, e) => s + e.v * e.rev, 0) / _rmRevSum
          : rmEntries.reduce((s, e) => s + e.v, 0) / rmEntries.length)
      : null

    // Revenue-weighted PBT average — includes loss years, matches the 5Y Avg bar
    const pbtEntries = slicedYears
      .map(yr => ({ v: segRaw('Operational PBT', yr), rev: (costTrend.revenue as any)?.[yr] ?? 0 }))
      .filter((e): e is { v: number; rev: number } => e.v !== null)
    const _pbtRevSum = pbtEntries.reduce((s, e) => s + e.rev, 0)
    const pbtAvg = pbtEntries.length > 0
      ? (_pbtRevSum > 0
          ? pbtEntries.reduce((s, e) => s + e.v * e.rev, 0) / _pbtRevSum
          : pbtEntries.reduce((s, e) => s + e.v, 0) / pbtEntries.length)
      : null

    const revEntries = slicedYears
      .map(yr => [yr, (costTrend.revenue as any)?.[yr] ?? 0] as [string, number])
      .filter(([, v]) => v > 0)
    let cagrStr = ''
    if (revEntries.length >= 2) {
      const n = revEntries.length - 1
      const cagrVal = (revEntries[n][1] / revEntries[0][1]) ** (1 / n) - 1
      cagrStr = `${(cagrVal * 100).toFixed(2)}%`
    }
    let s = `Average RM cost for ${companyId} (${costReportType})`
    if (rmAvg  !== null) s += ` is ~${Math.round(rmAvg)}% of revenue`
    if (pbtAvg !== null) s += ` and it is operating at ~${Math.round(pbtAvg)}% PBT margin in the last ${slicedYears.length} years`
    s += cagrStr ? `; top line has grown CAGR @ ${cagrStr}.` : '.'
    return s
  })()

  const exportCostPNG = () => {
    const svg = costSvgRef.current
    if (!svg) return
    const serializer = new XMLSerializer()
    const svgStr = serializer.serializeToString(svg)
    const svgBlob = new Blob([svgStr], { type: 'image/svg+xml;charset=utf-8' })
    const url = URL.createObjectURL(svgBlob)
    const img = new Image()
    img.onload = () => {
      const scale  = 3
      const canvas = document.createElement('canvas')
      canvas.width  = img.naturalWidth  * scale
      canvas.height = img.naturalHeight * scale
      const ctx = canvas.getContext('2d')!
      ctx.scale(scale, scale)
      ctx.fillStyle = '#ffffff'
      ctx.fillRect(0, 0, img.naturalWidth, img.naturalHeight)
      ctx.drawImage(img, 0, 0)
      URL.revokeObjectURL(url)
      const a = document.createElement('a')
      a.href = canvas.toDataURL('image/png')
      a.download = `cost_structure_${companyId}_${reportType}.png`
      a.click()
    }
    img.src = url
  }

  const exportCostPPT = () => {
    if (!costTrend?.segments) return
    setPptExporting(true)
    try {
      // Build bar data from displayYears (oldest→newest left→right) + dynamic avg
      const barsPayload = [
        ...displayYears.map(yr => ({
          barKey:       yr,
          segments:     Object.fromEntries(
            Object.entries(costTrend.segments || {})
              .map(([k, v]: [string, any]) => [k, v?.[yr] ?? 0])
          ),
          revenue:      costTrend.revenue?.[yr] ?? null,
          ebitdaMargin: costTrend.ebitda_margin?.[yr] ?? null,
          isAverage:    false,
        })),
        ...(slicedYears.length > 0 ? [{
          barKey:       avgLabel,
          segments:     avgSegments,
          revenue:      avgRevenue > 0 ? avgRevenue : null,
          ebitdaMargin: avgEbitda ?? null,
          isAverage:    true,
        }] : []),
      ]
      const yrs = displayYears.filter(y => !y.endsWith('Y Avg'))
      const subtitle = `${costReportType.charAt(0).toUpperCase()+costReportType.slice(1)} · ${yrs[0] ?? ''}–${yrs[yrs.length-1] ?? ''}${avgLabel ? ' · '+avgLabel : ''}`
      api.post('/export/cost-structure-ppt', {
        bars:     barsPayload,
        title:    `Cost Structure Analysis — ${companyId}`,
        subtitle,
        mode:     'dashboard',
      }, { responseType: 'blob', timeout: 90000 })
      .then(res => {
        const link = document.createElement('a')
        link.href = URL.createObjectURL(res.data)
        link.download = `CostStructure_${companyId}_${costReportType}.pptx`
        link.click()
        URL.revokeObjectURL(link.href)
      })
      .catch(e => alert(`PPT export failed: ${e.message}`))
      .finally(() => setPptExporting(false))
    } catch (e: any) {
      alert(`PPT export failed: ${e.message}`)
      setPptExporting(false)
    }
  }

  return (
    <Box>
      {/* ── Header ── */}
      <Stack direction="row" justifyContent="space-between" alignItems="center" mb={2.5}
        flexWrap="wrap" gap={1}>
        <Box>
          <Typography variant="h5" fontWeight={800} color="text.primary">Analytics Dashboard</Typography>
          <Typography variant="body2" color="text.secondary">
            {companyId} · {period} · {reportType === 'consolidated' ? 'Consolidated' : 'Standalone'}
          </Typography>
        </Box>
        <Stack direction="row" spacing={1.5} alignItems="center">
          <ToggleButtonGroup value={dispUnit} exclusive size="small"
            onChange={(_, v) => v && setDispUnit(v)}
            sx={{ '& .MuiToggleButton-root': { px: 1.5, py: 0.4, fontSize: 12, textTransform: 'none' } }}>
            <ToggleButton value="million">₹ Million</ToggleButton>
            <ToggleButton value="crore">₹ Crore</ToggleButton>
          </ToggleButtonGroup>
          <Button startIcon={<RefreshIcon />} onClick={load}
            variant="outlined" size="small">Refresh</Button>
        </Stack>
      </Stack>

      {error && <Alert severity="error" sx={{ mb: 2 }}>{error}</Alert>}
      {!loading && dataReady && (data?.no_data || (!kpis.revenue?.value && !kpis.total_assets?.value)) && (
        <Alert severity="info" sx={{ mb: 2, py: 1.5 }} icon={<span style={{ fontSize: 20 }}>📭</span>}>
          <strong>No data found for {companyId}</strong>
          {data?.years && data.years.length > 0
            ? ` — data exists for: ${(data.years as string[]).slice(0, 5).join(', ')}. Select a different period above.`
            : ` — go to Data Input, enter financial values, then click Analyze to process all companies.`}
        </Alert>
      )}

      {/* ── KPI Cards — Google Material Blue 800 theme ── */}
      <Grid container spacing={1.5} mb={2.5}>
        {[
          { label: 'Revenue',         value: kpis.revenue?.value,        yoy: kpis.revenue?.yoy      },
          { label: 'EBITDA',          value: kpis.ebitda?.value,         sub: kpis.ebitda?.margin    },
          { label: 'EBIT',            value: kpis.ebit?.value,           sub: kpis.ebit?.margin      },
          { label: 'PAT',             value: kpis.pat?.value,            sub: kpis.pat?.margin       },
          { label: 'Total Assets',    value: kpis.total_assets?.value,   yoy: kpis.total_assets?.yoy },
          { label: 'Net Worth',       value: kpis.net_worth?.value                                   },
          { label: 'Working Capital', value: kpis.working_capital?.value                             },
          { label: 'Current Ratio',   value: kpis.current_ratio?.value,  unit: 'Ratio', div: 1      },
          { label: 'ROE',             value: kpis.roe?.value,            unit: 'Ratio', div: 1, decimals: 2 },
        ].map(card => (
          <Grid item xs={6} sm={4} md={3} lg={2} key={card.label}>
            <KPICard {...card} color="#FCD535" themeMode={themeMode}
              unit={(card as any).unit || unitLabel} div={(card as any).div ?? div} />
          </Grid>
        ))}
        <Grid item xs={6} sm={4} md={3} lg={3}>
          <Card sx={{ height: '100%', borderTop: `3px solid ${T.accent}`, bgcolor: T.bg,
            border: `1px solid ${T.border}`, borderTopColor: T.accent, boxShadow: 'none', borderRadius: 2 }}>
            <ZGauge value={kpis.altman_z?.value ?? undefined} zone={kpis.altman_z?.zone} />
          </Card>
        </Grid>
      </Grid>

      {/* ── Revenue & EBITDA trend ── */}
      <Grid container spacing={2} mb={2}>
        <Grid item xs={12} md={6}>
          <Paper sx={{ p: 2 }}>
            <Typography variant="subtitle1" fontWeight={700} mb={1}>
              Revenue & EBITDA Trend ({unitLabel})
            </Typography>
            {revData.length > 0 ? (
              <Plot
                data={[
                  { x: years, y: revData.map(d => d.value / div), type: 'bar',
                    name: 'Revenue',
                    marker: { color: '#F2B524', opacity: 0.92, line: { width: 0 } } } as any,
                  { x: years, y: ebdData.map(d => d.value / div), type: 'scatter',
                    mode: 'lines+markers', name: 'EBITDA',
                    line: { color: '#0ecb81', width: 3 }, marker: { color: '#0ecb81', size: 7 },
                    yaxis: 'y2' } as any,
                ]}
                layout={{
                  height: 250, margin: { t: 10, b: 40, l: 70, r: 60 },
                  paper_bgcolor: 'transparent', plot_bgcolor: 'transparent',
                  yaxis: { gridcolor: T.gridClr, title: unitLabel, color: T.chartFont },
                  yaxis2: { overlaying: 'y', side: 'right', showgrid: false, color: T.chartFont },
                  legend: { x: 0, y: 1.12, orientation: 'h', font: { color: T.legendFont } },
                  xaxis: { tickangle: 0, tickfont: { size: 11 }, color: T.chartFont },
                  font: { family: 'Inter, -apple-system, sans-serif', size: 12, color: T.chartFont },
                } as any}
                style={{ width: '100%' }}
                config={{ displayModeBar: false, responsive: true } as any}
              />
            ) : (
              <Box sx={{ height: 250, display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
                <Typography color="text.secondary">No trend data available for this company</Typography>
              </Box>
            )}
          </Paper>
        </Grid>

        {/* PAT trend */}
        {patData.length > 0 && (
          <Grid item xs={12} md={6}>
            <Paper sx={{ p: 2 }}>
              <Typography variant="subtitle1" fontWeight={500} mb={1}>PAT Trend ({unitLabel})</Typography>
              <Plot
                data={[{ x: patData.map(d => d.year), y: patData.map(d => d.value / div),
                  type: 'scatter', mode: 'lines+markers', name: 'PAT',
                  line: { color: '#2dbdb6', width: 3 }, marker: { color: '#2dbdb6', size: 8 } } as any]}
                layout={{ height: 250, margin: { t: 5, b: 40, l: 70, r: 20 },
                  paper_bgcolor: 'transparent', plot_bgcolor: 'transparent',
                  yaxis: { gridcolor: T.gridClr, color: T.chartFont }, xaxis: { tickangle: 0, color: T.chartFont },
                  font: { family: 'Inter, -apple-system, sans-serif', size: 12, color: T.chartFont } } as any}
                style={{ width: '100%' }}
                config={{ displayModeBar: false, responsive: true } as any}
              />
            </Paper>
          </Grid>
        )}
      </Grid>

      {/* ══════════════════════════════════════════════════════════════════════
          COST STRUCTURE — PPT / Equity Research Style
          ══════════════════════════════════════════════════════════════════════ */}
      <Paper sx={{ p: 2.5, mb: 2 }}>
        {/* Header row */}
        <Stack direction="row" justifyContent="space-between" alignItems="flex-start"
          mb={1.5} flexWrap="wrap" gap={1}>
          <Box>
            <Typography variant="subtitle1" fontWeight={600} color="text.primary" fontSize={15}>
              Cost Structure Analysis — {companyId}
            </Typography>
            <Typography variant="caption" color="text.secondary">
              Each bar = Revenue 100% · All % of Revenue · Revenue value shown on top
            </Typography>
          </Box>
          <Stack direction="row" spacing={1} alignItems="center" flexWrap="wrap" gap={0.5}>
            <ToggleButtonGroup value={costReportType} exclusive size="small"
              onChange={(_, v) => { if (v) { setCostReportType(v); loadCostTrend(v) } }}
              sx={{ '& .MuiToggleButton-root': { px: 1.3, py: 0.4, fontSize: 11, textTransform: 'none' } }}>
              <ToggleButton value="consolidated">Consolidated</ToggleButton>
              <ToggleButton value="standalone">Standalone</ToggleButton>
            </ToggleButtonGroup>
            <FormControl size="small" sx={{ minWidth: 120 }}>
              <InputLabel sx={{ fontSize: 11 }}>Years shown</InputLabel>
              <Select
                value={nYears}
                label="Years shown"
                onChange={e => setNYears(Number(e.target.value))}
                sx={{ fontSize: 11 }}
              >
                {[1, 2, 3, 4, 5, 6].map(n => (
                  <MenuItem key={n} value={n} sx={{ fontSize: 11 }}>
                    {n} Year{n > 1 ? 's' : ''}
                  </MenuItem>
                ))}
              </Select>
            </FormControl>
            <Tooltip title="Download chart as PNG">
              <IconButton size="small" onClick={exportCostPNG}
                sx={{ border: '1px solid #E2E8F0', borderRadius: 1 }}>
                <DownloadIcon sx={{ fontSize: 16 }} />
              </IconButton>
            </Tooltip>
            <Tooltip title="Download chart as PowerPoint (.pptx)">
              <span>
                <Button size="small" onClick={exportCostPPT}
                  disabled={pptExporting}
                  variant="outlined"
                  sx={{ fontSize: 11, textTransform: 'none', minWidth: 48, px: 1,
                    borderColor: '#E2E8F0', color: '#D97706',
                    '&:hover': { borderColor: '#D97706', bgcolor: '#FFFBEB' } }}>
                  {pptExporting ? '…' : 'PPT'}
                </Button>
              </span>
            </Tooltip>
          </Stack>
        </Stack>

        {costLoading ? (
          <Box sx={{ display: 'flex', justifyContent: 'center', py: 6 }}><CircularProgress /></Box>
        ) : costTrend?.years?.length > 0 ? (
          <>
            <CostStructureChart
              bars={[
                ...displayYears.map(yr => ({
                  barKey:       yr,
                  segments:     Object.fromEntries(
                    Object.entries(costTrend.segments || {})
                      .map(([k, v]: [string, any]) => [k, v?.[yr] ?? 0])
                  ),
                  revenue:      costTrend.revenue?.[yr],
                  ebitdaMargin: costTrend.ebitda_margin?.[yr],
                })),
                // Dynamic N-Year Avg — always shown regardless of nYears
                ...(slicedYears.length > 0 ? [{
                  barKey:       avgLabel,
                  segments:     avgSegments,
                  revenue:      avgRevenue > 0 ? avgRevenue : undefined,
                  isAverage:    true,
                  ebitdaMargin: avgEbitda,
                }] : []),
              ]}
              div={div}
              unitLabel={unitLabel}
              yAxisLabel="% of Revenue"
              svgRef={costSvgRef}
            />
            {dashCostInsight && (
              <Box sx={{ mt: 1.5, px: 1.75, py: 1.25, bgcolor: '#FFFBEB', borderRadius: 1,
                border: '1px solid #FDE68A' }}>
                <Typography fontSize={14.5} sx={{ color: '#78350F', lineHeight: 1.65 }}>
                  <Box component="span" fontWeight={700}>Auto generated insights : </Box>
                  {dashCostInsight}
                </Typography>
              </Box>
            )}
          </>
        ) : (
          <Box sx={{ py: 6, textAlign: 'center' }}>
            <Typography color="text.secondary">
              No cost structure data available for this company.
            </Typography>
          </Box>
        )}

      </Paper>

      {/* ── Financial Ratios ── */}
      {(() => {
        const allRatioYears: string[] = ratios?.years || []
        // Build sorted unique FY list for dropdowns (ascending: FY20, FY21, ...)
        const fyAsc = [...allRatioYears].reverse()

        // Derive numeric bounds for filtering
        const toFY   = (s: string) => parseInt(s.replace('FY', ''), 10) || 0
        const fromN  = toFY(ratioFrom || fyAsc[0] || 'FY20')
        const toN    = toFY(ratioTo   || fyAsc[fyAsc.length - 1] || 'FY25')
        const lo = Math.min(fromN, toN)
        const hi = Math.max(fromN, toN)

        // Filtered years in ascending order (FY20 → FY25, left → right)
        const visibleYears = [...allRatioYears].reverse().filter(y => {
          const n = toFY(y); return n >= lo && n <= hi
        })

        const fmtVal = (v: any, unit: string) => {
          if (v == null) return '—'
          const n = Number(v)
          return unit === 'Days' ? n.toFixed(1) : n.toFixed(2)
        }

        return (
          <Paper sx={{ p: 2, mb: 2 }}>
            <Stack direction="row" justifyContent="space-between" alignItems="center"
              mb={1.5} flexWrap="wrap" gap={1}>
              <Box>
                <Typography variant="subtitle1" fontWeight={600} color="text.primary" fontSize={15}>
                  Financial Ratios
                </Typography>
                <Typography variant="caption" color="text.secondary">
                  Liquidity · Leverage · Efficiency · Coverage
                </Typography>
              </Box>

              {allRatioYears.length > 0 && (
                <Stack direction="row" spacing={1} alignItems="center">
                  <FormControl size="small" sx={{ minWidth: 95 }}>
                    <InputLabel sx={{ fontSize: 11 }}>From</InputLabel>
                    <Select value={ratioFrom} label="From"
                      onChange={e => setRatioFrom(e.target.value)}
                      sx={{ fontSize: 11 }}>
                      {fyAsc.map(y => (
                        <MenuItem key={y} value={y} sx={{ fontSize: 11 }}>{y}</MenuItem>
                      ))}
                    </Select>
                  </FormControl>
                  <Typography fontSize={12} color="text.secondary">—</Typography>
                  <FormControl size="small" sx={{ minWidth: 95 }}>
                    <InputLabel sx={{ fontSize: 11 }}>To</InputLabel>
                    <Select value={ratioTo} label="To"
                      onChange={e => setRatioTo(e.target.value)}
                      sx={{ fontSize: 11 }}>
                      {fyAsc.map(y => (
                        <MenuItem key={y} value={y} sx={{ fontSize: 11 }}>{y}</MenuItem>
                      ))}
                    </Select>
                  </FormControl>
                </Stack>
              )}
            </Stack>

            {ratios?.rows?.length > 0 ? (
              <Table size="small" sx={{ tableLayout: 'auto' }}>
                <TableHead>
                  <TableRow>
                    <TableCell sx={{
                      fontWeight: 600, bgcolor: T.bgHead, color: T.text,
                      fontSize: 12, py: 1, minWidth: 200,
                    }}>
                      Particulars
                    </TableCell>
                    <TableCell sx={{
                      fontWeight: 600, bgcolor: T.bgHead, color: T.text,
                      fontSize: 12, py: 1, width: 72,
                    }}>
                      Units
                    </TableCell>
                    {visibleYears.map(y => (
                      <TableCell key={y} align="right" sx={{
                        fontWeight: 600, bgcolor: T.bgHead, color: T.text,
                        fontSize: 12, py: 1, minWidth: 72,
                      }}>
                        {y}
                      </TableCell>
                    ))}
                  </TableRow>
                </TableHead>
                <TableBody>
                  {(ratios.rows as Array<{ label: string; unit: string; values: Record<string, number | null> }>)
                    .map((row, idx) => (
                    <TableRow key={row.label} sx={{
                      bgcolor: idx % 2 === 0 ? T.bgAlt : T.bg,
                      '&:hover': { bgcolor: T.accentBg },
                    }}>
                      <TableCell sx={{ fontWeight: 500, fontSize: 12.5, color: T.text, py: 0.9 }}>
                        {row.label}
                      </TableCell>
                      <TableCell sx={{ fontSize: 11.5, color: T.textSub, py: 0.9 }}>
                        {row.unit}
                      </TableCell>
                      {visibleYears.map(y => (
                        <TableCell key={y} align="right" sx={{
                          fontSize: 12.5, py: 0.9,
                          fontVariantNumeric: 'tabular-nums',
                          color: row.values[y] == null ? T.textSub : T.text,
                          fontWeight: row.values[y] != null ? 500 : 400,
                        }}>
                          {fmtVal(row.values[y], row.unit)}
                        </TableCell>
                      ))}
                    </TableRow>
                  ))}
                </TableBody>
              </Table>
            ) : (
              <Box sx={{ py: 4, textAlign: 'center' }}>
                <Typography color="text.secondary" fontSize={13}>
                  No financial ratio data available for this company.
                </Typography>
              </Box>
            )}
          </Paper>
        )
      })()}

      {/* ── Altman Z Decomposition ── */}
      {altman?.components && (
        <Paper sx={{ p: 2 }}>
          <Stack direction="row" spacing={1.5} alignItems="center" mb={1.5}>
            <Typography variant="subtitle1" fontWeight={700}>
              Altman Z Decomposition — {altman.year}
            </Typography>
            {altman.z_score != null && (
              <Chip label={`Z = ${Number(altman.z_score).toFixed(2)}`}
                sx={{ bgcolor: altman.zone === 'safe' ? '#059669' : altman.zone === 'grey' ? '#D97706' : '#DC2626',
                  color: '#fff', fontWeight: 700 }} size="small" />
            )}
          </Stack>
          <Table size="small">
            <TableHead>
              <TableRow sx={{ '& th': { fontWeight: 600, bgcolor: T.bgHead, color: T.textSub, fontSize: 12 } }}>
                <TableCell>Component</TableCell>
                <TableCell>Formula</TableCell>
                <TableCell align="right">Weight</TableCell>
                <TableCell align="right">Raw Value</TableCell>
                <TableCell align="right">Contribution</TableCell>
              </TableRow>
            </TableHead>
            <TableBody>
              {Object.entries(altman.components).map(([key, comp]: [string, any]) => {
                const contrib = comp.value != null ? comp.weight * comp.value : null
                const isX2 = key === 'X2'
                const srcColor = comp.source === 'direct' ? '#059669'
                  : comp.source === 'derived' ? '#D97706'
                  : '#94A3B8'
                const srcLabel = comp.source === 'direct' ? 'Direct'
                  : comp.source === 'derived' ? 'Derived'
                  : comp.source === 'not_available' ? 'N/A' : undefined

                // Build tooltip text for derived X2
                let ttContent = ''
                if (isX2 && comp.tooltip && typeof comp.tooltip === 'object') {
                  ttContent = Object.entries(comp.tooltip)
                    .map(([k, v]) => `${k}: ${typeof v === 'number' ? Number(v).toLocaleString('en-IN') : v}`)
                    .join('\n')
                }

                return (
                  <TableRow key={key} sx={{ '&:hover': { bgcolor: T.bgAlt } }}>
                    <TableCell>
                      <Typography fontWeight={700} fontSize={13} sx={{ color: T.accent }}>{key}</Typography>
                    </TableCell>
                    <TableCell>
                      <Stack spacing={0.3}>
                        <Typography fontSize={12} color="text.secondary">
                          {/* Show source_label for X2, name for others */}
                          {isX2 && comp.source_label
                            ? comp.source_label.split('\n')[0]
                            : comp.name}
                        </Typography>
                        {isX2 && srcLabel && (
                          <Tooltip
                            title={ttContent || comp.source_label || ''}
                            placement="right"
                            arrow
                            componentsProps={{ tooltip: { sx: { whiteSpace:'pre-line', fontSize:11 } } }}
                          >
                            <Chip
                              label={`Source: ${srcLabel}`}
                              size="small"
                              sx={{ fontSize: 10, height: 18, width: 'fit-content',
                                bgcolor: `${srcColor}18`, color: srcColor,
                                border: `1px solid ${srcColor}40`, fontWeight: 600,
                                cursor: ttContent ? 'help' : 'default' }}
                            />
                          </Tooltip>
                        )}
                      </Stack>
                    </TableCell>
                    <TableCell align="right">
                      <Typography fontSize={13}>{comp.weight}×</Typography>
                    </TableCell>
                    <TableCell align="right">
                      <Typography fontSize={13} fontWeight={500}>
                        {comp.value != null ? Number(comp.value).toFixed(4) : '—'}
                      </Typography>
                    </TableCell>
                    <TableCell align="right">
                      <Chip label={contrib != null ? Number(contrib).toFixed(3) : '—'} size="small"
                        sx={{ bgcolor: contrib && contrib > 0 ? '#ECFDF5' : contrib && contrib < 0 ? '#FEF2F2' : '#F1F5F9',
                          color: contrib && contrib > 0 ? '#059669' : contrib && contrib < 0 ? '#DC2626' : '#64748B',
                          fontWeight: 600, fontSize: 11 }} />
                    </TableCell>
                  </TableRow>
                )
              })}
              <TableRow sx={{ bgcolor: T.bgHead }}>
                <TableCell colSpan={4}>
                  <Typography fontWeight={700} fontSize={13} sx={{ color: T.text }}>Total Z Score</Typography>
                </TableCell>
                <TableCell align="right">
                  <Typography fontWeight={700} fontSize={14}
                    sx={{ color: altman.zone === 'safe' ? '#059669' : altman.zone === 'grey' ? '#D97706' : '#DC2626' }}>
                    {altman.z_score != null ? Number(altman.z_score).toFixed(2) : '—'}
                  </Typography>
                </TableCell>
              </TableRow>
            </TableBody>
          </Table>
          <Stack direction="row" spacing={1} mt={1.5}>
            {[['Safe Zone: Z > 2.99', '#059669'], ['Grey Zone: 1.81–2.99', '#D97706'], ['Distress: Z < 1.81', '#DC2626']]
              .map(([l, c]) => (
                <Box key={l} sx={{ px: 1.5, py: 0.5, bgcolor: `${c}18`, borderRadius: 1, border: `1px solid ${c}40` }}>
                  <Typography fontSize={11} fontWeight={600} sx={{ color: c }}>{l}</Typography>
                </Box>
              ))}
          </Stack>
        </Paper>
      )}

    </Box>
  )
}
