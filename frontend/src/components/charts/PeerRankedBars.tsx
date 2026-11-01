/**
 * PeerRankedBars.tsx
 *
 * Horizontal bar charts — one card per time period — with rank-based
 * discrete color shading.
 *
 * Color logic
 * ──────────────────────────────────────────────────────────────────
 * For each period independently:
 *   1. Sort companies descending by value  (Rank 1 = highest).
 *   2. Generate N evenly-spaced discrete color steps between:
 *        Rank 1  →  #9A531C  (darkest brown)
 *        Rank N  →  #FFEFB0  (lightest yellow)
 *      step i (0-based):  t = i / (N − 1)
 *      rgb = lerp(#9A531C, #FFEFB0, t)
 *   3. Assign color[i] to the company at rank i+1.
 *
 * Guarantees obvious differentiation between adjacent ranks even when
 * their numerical values are nearly identical, because color is driven
 * by ordinal position, not value proximity.
 *
 * UI rules (per spec):
 *   ✓  Company name on Y-axis
 *   ✓  Value label at end of each bar
 *   ✓  Average indicator box — top-right of each period card
 *   ✗  No color-scale strip / gradient key / "Low – High" label
 */

import React, { useMemo } from 'react'
import Plot from 'react-plotly.js'
import { Box, Grid, Typography } from '@mui/material'

// ── Color engine ───────────────────────────────────────────────────────────────

const DARK_ANCHOR  = { r: 0x9A, g: 0x53, b: 0x1C } // #9A531C  Rank 1
const LIGHT_ANCHOR = { r: 0xFF, g: 0xEF, b: 0xB0 } // #FFEFB0  Rank N

/**
 * Generate exactly N evenly-spaced colors.
 *   colors[0]   → darkest  (#9A531C) — Rank 1 (highest value)
 *   colors[N-1] → lightest (#FFEFB0) — Rank N (lowest value)
 */
function generateRankColors(n: number): string[] {
  if (n === 0) return []
  if (n === 1) return [`rgb(${DARK_ANCHOR.r},${DARK_ANCHOR.g},${DARK_ANCHOR.b})`]

  return Array.from({ length: n }, (_, i) => {
    const t = i / (n - 1)                                   // 0 → darkest, 1 → lightest
    const r = Math.round(DARK_ANCHOR.r + (LIGHT_ANCHOR.r - DARK_ANCHOR.r) * t)
    const g = Math.round(DARK_ANCHOR.g + (LIGHT_ANCHOR.g - DARK_ANCHOR.g) * t)
    const b = Math.round(DARK_ANCHOR.b + (LIGHT_ANCHOR.b - DARK_ANCHOR.b) * t)
    return `rgb(${r},${g},${b})`
  })
}

// ── Types ──────────────────────────────────────────────────────────────────────

export interface SeriesEntry {
  /** The company / entity identifier shown on the Y-axis */
  company_id: string
  /** Values parallel to the `periods` array passed to the component */
  values: (number | null)[]
}

export interface PeerRankedBarsProps {
  /**
   * Ordered list of period labels, e.g. ["FY20","FY21","FY22","FY23","FY24","FY25"].
   * The component displays them in reverse (most-recent first).
   */
  periods: string[]
  series:  SeriesEntry[]

  /** Human-readable metric name shown in tooltip and heading */
  metricLabel: string

  /** Format a raw number into a display string (e.g. "₹1,234 Cr", "12.3%") */
  formatValue: (v: number | null) => string

  /** Number of chart cards per row.  Default: 2. */
  cols?: 1 | 2 | 3

  // ── Theme palette ─────────────────────────────────────────────────
  /** Card background color */
  bgCard:     string
  /** Card header background color */
  bgHeader:   string
  /** Border color for card outlines and zero-line */
  borderColor: string
  /** Primary text color used for axis labels and value labels */
  textColor:  string
  /** Accent color used for the period heading and Average badge */
  accentColor: string
  /** Accent background for the Average badge */
  accentBg:   string
}

// ── Component ──────────────────────────────────────────────────────────────────

const PeerRankedBars: React.FC<PeerRankedBarsProps> = ({
  periods,
  series,
  metricLabel,
  formatValue,
  cols = 2,
  bgCard,
  bgHeader,
  borderColor,
  textColor,
  accentColor,
  accentBg,
}) => {
  // Show most-recent period first
  const displayPeriods = useMemo(() => [...periods].reverse(), [periods])

  // Grid column span: 12 / cols
  const colSpan = cols === 1 ? 12 : cols === 3 ? 4 : 6

  return (
    <Grid container spacing={2.5}>
      {displayPeriods.map(period => {
        // ── 1. Collect raw values for this period ──────────────────
        const pi = periods.indexOf(period)

        const allEntries = series.map(s => ({
          company: s.company_id,
          value:   pi >= 0 && s.values[pi] != null && !Number.isNaN(s.values[pi])
                     ? Number(s.values[pi])
                     : null,
        }))

        // ── 2. Filter nulls/zeros then sort descending (Rank 1 = highest) ─
        // value===0 means no data for this company/year — exclude from chart
        const ranked = allEntries
          .filter((e): e is { company: string; value: number } => e.value != null && e.value !== 0)
          .sort((a, b) => b.value - a.value)

        if (!ranked.length) return null

        const n = ranked.length

        // ── 3. Generate N evenly-spaced rank colors ────────────────
        const rankColors = generateRankColors(n)

        // Arrays in top-to-bottom display order (Rank 1 at top)
        const sortedCompanies = ranked.map(r => r.company)
        const sortedValues    = ranked.map(r => r.value)
        const sortedColors    = rankColors   // colors[0] → Rank 1

        // ── 4. Compute average ─────────────────────────────────────
        const avg = ranked.reduce((sum, r) => sum + r.value, 0) / n

        // ── 5. X-axis range with headroom for outside labels ───────
        const hasNeg = sortedValues.some(v => v < 0)
        const maxAbs = Math.max(...sortedValues.map(Math.abs))
        const xMax   = maxAbs * 1.42          // 42 % headroom for text labels
        const xMin   = hasNeg
          ? Math.min(...sortedValues.filter(v => v < 0)) * 1.18
          : 0

        // ── 6. Chart height: 48 px per company + 16 px padding ─────
        const chartHeight = Math.max(90, n * 48 + 16)

        return (
          <Grid item xs={12} sm={colSpan} key={period}>

            {/* ── Card wrapper ── */}
            <Box sx={{
              bgcolor:      bgCard,
              border:       `1px solid ${borderColor}`,
              borderRadius: '10px',
              overflow:     'hidden',
              display:      'flex',
              flexDirection:'column',
            }}>

              {/* ── Header row: period label + Average badge ── */}
              <Box sx={{
                bgcolor:        bgHeader,
                px:             2,
                py:             0.85,
                display:        'flex',
                alignItems:     'center',
                justifyContent: 'space-between',
                borderBottom:   `1px solid ${borderColor}`,
              }}>
                {/* Period label */}
                <Typography
                  fontSize={13}
                  fontWeight={700}
                  sx={{ color: accentColor, letterSpacing: '-0.1px' }}
                >
                  {period}
                </Typography>

                {/* Average indicator box */}
                <Box sx={{
                  px:           1.25,
                  py:           0.3,
                  borderRadius: '6px',
                  border:       `1.5px solid ${accentColor}`,
                  bgcolor:      accentBg,
                  display:      'flex',
                  alignItems:   'center',
                  gap:          0.4,
                }}>
                  <Typography fontSize={10.5} sx={{ color: accentColor, opacity: 0.75 }}>
                    Avg
                  </Typography>
                  <Typography fontSize={11.5} fontWeight={700} sx={{ color: accentColor }}>
                    {formatValue(avg)}
                  </Typography>
                </Box>
              </Box>

              {/* ── Plotly horizontal bar chart ── */}
              <Plot
                data={[{
                  type:        'bar' as const,
                  orientation: 'h'  as const,

                  // Plotly draws y-axis top→bottom when autorange='reversed'
                  // so index 0 (Rank 1) appears at the top.
                  y: sortedCompanies,
                  x: sortedValues,

                  marker: {
                    color: sortedColors,
                    opacity: 1,
                    line: {
                      // thin white separator between bar and background
                      color: 'rgba(255,255,255,0.5)',
                      width: 0.6,
                    },
                  },

                  // Value labels positioned outside the bar end
                  text:         sortedValues.map(v => formatValue(v)),
                  textposition: 'outside' as const,
                  cliponaxis:   false,
                  textfont: {
                    size:   12,
                    color:  textColor,
                    family: 'Inter, -apple-system, BlinkMacSystemFont, sans-serif',
                    weight: 700,
                  },

                  hovertemplate:
                    `<b>%{y}</b><br>${metricLabel}: <b>%{customdata}</b><extra></extra>`,
                  customdata: sortedValues.map(v => formatValue(v)),
                }]}

                layout={{
                  height:        chartHeight,
                  margin:        { t: 6, b: 6, l: 4, r: 72 },
                  paper_bgcolor: 'transparent',
                  plot_bgcolor:  'transparent',

                  xaxis: {
                    range:          [xMin, xMax],
                    showgrid:       false,
                    zeroline:       hasNeg,
                    zerolinecolor:  borderColor,
                    zerolinewidth:  1,
                    showticklabels: false,
                    fixedrange:     true,
                  },

                  yaxis: {
                    automargin: true,
                    autorange:  'reversed' as const, // Rank 1 stays at top
                    fixedrange: true,
                    tickmode:   'array',
                    tickvals:   sortedCompanies,
                    ticktext:   sortedCompanies,
                    tickfont: {
                      size:   12,
                      color:  textColor,
                      family: 'Inter, -apple-system, BlinkMacSystemFont, sans-serif',
                      weight: 700,
                    },
                  },

                  showlegend: false,
                } as any}

                style={{ width: '100%' }}
                config={{ displayModeBar: false, responsive: true } as any}
              />
            </Box>
          </Grid>
        )
      })}
    </Grid>
  )
}

export default PeerRankedBars
