/**
 * PeerYearlyBars.tsx
 *
 * Horizontal bar charts: one card per year, companies sorted high→low.
 *
 * Color logic — continuous interpolation across 4 anchors:
 *   t=0 (min value) → #FFEFB0  lightest yellow
 *   t=⅓             → #F8C359
 *   t=⅔             → #D1933F
 *   t=1 (max value) → #9A531C  darkest brown
 *
 * t is computed per-year independently:
 *   t = (value − yearMin) / (yearMax − yearMin)
 *
 * The highest-performing company maps exactly to #9A531C;
 * the lowest maps exactly to #FFEFB0. All intermediate
 * companies are placed by interpolation, not by rank bucket.
 */

import React, { useMemo } from 'react'
import Plot from 'react-plotly.js'
import { Box, Grid, Typography } from '@mui/material'

// ── Color scale ────────────────────────────────────────────────────────────────
interface Anchor { t: number; r: number; g: number; b: number }

const ANCHORS: Anchor[] = [
  { t: 0,         r: 0xFF, g: 0xEF, b: 0xB0 },  // #FFEFB0  min / lightest
  { t: 1 / 3,    r: 0xF8, g: 0xC3, b: 0x59 },   // #F8C359
  { t: 2 / 3,    r: 0xD1, g: 0x93, b: 0x3F },   // #D1933F
  { t: 1,         r: 0x9A, g: 0x53, b: 0x1C },  // #9A531C  max / darkest
]

/** Map a normalised t ∈ [0,1] to an rgb() string along the 4-anchor scale. */
function interpolateColor(t: number): string {
  t = Math.max(0, Math.min(1, t))

  // locate the two anchors that bracket t
  let lo = ANCHORS[0]
  let hi = ANCHORS[ANCHORS.length - 1]
  for (let i = 0; i < ANCHORS.length - 1; i++) {
    if (t <= ANCHORS[i + 1].t) { lo = ANCHORS[i]; hi = ANCHORS[i + 1]; break }
  }

  const span = hi.t - lo.t
  const s    = span > 0 ? (t - lo.t) / span : 0
  const r    = Math.round(lo.r + (hi.r - lo.r) * s)
  const g    = Math.round(lo.g + (hi.g - lo.g) * s)
  const b    = Math.round(lo.b + (hi.b - lo.b) * s)
  return `rgb(${r},${g},${b})`
}

/**
 * For one year's array of values (parallel to `companies`):
 *  • find yearMin / yearMax among non-null entries
 *  • compute t = (v − min) / (max − min) for every entry
 *  • return hex/rgb color strings — null entries receive a neutral grey
 */
function yearColors(values: (number | null)[]): string[] {
  const valid = values.filter((v): v is number => v != null)
  if (!valid.length) return values.map(() => '#D1933F')

  const mn = Math.min(...valid)
  const mx = Math.max(...valid)

  return values.map(v => {
    if (v == null) return '#bdbdbd'
    const t = mx === mn ? 0.5 : (v - mn) / (mx - mn)
    return interpolateColor(t)
  })
}

// ── Types ──────────────────────────────────────────────────────────────────────
export interface SeriesEntry {
  company_id: string
  values: (number | null)[]   // parallel to `years`
}

export interface ThemePalette {
  bg:       string
  bgHead:   string
  border:   string
  text:     string
  accent:   string
  accentBg?: string
  chartFont?: string
}

export interface PeerYearlyBarsProps {
  /** All years in chronological order, e.g. ["FY20","FY21","FY22","FY23","FY24","FY25"] */
  years:       string[]
  series:      SeriesEntry[]
  trendLabel:  string
  fmtBar:      (v: number | null) => string
  T:           ThemePalette
  /** cols per row: 1, 2 (default), or 3 */
  cols?:       1 | 2 | 3
}

// ── Component ──────────────────────────────────────────────────────────────────
const PeerYearlyBars: React.FC<PeerYearlyBarsProps> = ({
  years, series, trendLabel, fmtBar, T, cols = 2,
}) => {
  // Most-recent year first
  const displayYears = useMemo(() => [...years].reverse(), [years])

  const companies = series.map(s => s.company_id)

  /** Return the value for (series-entry, year). */
  const getValue = (entry: SeriesEntry | undefined, yr: string): number | null => {
    if (!entry) return null
    const yi = years.indexOf(yr)
    if (yi < 0) return null
    const v = entry.values[yi]
    return v != null && !Number.isNaN(v) ? Number(v) : null
  }

  const gridCols = cols === 1 ? 12 : cols === 3 ? 4 : 6

  return (
    <Grid container spacing={2}>
      {displayYears.map(year => {
        // ── raw values (parallel to companies) ──
        const rawVals = companies.map(co =>
          getValue(series.find(s => s.company_id === co), year))

        const validVals = rawVals.filter((v): v is number => v != null)
        if (!validVals.length) return null

        // ── sort companies high → low for this year ──
        const ranked = companies
          .map((co, i) => ({ co, val: rawVals[i] }))
          .sort((a, b) => {
            if (a.val == null && b.val == null) return 0
            if (a.val == null) return 1
            if (b.val == null) return -1
            return b.val - a.val          // descending
          })

        const sortedCos  = ranked.map(r => r.co)
        const sortedVals = ranked.map(r => r.val)

        // ── per-year color interpolation ──
        const colors = yearColors(sortedVals)

        // ── axis extents ──
        const absVals = validVals.map(Math.abs)
        const maxAbs  = Math.max(...absVals)
        const hasNeg  = validVals.some(v => v < 0)
        const xMin    = hasNeg ? Math.min(...validVals) * 1.15 : 0
        const xMax    = maxAbs * 1.40          // room for outside labels

        // ── average ──
        const avgVal = validVals.length
          ? validVals.reduce((a, b) => a + b, 0) / validVals.length
          : null

        // ── chart height: 52 px per company + 24 px padding ──
        const chartH = Math.max(100, sortedCos.length * 52 + 24)

        // ── text color inside/outside bars ──
        // bars are amber tones — always use dark text for labels
        const labelColor = T.text

        return (
          <Grid item xs={12} sm={gridCols} key={year}>
            <Box sx={{
              border:       `1px solid ${T.border}`,
              borderRadius: '10px',
              overflow:     'hidden',
              bgcolor:      T.bg,
              display:      'flex',
              flexDirection:'column',
            }}>

              {/* ── Year header ── */}
              <Box sx={{
                bgcolor: T.bgHead, px: 2, py: 0.9,
                display: 'flex', alignItems: 'center', justifyContent: 'space-between',
              }}>
                <Typography variant="body2" fontWeight={700} sx={{ color: T.accent }} fontSize={13}>
                  {year}
                </Typography>
                {avgVal != null && (
                  <Box sx={{
                    px: 1, py: 0.25, borderRadius: '6px',
                    border: `1px solid ${T.accent}`,
                    bgcolor: T.accentBg ?? 'rgba(0,0,0,0.04)',
                  }}>
                    <Typography fontSize={11} fontWeight={600} sx={{ color: T.accent }}>
                      Avg: <strong>{fmtBar(avgVal)}</strong>
                    </Typography>
                  </Box>
                )}
              </Box>

              {/* ── Horizontal bar chart ── */}
              <Plot
                data={[{
                  type:        'bar' as const,
                  orientation: 'h'  as const,
                  // Plotly renders y-axis top-to-bottom when autorange='reversed'
                  // so index 0 = top of chart = highest value (already sorted high→low)
                  y: sortedCos,
                  x: sortedVals,
                  marker: {
                    color:   colors,
                    opacity: 1,
                    line:    { color: 'rgba(255,255,255,0.35)', width: 0.8 },
                  },
                  // value labels outside bars
                  text:         sortedVals.map(v => fmtBar(v)),
                  textposition: 'outside' as const,
                  cliponaxis:   false,
                  textfont: {
                    size:   12,
                    color:  labelColor,
                    family: 'Inter, -apple-system, sans-serif',
                    weight: 700,
                  },
                  hovertemplate: `<b>%{y}</b><br>${trendLabel}: <b>%{customdata}</b><extra></extra>`,
                  customdata: sortedVals.map(v => fmtBar(v)),
                }]}
                layout={{
                  height:        chartH,
                  margin:        { t: 8, b: 8, l: 4, r: 80 },
                  paper_bgcolor: 'transparent',
                  plot_bgcolor:  'transparent',
                  xaxis: {
                    range:          [xMin, xMax],
                    showgrid:       false,
                    zeroline:       hasNeg,
                    zerolinecolor:  T.border,
                    zerolinewidth:  1,
                    showticklabels: false,
                    fixedrange:     true,
                  },
                  yaxis: {
                    automargin: true,
                    autorange:  'reversed' as const,
                    tickfont: {
                      size:   12,
                      color:  T.text,
                      family: 'Inter, -apple-system, sans-serif',
                      weight: 700,
                    },
                    fixedrange: true,
                    tickmode:   'array',
                    tickvals:   sortedCos,
                    ticktext:   sortedCos,
                  },
                  showlegend: false,
                } as any}
                style={{ width: '100%' }}
                config={{ displayModeBar: false, responsive: true } as any}
              />

              {/* ── Color scale legend strip ── */}
              <Box sx={{
                px: 2, pb: 1.2, pt: 0.5,
                display: 'flex', alignItems: 'center', gap: 1,
              }}>
                <Typography fontSize={10} sx={{ color: T.text, opacity: 0.55, whiteSpace: 'nowrap' }}>
                  Low
                </Typography>
                <Box sx={{
                  flex: 1, height: 6, borderRadius: 3,
                  background: 'linear-gradient(to right, #FFEFB0, #F8C359, #D1933F, #9A531C)',
                }} />
                <Typography fontSize={10} sx={{ color: T.text, opacity: 0.55, whiteSpace: 'nowrap' }}>
                  High
                </Typography>
              </Box>
            </Box>
          </Grid>
        )
      })}
    </Grid>
  )
}

export default PeerYearlyBars
