import React, { useState, useEffect, useCallback, useRef } from 'react'
import Plot from 'react-plotly.js'
// Plotly loaded from CDN (see index.html) — available as window.Plotly
import {
  Box, Typography, Stack, Paper, Grid, FormControl, InputLabel, Select,
  MenuItem, CircularProgress, Table, TableBody, TableCell, TableHead,
  TableRow, Chip, Button, Checkbox, ListItemText, OutlinedInput,
  ToggleButton, ToggleButtonGroup, Alert, Tooltip, Snackbar
} from '@mui/material'
import { useFilter, useThemeMode } from '../../App'
import { api,
  fetchSectors, fetchCompaniesInSector, fetchCompanies,
  fetchPeerCostStructure, fetchPeerTrend,
} from '../../api/client'
import CompareArrowsIcon from '@mui/icons-material/CompareArrows'
import DownloadIcon      from '@mui/icons-material/Download'
import ImageIcon         from '@mui/icons-material/Image'
import CostStructureChart, { BarData } from '../charts/CostStructureChart'
import PeerRankedBars from '../charts/PeerRankedBars'

// ─── Constants ─────────────────────────────────────────────────────
const COST_SEGMENTS = [
  "Raw Material Cost","Consumables","Power & Fuel",
  "Transportation","Manpower","Rest in Other Expenses",
  "Finance Costs","Depreciation & Amortization",
  "Remaining Expenses","Operational PBT",
]
const COST_COLORS = [
  "#2B59C3",  // Raw Material Cost      — Blue
  "#8B5CF6",  // Consumables            — Light Purple (part of Others)
  "#6F42C1",  // Power & Fuel           — Purple (mid)
  "#D97706",  // Transportation         — Orange
  "#E02525",  // Manpower               — Red
  "#8B5CF6",  // Rest in Other Expenses — Light Purple (part of Others)
  "#1B8EA6",  // Finance Costs          — Teal/Cyan (part of Interest & Depreciation)
  "#1B8EA6",  // Depreciation           — Teal/Cyan
  "#8B5CF6",  // Remaining Expenses     — Light Purple (part of Others)
  "#138B63",  // Operational PBT        — Green
]
const COMPANY_COLORS = [
  "#F59E0B","#D97706","#F97316","#B45309",
  "#FBBF24","#EA580C","#FCD34D","#C2410C",
]
const TREND_METRICS = [
  { label: "Revenue",           value: "Revenue from Operations" },
  { label: "Revenue Growth %",  value: "Revenue Growth" },
  { label: "EBITDA",            value: "EBITDA" },
  { label: "EBITDA Margin %",   value: "EBITDA Margin" },
  { label: "EBIT",              value: "EBIT" },
  { label: "PAT",               value: "PAT" },
  { label: "PAT Margin %",      value: "PAT Margin" },
  { label: "Current Ratio",     value: "Current Ratio" },
  { label: "ROE %",             value: "ROE" },
  { label: "Working Capital",   value: "Working Capital" },
  { label: "Finance Costs",     value: "Finance Costs" },
  { label: "Altman Z Score",    value: "Altman Z Score" },
  { label: "Total Assets",      value: "Total Assets" },
  { label: "Total Equity",      value: "Total Equity" },
]
const ALL_FY = ["FY19","FY20","FY21","FY22","FY23","FY24","FY25","FY26"]

type CostMode = 'pct_revenue' | 'pct_total_cost'
const fmt = (v: any) =>
  v == null ? '—' : Number(v).toLocaleString('en-IN', { maximumFractionDigits: 1 })

// ─── Component ─────────────────────────────────────────────────────
export default function PeerPage() {
  const { filter }  = useFilter()
  const { mode: themeMode } = useThemeMode()
  const period      = filter.period
  const reportType  = filter.reportType

  const T = themeMode === 'light' ? {
    bg:       '#ffffff',
    bgAlt:    '#f5f5f7',
    bgHead:   '#f0f0f5',
    border:   '#e0e0e0',
    text:     '#1d1d1f',
    textSub:  '#6e6e73',
    accent:   '#0066cc',
    accentBg: 'rgba(0,102,204,0.08)',
    accentClr:'#ffffff',
    gridClr:  '#e0e0e0',
    chartFont:'#6e6e73',
    btnBg:    '#0066cc',
    btnText:  '#ffffff',
    btnHover: '#0071e3',
  } : {
    bg:       '#1e2329',
    bgAlt:    '#2b3139',
    bgHead:   '#181a20',
    border:   '#2b3139',
    text:     '#eaecef',
    textSub:  '#707a8a',
    accent:   '#FCD535',
    accentBg: 'rgba(252,213,53,0.10)',
    accentClr:'#181a20',
    gridClr:  '#2b3139',
    chartFont:'#707a8a',
    btnBg:    '#FCD535',
    btnText:  '#181a20',
    btnHover: '#f0b90b',
  }

  const [sectors, setSectors]             = useState<string[]>([])
  const [sector, setSector]               = useState('')
  const [availCos, setAvailCos]           = useState<any[]>([])
  const [selectedCos, setSelectedCos]     = useState<string[]>([])
  const [costMode, setCostMode]           = useState<CostMode>('pct_revenue')
  const [costData, setCostData]           = useState<any>(null)
  const [costLoading, setCostLoading]     = useState(false)
  const [exporting, setExporting]         = useState<'cost-png'|'cost-ppt'|null>(null)
  const [toast, setToast]                 = useState('')
  const [clickedSeg, setClickedSeg]       = useState<string|null>(null)
  const costPlotRef   = useRef<any>(null)
  const costSvgRef    = useRef<SVGSVGElement>(null)

  // ── Multi-company trend state ────────────────────────────────────
  const TREND_MX = [
    { label:'Revenue',                     value:'Revenue from Operations' },
    { label:'EBITDA',                      value:'EBITDA' },
    { label:'EBITDA Margin %',             value:'EBITDA Margin' },
    { label:'PAT',                         value:'PAT' },
    { label:'PAT Margin %',                value:'PAT Margin' },
    { label:'Total Assets',                value:'Total Assets' },
    { label:'Altman Z Score',              value:'Altman Z Score' },
    // ── Financial Ratios ──────────────────────────────
    { label:'ROE (Ratio)',                 value:'ROE' },
    { label:'Current Ratio',               value:'Current Ratio' },
    { label:'DSCR - On Interest Basis',    value:'DSCR - On Interest Basis' },
    { label:'Debt to Asset Ratio',         value:'Debt to Asset Ratio' },
    { label:'Interest Coverage Ratio',     value:'Interest Coverage Ratio' },
    { label:'Cash Conversion Cycle',       value:'Cash Conversion Cycle' },
    { label:'Creditors (Payables) Days',   value:'Creditors (Payables) Days' },
    { label:"Debtors (Receivables) Days",  value:"Debtors (Receivables) Days" },
    { label:'Inventory Days',              value:'Inventory Days' },
  ]
  const ALL_FY = ['FY19','FY20','FY21','FY22','FY23','FY24','FY25','FY26']
  const [trendMetric,  setTrendMetric]  = useState('Revenue from Operations')
  const [trendStart,   setTrendStart]   = useState('FY20')
  const [trendEnd,     setTrendEnd]     = useState('FY25')
  const [trendData,    setTrendData]    = useState<any>(null)
  const [trendLoading, setTrendLoading] = useState(false)
  const [trendError,   setTrendError]   = useState<string|null>(null)
  const [sortYear,     setSortYear]     = useState<string|null>(null)
  const [sortDir,      setSortDir]      = useState<'asc'|'desc'>('desc')

  const fetchTrend = useCallback(() => {
    if (!selectedCos.length) return
    setTrendLoading(true); setTrendData(null); setTrendError(null)
    fetchPeerTrend({
      companies: selectedCos,           // use exactly the companies selected on top
      metric: trendMetric, start_year: trendStart, end_year: trendEnd,
      report_type: reportType,          // consolidated / standalone from global filter
    }).then(d => setTrendData(d))
      .catch(e => setTrendError(e?.message || 'Failed to load trend data'))
      .finally(() => setTrendLoading(false))
  }, [trendMetric, trendStart, trendEnd, reportType, selectedCos])

  // Reset sort when metric changes so default behaviour applies
  useEffect(() => { setSortYear(null); setSortDir('desc') }, [trendMetric])

  // ── Load sectors ────────────────────────────────────────────────
  useEffect(() => {
    fetchSectors().then((s: string[]) => {
      const all = ['All Sectors', ...s]; setSectors(all); setSector(all[0])
    }).catch(() => {})
  }, [])

  // ── Load companies ──────────────────────────────────────────────
  useEffect(() => {
    if (!sector) return
    const p = sector === 'All Sectors' ? fetchCompanies() : fetchCompaniesInSector(sector)
    p.then((cos: any[]) => {
      const ids = cos.map((c: any) => c.company_id)
      setAvailCos(cos); setSelectedCos(ids)
    }).catch(() => {})
  }, [sector])

  // ── Fetch all data ──────────────────────────────────────────────
  const fetchAll = useCallback(() => {
    if (!selectedCos.length) return
    setCostLoading(true)
    fetchPeerCostStructure({
      companies: selectedCos, period, report_type: reportType, unit: 'absolute',
    }).then(setCostData).catch(() => setCostData(null)).finally(() => setCostLoading(false))
  }, [selectedCos, period, reportType])

  useEffect(() => {
    if (selectedCos.length && costData) fetchAll()
  }, [period, reportType])

  // ── Computed display value per segment per company ──────────────
  const cosWithData = costData ? selectedCos.filter(c => costData.data?.[c]) : []

  function segDisplayValue(co: string, seg: string): number | null {
    const d = costData?.data?.[co]
    if (!d) return null
    const raw = d[seg] ?? 0
    if (!raw) return null
    if (costMode === 'pct_revenue') {
      const rv = d['_revenue'] || 1
      return parseFloat((raw / rv * 100).toFixed(2))
    }
    if (costMode === 'pct_total_cost') {
      // If no valid total cost (company lacks cost breakdown), fall back to revenue
      const tc = (d['_total_cost'] && d['_total_cost'] > 0) ? d['_total_cost'] : d['_revenue'] || 1
      return parseFloat((raw / tc * 100).toFixed(2))
    }
    return raw
  }

  // Segments sorted descending by average value across companies (largest at bottom)
  // Sort by ABSOLUTE average across companies (consistent ordering in all 3 display modes)
  // Ascending = largest at bottom of stack (Plotly stacks from bottom up)
  const sortedSegments = [...COST_SEGMENTS].sort((a, b) => {
    const rawA = cosWithData.reduce((s, co) => {
      const d = costData?.data?.[co]; return s + ((d?.[a] ?? 0) as number)
    }, 0) / Math.max(cosWithData.length, 1)
    const rawB = cosWithData.reduce((s, co) => {
      const d = costData?.data?.[co]; return s + ((d?.[b] ?? 0) as number)
    }, 0) / Math.max(cosWithData.length, 1)
    return rawA - rawB   // ascending → largest at bottom of each stacked bar
  })

  // ── Build cost traces ─────────────────────────────────────────────
  // Pre-compute per-company segment ranks (sorted descending by raw absolute value)
  const segRanks: Record<string, Record<string, number>> = {}
  cosWithData.forEach(co => {
    const segsWithVals = COST_SEGMENTS
      .map(s => ({ s, v: costData?.data?.[co]?.[s] ?? 0 }))
      .sort((a, b) => b.v - a.v)
    segsWithVals.forEach(({ s }, i) => {
      if (!segRanks[co]) segRanks[co] = {}
      segRanks[co][s] = i + 1
    })
  })

  const costTraces = sortedSegments.map((seg) => {
    const segIdx = COST_SEGMENTS.indexOf(seg)
    const color  = COST_COLORS[segIdx % COST_COLORS.length]
    const isHi   = clickedSeg === null || clickedSeg === seg

    return {
      type: 'bar' as const,
      name: seg,
      x: cosWithData,
      y: cosWithData.map(co => segDisplayValue(co, seg)),
      marker: {
        color,
        opacity: isHi ? 0.92 : 0.25,
        line: clickedSeg === seg
          ? { color: '#F97316', width: 2.5 }
          : { color: 'rgba(0,0,0,0)', width: 0 },
      },
      // Per-trace tooltip border = segment color, giving a visual color indicator
      hoverlabel: {
        bgcolor:     '#1E293B',
        bordercolor: color,
        font: { size: 13, color: '#F8FAFC', family: '-apple-system, Arial, sans-serif' },
        align: 'left' as const,
      },
      // customdata: [company, raw_mn, pct_rev, pct_tc, rank, seg_name]
      customdata: cosWithData.map(co => {
        const d   = costData?.data?.[co]
        const raw = d?.[seg] ?? 0
        const rv  = d?.['_revenue']    || 1
        const tc  = d?.['_total_cost'] || 1
        const rk  = segRanks[co]?.[seg] ?? '—'
        return [co, raw, (raw / rv * 100).toFixed(2), (raw / tc * 100).toFixed(2), rk, seg]
      }),
      // Tooltip: Plotly strips inline style= attributes, so we cannot colour
      // individual words. Instead we use the legendgroup color as the trace's
      // hoverlabel.bordercolor (set globally below in the layout) and rely on
      // bold / structured layout for legibility.
      // customdata: [company, raw_mn, pct_rev, pct_tc, rank, seg_name]
      hovertemplate: (
        '<b>%{customdata[0]}</b><br>' +
        '<b>■ %{customdata[5]}</b><br>' +
        '<b>₹ %{customdata[1]:,.0f} Mn</b><br>' +
        '%{customdata[2]}% of Revenue<br>' +
        '%{customdata[3]}% of Total Cost<br>' +
        'Rank #%{customdata[4]} of ' + COST_SEGMENTS.length +
        '<extra></extra>'
      ),
      // Label visibility: show inside for large segments (≥ 9% of stack), hide for small ones.
      // Small segments are always readable via hover tooltip.
      text: cosWithData.map(co => {
        const v = segDisplayValue(co, seg)
        if (!v || v <= 0) return ''
        // Compute this segment's share of the full visible stack
        const stackTotal = sortedSegments.reduce(
          (s, s2) => s + (segDisplayValue(co, s2) ?? 0), 0
        ) || 1
        const pctOfStack = v / stackTotal * 100
        if (pctOfStack < 9) return ''    // too small — tooltip handles it
        return `${v.toFixed(1)}%`
      }),
      textposition: 'inside' as const,
      insidetextanchor: 'middle' as const,
      textfont:      { size: 9, color: 'white', family: '-apple-system, Arial, sans-serif' },
      outsidetextfont: { size: 9, color: T.chartFont, family: 'Inter, -apple-system, sans-serif' },
      cliponaxis:    false,
    }
  })

  // ── 100% Normalized Cost Composition Traces ─────────────────────────────
  // Each segment is a separate Plotly trace so it shows in the legend.
  // Y values are normalized to 0-100 so ALL bars have identical height —
  // even very small segments like Finance Costs remain visible.

  // ── 100% Normalized Cost Composition Traces ─────────────────────────────
  // Each segment is a separate Plotly trace so it shows in the legend.
  // Y values are normalized to 0-100 so ALL bars have identical height —
  // even very small segments like Finance Costs remain visible.
  // ── Jindal-style 100% normalized traces ─────────────────────────────────────
  // • Every bar same height (0–100%)
  // • Revenue annotation at top of each bar
  // • ALL segment % labels visible — inside if ≥ 5%, outside annotation if smaller
  // • Per-company mode (consolidated / standalone / 5yr average)
  const costNormTraces = (() => {
    if (!costData?.data || cosWithData.length === 0) return []
    const avgVal = (seg: string) =>
      cosWithData.reduce((s, co) => s + ((costData.data[co]?.[seg]) || 0), 0) / cosWithData.length
    const sorted = [...COST_SEGMENTS].sort((a, b) => avgVal(a) - avgVal(b)) // asc → largest at bottom

    return sorted.map((seg) => {
      const color = COST_COLORS[COST_SEGMENTS.indexOf(seg) % COST_COLORS.length]
      const yVals = cosWithData.map(co => {
        const d   = costData.data[co]; if (!d) return null
        const raw = d[seg] || 0
        const rv  = d['_revenue']    || 1
        const tc  = d['_total_cost'] && d['_total_cost'] > 0 ? d['_total_cost'] : rv
        const denom = costMode === 'pct_revenue' ? rv : tc
        return raw ? parseFloat((raw / denom * 100).toFixed(2)) : 0
      })
      const customData = cosWithData.map(co => {
        const d      = costData.data[co]
        const raw    = d?.[seg] || 0
        const rv     = d?.['_revenue']    || 1
        const tc     = d?.['_total_cost'] && d['_total_cost'] > 0 ? d['_total_cost'] : rv
        const pctTc  = raw ? (raw / tc  * 100).toFixed(1) : '0.0'
        const pctRev = raw ? (raw / rv  * 100).toFixed(1) : '0.0'
        const absMn  = raw ? (raw / 1000).toFixed(0) + 'K' : '0'
        return `<b>${co}</b><br><b style="color:${color}">■ ${seg}</b><br>` +
               `₹${absMn} Mn<br>${pctTc}% of Total Cost<br>${pctRev}% of Revenue`
      })
      // Labels: ALWAYS show % — inside bar if ≥ 5%, else as small outside text
      const textVals = yVals.map(v => v !== null && v > 0 ? `${(v).toFixed(0)}%` : '')
      const textPos  = yVals.map(v => (v !== null && v >= 5) ? 'inside' : 'outside') as any[]
      return {
        type:    'bar' as const, name: seg,
        x:       cosWithData, y: yVals,
        marker:  { color, opacity: 0.92 },
        customdata: customData,
        hovertemplate: '%{customdata}<extra></extra>',
        hoverlabel: { bgcolor: '#1E293B', bordercolor: color,
          font: { size: 12, color: '#F8FAFC', family: '-apple-system, Arial, sans-serif' } },
        text: textVals,
        textposition: textPos,
        insidetextanchor: 'middle' as const,
        // Inside labels: white bold; outside labels: dark colored
        textfont: { size: 10, color: 'white', family: '-apple-system, Arial, sans-serif' },
        outsidetextfont: { size: 9, color: color, family: '-apple-system, Arial, sans-serif' },
        cliponaxis: false,
      } as any
    })
  })()

  // Revenue annotations at top of each bar (like Jindal format)
  const revenueAnnotations = cosWithData.map(co => {
    const d   = costData?.data?.[co]
    const rv  = d?.['_revenue']
    if (!rv) return null
    // Display in Crores (1 Cr = 10 Mn)
    const rvCr = rv / 10
    const label = rvCr >= 100000 ? `₹${(rvCr/100000).toFixed(1)}L Cr`
                : rvCr >= 1000   ? `₹${(rvCr/1000).toFixed(1)}K Cr`
                : `₹${rvCr.toLocaleString('en-IN', { maximumFractionDigits: 0 })} Cr`
    return {
      x: co, y: 102,
      text: `<b>${label}</b>`,
      showarrow: false,
      yanchor: 'bottom' as const,
      font: { size: 10, color: T.text, family: 'Inter, -apple-system, sans-serif' },
      bgcolor: themeMode === 'light' ? 'rgba(255,255,255,0.95)' : 'rgba(30,35,41,0.9)',
      borderpad: 2,
    }
  }).filter(Boolean)

  // Totals annotation at top of each stack
  const costAnnotations = cosWithData.map(co => {
    const total = sortedSegments.reduce((s, seg) => s + (segDisplayValue(co, seg) ?? 0), 0)
    if (!total) return null
    const label = `${total.toFixed(0)}%`
    return {
      x: co, y: total,
      text: `<b>${label}</b>`,
      showarrow: false, yanchor: 'bottom' as const,
      font: { size: 11, color: T.text, family: 'Inter, -apple-system, sans-serif' },
      bgcolor: themeMode === 'light' ? 'rgba(255,255,255,0.92)' : 'rgba(30,35,41,0.85)', borderpad: 3,
    }
  }).filter(Boolean)

  const yAxisTitle = costMode === 'pct_revenue' ? '% of Revenue' : '% of Total Cost'
  const yTickFmt = '.1f'

  // ── Click handler ───────────────────────────────────────────────
  const onCostClick = useCallback((e: any) => {
    const seg = e?.points?.[0]?.data?.name
    setClickedSeg(prev => (prev === seg ? null : (seg ?? null)))
  }, [])

  // ── Export helpers ──────────────────────────────────────────────
  const downloadBlob = (buf: ArrayBuffer, filename: string, mime: string) => {
    const blob = new Blob([buf], { type: mime })
    const url  = URL.createObjectURL(blob)
    const a    = document.createElement('a'); a.href = url; a.download = filename; a.click()
    URL.revokeObjectURL(url)
  }

  // Cost structure PNG — export SVG chart via canvas
  const exportCostPNG = async () => {
    setExporting('cost-png')
    try {
      const svg = costSvgRef.current
      if (!svg) throw new Error('Chart not ready')
      const serializer = new XMLSerializer()
      const svgStr  = serializer.serializeToString(svg)
      const svgBlob = new Blob([svgStr], { type: 'image/svg+xml;charset=utf-8' })
      const url     = URL.createObjectURL(svgBlob)
      await new Promise<void>((resolve, reject) => {
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
          a.download = `cost_structure_comparison_${period}.png`
          a.click()
          resolve()
        }
        img.onerror = reject
        img.src = url
      })
      setToast('✓ Cost structure PNG downloaded')
    } catch (e: any) {
      setToast(`PNG export failed: ${e?.message || 'check console'}`)
    } finally { setExporting(null) }
  }

  // Cost structure PPT export — sends bar DATA for native PowerPoint chart
  const exportCostPPT = async () => {
    setExporting('cost-ppt')
    try {
      if (!costData?.data || cosWithData.length === 0) throw new Error('Chart data not loaded — click Go first')

      // MUST match the on-screen chart's ALL_SEGS exactly. Previously this omitted
      // 'Consumables' and 'Rest in Other Expenses' — both roll into "Others" — so the
      // PPT's Others collapsed (e.g. 0.9% vs the portal's 29.7%) and bars didn't sum
      // to 100%. Send the full set so the PPT matches the portal.
      const ALL_SEGS_PPT = [
        'Raw Material Cost','Consumables','Power & Fuel','Transportation','Manpower',
        'Rest in Other Expenses','Remaining Expenses','Finance Costs',
        'Depreciation & Amortization','Operational PBT',
      ]

      // Build peer bars — same logic as the chart render
      const pptBars = cosWithData.map((co: string) => {
        const d   = costData.data[co] || {}
        const rv  = d['_revenue'] || 0
        const denom = rv || 1
        const segPcts: Record<string, number> = {}
        ALL_SEGS_PPT.forEach((seg: string) => {
          const raw = d[seg] ?? 0
          segPcts[seg] = raw ? parseFloat((raw / denom * 100).toFixed(2)) : 0
        })
        const ebitdaMargin = d['_ebitda_margin'] != null
          ? d['_ebitda_margin'] as number
          : (d['EBITDA'] && rv > 0 ? parseFloat((d['EBITDA'] / rv * 100).toFixed(1)) : null)
        return { barKey: co, segments: segPcts, revenue: rv || null, ebitdaMargin, isAverage: false }
      })

      // Avg bar
      const avgSegs: Record<string, number> = {}
      ALL_SEGS_PPT.forEach((seg: string) => {
        const vals = pptBars.map((b: any) => b.segments[seg] || 0)
        avgSegs[seg] = parseFloat((vals.reduce((s: number, v: number) => s + v, 0) / vals.length).toFixed(2))
      })
      const avgEmVals = pptBars.map((b: any) => b.ebitdaMargin).filter((v: any) => v != null)
      const avgEm = avgEmVals.length > 0
        ? parseFloat((avgEmVals.reduce((a: number, b: number) => a + b, 0) / avgEmVals.length).toFixed(1))
        : null
      const avgRev = pptBars.reduce((s: number, b: any) => s + (b.revenue || 0), 0) / pptBars.length
      pptBars.push({ barKey: 'Ind. Avg', segments: avgSegs, revenue: avgRev || null, ebitdaMargin: avgEm, isAverage: true })

      const res = await api.post('/export/cost-structure-ppt', {
        bars:     pptBars,
        title:    `Cost Structure Comparison — ${period}`,
        subtitle: `${selectedCos.join(' · ')} · ${costMode === 'pct_revenue' ? '% of Revenue' : '% of Total Cost'} · ${reportType}`,
        mode:     'peer',
      }, { responseType: 'blob', timeout: 90000 })
      const link = document.createElement('a')
      link.href = URL.createObjectURL(res.data)
      link.download = `CostStructure_Peer_${period}.pptx`
      link.click()
      URL.revokeObjectURL(link.href)
      setToast('✓ PPT downloaded')
    } catch (e: any) {
      setToast(`PPT export failed: ${e?.message || 'check console'}`)
    } finally { setExporting(null) }
  }

  const hasData = cosWithData.length > 0

  // ── Render ──────────────────────────────────────────────────────
  return (
    <Box>
      <Typography variant="h5" fontWeight={800} color="text.primary" mb={0.5}>
        Peer Comparison
      </Typography>
      <Typography variant="body2" color="text.secondary" mb={2}>
        {period} · {reportType === 'consolidated' ? 'Consolidated' : 'Standalone'} ·
        Multi-company benchmarking
      </Typography>

      {/* ── Filters ── */}
      <Paper sx={{ p: 2, mb: 2.5 }}>
        <Grid container spacing={2} alignItems="flex-end">
          <Grid item xs={12} sm={3}>
            <FormControl fullWidth size="small">
              <InputLabel>Sector</InputLabel>
              <Select value={sector} label="Sector" onChange={e => setSector(e.target.value)}>
                {sectors.map(s => (
                  <MenuItem key={s} value={s}
                    sx={s === 'All Sectors' ? { fontWeight: 700, borderBottom: '1px solid #E2E8F0' } : {}}>
                    {s}
                  </MenuItem>
                ))}
              </Select>
            </FormControl>
          </Grid>
          <Grid item xs={12} sm={6}>
            <FormControl fullWidth size="small">
              <InputLabel>Companies</InputLabel>
              <Select multiple value={selectedCos}
                onChange={e => setSelectedCos(typeof e.target.value === 'string' ? e.target.value.split(',') : e.target.value as string[])}
                input={<OutlinedInput label="Companies" />}
                renderValue={(sel: string[]) => sel.join(', ')}
                MenuProps={{ PaperProps: { style: { maxHeight: 280 } } }}>
                {availCos.map((c: any) => (
                  <MenuItem key={c.company_id} value={c.company_id}>
                    <Checkbox checked={selectedCos.includes(c.company_id)} size="small" />
                    <ListItemText primary={c.company_id} secondary={c.company_name} />
                  </MenuItem>
                ))}
              </Select>
            </FormControl>
          </Grid>
          <Grid item xs={12} sm={2}>
            <Button variant="contained" fullWidth
              onClick={() => { setCostData(null); setClickedSeg(null); fetchAll() }}
              disabled={costLoading || !selectedCos.length}
              startIcon={costLoading
                ? <CircularProgress size={14} color="inherit" /> : <CompareArrowsIcon />}
              sx={{ bgcolor: T.btnBg, color: T.btnText, '&:hover': { bgcolor: T.btnHover }, height: 40 }}>
              Go
            </Button>
          </Grid>
        </Grid>
      </Paper>

      {!hasData && !costLoading && (
        <Alert severity="info">
          Select sector and companies above, then click <strong>Go</strong> to load charts.
          {selectedCos.length > 0 && ` (${selectedCos.length} companies selected)`}
        </Alert>
      )}

      {/* ═══════════════════════════════════════════════════════════
          SECTION 1 — Cost Structure Peer Comparison
          ═══════════════════════════════════════════════════════════ */}
      <Paper sx={{ p: 2, mb: 2.5 }}>
        <Stack direction="row" justifyContent="space-between" alignItems="center" mb={1.5} flexWrap="wrap" gap={1}>
          <Box>
            <Typography variant="subtitle1" fontWeight={600} color="text.primary">
              Cost Structure Comparison
            </Typography>
            <Typography variant="caption" color="text.secondary">
              Sorted descending · Click segment to highlight · {period}
              {clickedSeg && ` · Highlighted: ${clickedSeg}`}
            </Typography>
          </Box>
          <Stack direction="row" spacing={1} alignItems="center" flexWrap="wrap" gap={0.5}>
            {/* Display mode — 2 options only */}
            <ToggleButtonGroup value={costMode} exclusive size="small"
              onChange={(_, v) => v && setCostMode(v)}
              sx={{ '& .MuiToggleButton-root': { px: 1.2, py: 0.4, fontSize: 10.5, textTransform: 'none' } }}>
              <ToggleButton value="pct_revenue">% Revenue</ToggleButton>
              <ToggleButton value="pct_total_cost">% Total Cost</ToggleButton>
            </ToggleButtonGroup>
            {/* Cost PNG export */}
            <Tooltip title={`Download PNG — cost_structure_comparison_${period}.png`}>
              <span>
                <Button size="small" variant="outlined" startIcon={<ImageIcon />}
                  onClick={exportCostPNG}
                  disabled={exporting !== null || cosWithData.length === 0}
                  sx={{ fontSize: 10.5, textTransform: 'none', minWidth: 0, px: 1.2 }}>
                  {exporting === 'cost-png' ? '…' : 'PNG'}
                </Button>
              </span>
            </Tooltip>
            {/* Cost PPT export */}
            <Tooltip title={`Download PowerPoint — cost_structure_comparison_${period}.pptx`}>
              <span>
                <Button size="small" variant="outlined"
                  onClick={exportCostPPT}
                  disabled={exporting !== null || cosWithData.length === 0}
                  sx={{ fontSize: 10.5, textTransform: 'none', minWidth: 0, px: 1.2,
                    borderColor: '#E2E8F0', color: '#D97706',
                    '&:hover': { borderColor: '#D97706', bgcolor: '#FFFBEB' } }}>
                  {exporting === 'cost-ppt' ? '…' : 'PPT'}
                </Button>
              </span>
            </Tooltip>
          </Stack>
        </Stack>

        {costLoading ? (
          <Box sx={{ display: 'flex', justifyContent: 'center', py: 5 }}><CircularProgress /></Box>
        ) : cosWithData.length > 0 ? (() => {
          const yAxisLabel = costMode === 'pct_revenue' ? '% of Revenue' : '% of Total Cost'
          const ALL_SEGS = [
            'Raw Material Cost','Consumables','Power & Fuel',
            'Transportation','Manpower','Rest in Other Expenses',
            'Finance Costs','Depreciation & Amortization',
            'Remaining Expenses','Operational PBT',
          ]

          // Build per-company bars
          const peerBars: BarData[] = cosWithData.map(co => {
            const d   = costData?.data?.[co] || {}
            const rv  = d['_revenue']    || 0
            const tc  = (d['_total_cost'] && d['_total_cost'] > 0) ? d['_total_cost'] : rv || 1
            const denom = costMode === 'pct_revenue' ? (rv || 1) : tc
            const segPcts: Record<string, number> = {}
            ALL_SEGS.forEach(seg => {
              const raw = d[seg] ?? 0
              segPcts[seg] = raw ? parseFloat((raw / denom * 100).toFixed(2)) : 0
            })
            // EBITDA margin — use pre-computed value from backend if available
            const ebitdaMargin = d['_ebitda_margin'] != null
              ? d['_ebitda_margin'] as number
              : (d['EBITDA'] && rv > 0 ? parseFloat((d['EBITDA'] / rv * 100).toFixed(1)) : undefined)
            return { barKey: co, segments: segPcts, revenue: rv, ebitdaMargin }
          })

          // Build Industry Avg bar — revenue-weighted mean across companies
          const _totalPeerRev = peerBars.reduce((s, b) => s + (b.revenue || 0), 0)
          const avgSegs: Record<string, number> = {}
          ALL_SEGS.forEach(seg => {
            if (_totalPeerRev > 0) {
              avgSegs[seg] = parseFloat((peerBars.reduce((s, b) => {
                return s + (b.segments[seg] || 0) * (b.revenue || 0)
              }, 0) / _totalPeerRev).toFixed(2))
            } else {
              const vals = peerBars.map(b => b.segments[seg] || 0)
              avgSegs[seg] = parseFloat((vals.reduce((s, v) => s + v, 0) / vals.length).toFixed(2))
            }
          })
          // Revenue-weighted EBITDA margin average
          const _barsWithEm = peerBars.filter(b => b.ebitdaMargin != null)
          const _emRevTotal  = _barsWithEm.reduce((s, b) => s + (b.revenue || 0), 0)
          const avgEbitda = _barsWithEm.length > 0
            ? (_emRevTotal > 0
                ? parseFloat((_barsWithEm.reduce((s, b) => s + b.ebitdaMargin! * (b.revenue || 0), 0) / _emRevTotal).toFixed(1))
                : parseFloat((_barsWithEm.reduce((s, b) => s + b.ebitdaMargin!, 0) / _barsWithEm.length).toFixed(1)))
            : undefined
          const avgBar: BarData = { barKey: 'Ind. Avg', segments: avgSegs, isAverage: true, ebitdaMargin: avgEbitda }
          const allBars = [...peerBars, avgBar]

          // ── Auto-generated insight (mirrors PPT insight) ──────────────────
          const peerInsight = (() => {
            if (costMode !== 'pct_revenue' || peerBars.length === 0) return ''
            const parts: string[] = []
            const pbtBars = peerBars.filter(b => (b.segments['Operational PBT'] || 0) > 0)
            if (pbtBars.length > 0) {
              const best   = pbtBars.reduce((a, b) => (b.segments['Operational PBT'] || 0) > (a.segments['Operational PBT'] || 0) ? b : a)
              const avgPbt = pbtBars.reduce((s, b) => s + (b.segments['Operational PBT'] || 0), 0) / pbtBars.length
              let s = `${best.barKey} leads peer profitability with ${(best.segments['Operational PBT'] || 0).toFixed(1)}% Operational PBT margin vs. industry average of ${avgPbt.toFixed(1)}% — indicating superior cost management.`
              parts.push(s)
            }
            const rms = peerBars.map(b => ({ co: b.barKey, v: b.segments['Raw Material Cost'] || 0 })).filter(x => x.v > 0)
            if (rms.length > 1) {
              const lo = rms.reduce((a, b) => b.v < a.v ? b : a)
              const hi = rms.reduce((a, b) => b.v > a.v ? b : a)
              parts.push(`RM intensity ranges from ${lo.v.toFixed(1)}% (${lo.co}) to ${hi.v.toFixed(1)}% (${hi.co}) — highlighting procurement differentiation across peers.`)
            }
            if (avgEbitda != null) {
              parts.push(`Industry average EBITDA margin stands at ${avgEbitda.toFixed(1)}%.`)
            }
            return parts.join('  ')
          })()

          return (
            <>
              <CostStructureChart
                bars={allBars}
                yAxisLabel={yAxisLabel}
                svgRef={costSvgRef}
              />
              {peerInsight && (
                <Box sx={{ mt: 1.5, px: 1.75, py: 1.25, bgcolor: '#FFFBEB', borderRadius: 1,
                  border: '1px solid #FDE68A' }}>
                  <Typography fontSize={14.5} sx={{ color: '#78350F', lineHeight: 1.65 }}>
                    <Box component="span" fontWeight={700}>Auto generated insights : </Box>
                    {peerInsight}
                  </Typography>
                </Box>
              )}
            </>
          )
        })() : hasData ? (
          <Box sx={{ py: 4, textAlign: 'center' }}>
            <Typography color="text.secondary">
              No cost structure data available for selected companies/period.
            </Typography>
          </Box>
        ) : null}
      </Paper>


      {/* ── Sector Ranking ── */}
      {/* ══════════════════════════════════════════════════════════
          SECTION 3 — Multi-Company Trend Comparison
          ══════════════════════════════════════════════════════════ */}
      <Paper sx={{ p: 2, mb: 2.5 }}>
        <Box mb={1.5}>
          <Typography variant="subtitle1" fontWeight={600} color="text.primary">
            Multi-Company Trend Comparison
          </Typography>
          <Typography variant="caption" color="text.secondary">
            Bars = per-company value · Dashed line = industry average across all companies
          </Typography>
        </Box>

        <Grid container spacing={1.5} mb={1.5} alignItems="flex-end">
          <Grid item xs={12} sm={4}>
            <FormControl fullWidth size="small">
              <InputLabel>Metric</InputLabel>
              <Select value={trendMetric} label="Metric" onChange={e => setTrendMetric(e.target.value)}>
                {TREND_MX.map(m => <MenuItem key={m.value} value={m.value}>{m.label}</MenuItem>)}
              </Select>
            </FormControl>
          </Grid>
          <Grid item xs={12} sm={3}>
            <FormControl fullWidth size="small">
              <InputLabel>From</InputLabel>
              <Select value={trendStart} label="From" onChange={e => setTrendStart(e.target.value)}>
                {ALL_FY.map(y => <MenuItem key={y} value={y}>{y}</MenuItem>)}
              </Select>
            </FormControl>
          </Grid>
          <Grid item xs={12} sm={3}>
            <FormControl fullWidth size="small">
              <InputLabel>To</InputLabel>
              <Select value={trendEnd} label="To" onChange={e => setTrendEnd(e.target.value)}>
                {ALL_FY.map(y => <MenuItem key={y} value={y}>{y}</MenuItem>)}
              </Select>
            </FormControl>
          </Grid>
          <Grid item xs={12} sm={2}>
            <Button variant="contained" fullWidth onClick={fetchTrend}
              disabled={trendLoading}
              sx={{ bgcolor: T.btnBg, color: T.btnText, '&:hover':{ bgcolor: T.btnHover }, height:40, textTransform:'none', fontSize:13 }}>
              {trendLoading ? <CircularProgress size={16} color="inherit"/> : 'Load'}
            </Button>
          </Grid>
        </Grid>

        {trendLoading ? (
          <Box sx={{display:'flex',justifyContent:'center',py:6}}><CircularProgress/></Box>
        ) : trendError ? (
          <Box sx={{py:3, textAlign:'center'}}>
            <Typography color="error" fontSize={13}>{trendError}</Typography>
          </Box>
        ) : trendData?.series?.length > 0 ? (() => {
          const trendYears: string[] = trendData.years ?? []
          const trendLabel = TREND_MX.find(m => m.value === trendMetric)?.label ?? trendMetric
          const series: any[] = trendData.series.filter((s: any) =>
            s.values.some((v: any) => v != null))

          if (!series.length) return (
            <Box sx={{py:4, textAlign:'center'}}>
              <Typography color="text.secondary">No data available for selected companies and year range.</Typography>
            </Box>
          )

          // Oldest → newest left → right (FY20 … FY25)
          const displayYears = [...trendYears]

          // Metric type classification
          const isDays      = ['Cash Conversion Cycle','Creditors (Payables) Days',
                               'Debtors (Receivables) Days','Inventory Days'].includes(trendMetric)
          const isMarginPct = ['EBITDA Margin','PAT Margin','Revenue Growth'].includes(trendMetric)
          // ROE is shown as a ratio (PAT / Net Worth), matching the dashboard card
          const isPureRatio = ['Current Ratio','DSCR - On Interest Basis','Interest Coverage Ratio',
                               'Debt to Asset Ratio','Altman Z Score','ROE'].includes(trendMetric)

          // Bar label with units
          const fmtBar = (v: number | null): string => {
            if (v == null) return ''
            if (isDays)      return `${Math.round(v)} Days`
            if (isMarginPct) return `${Math.round(v)}%`
            if (isPureRatio) return v.toFixed(2)
            // INR Million → Crores
            const cr = v / 10
            if (Math.abs(cr) >= 10000) return `₹${(cr / 1000).toFixed(1)}K Cr`
            return `₹${Math.round(cr).toLocaleString('en-IN')} Cr`
          }
          // Table cell: same units as bar labels
          const fmtCell = (v: number | null): string => {
            if (v == null) return '—'
            if (isDays)      return `${Math.round(v)} Days`
            if (isMarginPct) return `${Math.round(v)}%`
            if (isPureRatio) return v.toFixed(2)
            const cr = v / 10
            if (Math.abs(cr) >= 10000) return `₹${(cr / 1000).toFixed(1)}K Cr`
            return `₹${Math.round(cr).toLocaleString('en-IN')} Cr`
          }

          const companies = series.map((s: any) => s.company_id)

          const getValue = (s: any, year: string): number | null => {
            const yi = trendYears.indexOf(year)
            if (yi < 0) return null
            const v = s.values[yi]
            return (v != null && !isNaN(v)) ? Number(v) : null
          }

          const avgForYear = (year: string): number | null => {
            const vals = series.map((s: any) => getValue(s, year)).filter((v): v is number => v != null)
            return vals.length ? parseFloat((vals.reduce((a, b) => a + b, 0) / vals.length).toFixed(2)) : null
          }

          // Lower-is-better: shorter cycles/days and lower debt ratio are "best"
          const lowerIsBetter = isDays || trendMetric === 'Debt to Asset Ratio'

          // Rank 1 = best; for lowerIsBetter metrics smallest value wins
          const ranksByYear: Record<string, Record<string, number>> = {}
          const totalRankedByYear: Record<string, number> = {}
          for (const yr of trendYears) {
            const entries = series
              .map((s: any) => ({ co: s.company_id, v: getValue(s, yr) }))
              .filter((e): e is { co: string; v: number } => e.v != null && e.v !== 0)
              .sort((a, b) => lowerIsBetter ? a.v - b.v : b.v - a.v)
            ranksByYear[yr] = {}
            entries.forEach((e, i) => { ranksByYear[yr][e.co] = i + 1 })
            totalRankedByYear[yr] = entries.length
          }

          // Active sort column — default to most-recent year (rightmost = last element)
          const activeSortYear = (sortYear && trendYears.includes(sortYear))
            ? sortYear : displayYears[displayYears.length - 1]

          // Sort series rows by the active column
          const sortedSeries = [...series].sort((a, b) => {
            const va = getValue(a, activeSortYear)
            const vb = getValue(b, activeSortYear)
            if (va == null && vb == null) return 0
            if (va == null) return 1
            if (vb == null) return -1
            return sortDir === 'desc' ? vb - va : va - vb
          })

          return (
            <Box sx={{ overflowX: 'auto' }}>
              <Typography variant="subtitle2" fontWeight={600} color="text.primary" mb={1}>
                {trendLabel} — Summary Table
              </Typography>
              <Table size="small" sx={{ minWidth: 360 }}>
                <TableHead>
                  <TableRow>
                    <TableCell sx={{
                      bgcolor: T.bgHead, color: T.text, fontWeight: 600,
                      fontSize: 12, minWidth: 130, position: 'sticky', left: 0, zIndex: 1,
                    }}>
                      Company
                    </TableCell>
                    {displayYears.map((yr: string) => {
                      const isActive = yr === activeSortYear
                      return (
                        <TableCell key={yr} align="right"
                          onClick={() => {
                            if (yr === activeSortYear) setSortDir(d => d === 'desc' ? 'asc' : 'desc')
                            else { setSortYear(yr); setSortDir('desc') }
                          }}
                          sx={{
                            bgcolor: T.bgHead, color: isActive ? T.accent : T.text,
                            fontWeight: 600, fontSize: 12, minWidth: 110,
                            cursor: 'pointer', userSelect: 'none',
                            '&:hover': { bgcolor: T.accentBg },
                          }}>
                          <Box component="span" sx={{ display: 'inline-flex', alignItems: 'center', gap: 0.25 }}>
                            {yr}
                            <Box component="span" sx={{
                              fontSize: 9, lineHeight: 1, ml: 0.25,
                              color: isActive ? T.accent : T.textSub,
                            }}>
                              {isActive ? (sortDir === 'desc' ? '▼' : '▲') : '⇅'}
                            </Box>
                          </Box>
                        </TableCell>
                      )
                    })}
                  </TableRow>
                </TableHead>
                <TableBody>
                  {sortedSeries.map((s: any) => (
                    <TableRow key={s.company_id}
                      sx={{ '&:nth-of-type(odd)': { bgcolor: T.bgAlt } }}>
                      <TableCell sx={{
                        fontWeight: 700, fontSize: 12, color: T.text,
                        position: 'sticky', left: 0, bgcolor: 'inherit',
                      }}>
                        {s.company_id}
                      </TableCell>
                      {displayYears.map((yr: string) => {
                        const v      = getValue(s, yr)
                        const rank   = (v != null && v !== 0) ? ranksByYear[yr]?.[s.company_id] : undefined
                        const total  = totalRankedByYear[yr] ?? 0
                        const isTop    = rank === 1
                        const isBottom = rank != null && rank === total && total > 1
                        const rankColor = isTop ? '#16a34a' : isBottom ? '#dc2626' : T.accent
                        const cellBg   = isTop    ? 'rgba(34,197,94,0.10)'
                                       : isBottom ? 'rgba(239,68,68,0.08)' : undefined
                        return (
                          <TableCell key={yr} align="right" sx={{
                            fontSize: 12,
                            color: v != null ? T.text : T.textSub,
                            bgcolor: cellBg,
                          }}>
                            {fmtCell(v)}
                            {rank != null && (
                              <Box component="span" sx={{
                                ml: 0.75, fontSize: 10, fontWeight: 700,
                                color: rankColor,
                                opacity: isTop || isBottom ? 1 : 0.85,
                              }}>
                                #{rank}
                              </Box>
                            )}
                          </TableCell>
                        )
                      })}
                    </TableRow>
                  ))}
                  {/* Industry Avg — fixed at bottom, excluded from ranking */}
                  <TableRow sx={{ bgcolor: T.bgHead, borderTop: `2px solid ${T.accent}` }}>
                    <TableCell sx={{
                      fontWeight: 700, fontSize: 12, color: T.accent,
                      position: 'sticky', left: 0, bgcolor: T.bgHead,
                    }}>
                      Ind. Avg
                    </TableCell>
                    {displayYears.map((yr: string) => {
                      const avg = avgForYear(yr)
                      return (
                        <TableCell key={yr} align="right"
                          sx={{ fontSize: 12, fontWeight: 600, color: T.accent }}>
                          {fmtCell(avg)}
                        </TableCell>
                      )
                    })}
                  </TableRow>
                </TableBody>
              </Table>
            </Box>
          )
        })() : trendData ? (
          <Box sx={{py:4, textAlign:'center'}}>
            <Typography color="text.secondary">No data for selected metric and year range.</Typography>
          </Box>
        ) : (
          <Box sx={{py:4, textAlign:'center'}}>
            <Typography color="text.secondary">
              Select metric and year range, then click <strong>Load</strong>.
            </Typography>
          </Box>
        )}
      </Paper>

      {/* Toast */}
      <Snackbar open={!!toast} autoHideDuration={3500} onClose={() => setToast('')}
        message={toast} anchorOrigin={{ vertical: 'bottom', horizontal: 'right' }} />
    </Box>
  )
}
