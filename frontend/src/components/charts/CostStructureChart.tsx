/**
 * CostStructureChart.tsx  — Theme-aware
 *
 * Stack order (bottom → top): Others → Transportation → Manpower →
 *   Power & Fuel → Raw Material Cost → Interest & Dep → Operational PBT
 *
 * Label placement rules:
 *  • Any segment whose rendered pixel height < MIN_LABEL_H gets a right-side
 *    leader line instead of an inside label.
 *  • Leaders use a straight diagonal line from the segment mid-point to the
 *    label; each bar's leaders are de-overlapped then clamped so they never
 *    leave the 0%–top-of-bar zone.
 *  • Negative PBT is drawn as a dashed box BELOW the 0% baseline.
 */

import React, { useRef, useState, useCallback } from 'react'
import { Box, Typography, Stack } from '@mui/material'
import { useThemeMode } from '../../App'

// ── Segment stack ─────────────────────────────────────────────────────────────
export const STACK_ORDER: Array<{
  displayKey: string; label: string; color: string; sourceKeys: string[]
}> = [
  { displayKey:'Others',                 label:'Others',                 color:'#8B5CF6',
    sourceKeys:['Remaining Expenses','Rest in Other Expenses','Consumables'] },
  { displayKey:'Transportation',         label:'Transportation',         color:'#D97706',
    sourceKeys:['Transportation'] },
  { displayKey:'Manpower',               label:'Manpower',               color:'#E02525',
    sourceKeys:['Manpower'] },
  { displayKey:'Power & Fuel',           label:'Power & Fuel',           color:'#6F42C1',
    sourceKeys:['Power & Fuel'] },
  { displayKey:'Raw Material Cost',      label:'Raw Material Cost',      color:'#2B59C3',
    sourceKeys:['Raw Material Cost'] },
  { displayKey:'Interest & Depreciation',label:'Interest & Depreciation',color:'#1B8EA6',
    sourceKeys:['Finance Costs','Depreciation & Amortization'] },
  { displayKey:'Operational PBT',        label:'Operational PBT',        color:'#138B63',
    sourceKeys:['Operational PBT'] },
]
const PBT_KEY = 'Operational PBT'

// ── Layout constants ──────────────────────────────────────────────────────────
const TOTAL_BAR_H  = 420
const BAR_W        = 84
const BAR_GAP      = 80    // wider gap so leader labels never crowd the next bar
const MARGIN_L     = 90
const MARGIN_T     = 56
const MARGIN_B     = 96
const RIGHT_PAD    = 70    // extra room for the last bar's leader labels
const LABEL_PX     = 11    // uniform font size for ALL percentage labels
const BADGE_R      = 22
const BADGE_GAP    = 12
const MIN_LABEL_H  = 18    // pixel height below which a segment gets a leader line
const LEADER_SP    = 14    // minimum vertical gap between adjacent leader label centres
const LEADER_X     = 20    // horizontal distance from bar edge to leader label

const LIGHT_SEGS   = new Set(['#FDE68A','#FCD34D','#FBBF24'])
const OP_PBT_COLOR = STACK_ORDER.find(s => s.displayKey === PBT_KEY)!.color
const COST_DEFS    = STACK_ORDER.filter(s => s.displayKey !== PBT_KEY)

const segPct = (segments: Record<string, number>, sourceKeys: string[]) =>
  sourceKeys.reduce((s, k) => s + (segments[k] ?? 0), 0)

// ── Types ─────────────────────────────────────────────────────────────────────
export interface BarData {
  barKey:        string
  segments:      Record<string, number>
  revenue?:      number
  isAverage?:    boolean
  ebitdaMargin?: number
}

export interface CostStructureChartProps {
  bars:        BarData[]
  div?:        number
  unitLabel?:  string
  yAxisLabel?: string
  svgRef?:     React.RefObject<SVGSVGElement>
}

interface TT {
  svgX: number; svgY: number; label: string
  pctRev: number; pctCost: number; absVal: number
  barKey: string; div: number; unitLabel: string
}

interface Leader { midY: number; labelY: number; text: string; color: string }

// ── De-overlap helper ─────────────────────────────────────────────────────────
// Spreads leaders vertically so no two centres are closer than LEADER_SP px,
// then clamps the whole group so it stays between topY and botY.
function deOverlap(leaders: Leader[], topY: number, botY: number) {
  if (!leaders.length) return
  leaders.sort((a, b) => a.midY - b.midY)          // top → bottom

  // Push labels down from the top
  let prev = -Infinity
  for (const l of leaders) {
    l.labelY = Math.max(l.midY, prev + LEADER_SP)
    prev = l.labelY
  }

  // Clamp overflow: if the bottom label is below botY, shift everything up.
  // No secondary downward shift — it cascades and pushes cost labels into the
  // negative-PBT zone below baseY, causing visual collisions.
  const overflow = leaders[leaders.length - 1].labelY - botY
  if (overflow > 0) {
    for (const l of leaders) l.labelY -= overflow
  }
}

// ── Component ─────────────────────────────────────────────────────────────────
const CostStructureChart: React.FC<CostStructureChartProps> = ({
  bars, div = 1, unitLabel = 'INR Mn', yAxisLabel = '% of Revenue', svgRef: extRef,
}) => {
  const { mode: themeMode } = useThemeMode()
  const isLight = themeMode === 'light'

  const C = isLight ? {
    gridLine:'#d8d8dc', line100:'#94a3b8', line0:'#64748b', axisLabel:'#3a3a3c',
    revLabel:'#1d1d1f', yearLabel:'#1d1d1f', avgYearLabel:'#0066cc',
    avgSeparator:'#b0b0ba', legendText:'#1d1d1f', legendBorder:'#d0d0d8',
    tooltipBg:'#1E293B', tooltipText:'#F8FAFC', ebitdaGreen:'#059669',
  } : {
    gridLine:'#2b3139', line100:'#5b6673', line0:'#8a9ab0', axisLabel:'#707a8a',
    revLabel:'#eaecef', yearLabel:'#eaecef', avgYearLabel:'#FCD535',
    avgSeparator:'#2b3139', legendText:'#eaecef', legendBorder:'#2b3139',
    tooltipBg:'#1E293B', tooltipText:'#F8FAFC', ebitdaGreen:'#059669',
  }

  const internalRef = useRef<SVGSVGElement>(null)
  const svgRef      = extRef ?? internalRef
  const [tt, setTt] = useState<TT | null>(null)

  const nBars = bars.length
  const svgW  = MARGIN_L + nBars * (BAR_W + BAR_GAP) - BAR_GAP + RIGHT_PAD
  const svgH  = MARGIN_T + TOTAL_BAR_H + MARGIN_B

  // ── Dynamic Y scale ───────────────────────────────────────────────────────
  const barCostMax = (b: BarData) => {
    const pbt = b.segments[PBT_KEY] ?? 0
    if (pbt >= 0) return 100
    return COST_DEFS.reduce((s, d) => s + Math.max(0, segPct(b.segments, d.sourceKeys)), 0)
  }
  const maxCost  = Math.max(100, ...bars.map(barCostMax))
  const Y_MAX    = maxCost > 100.5 ? Math.ceil((maxCost + 3) / 5) * 5 : 100
  const minPbt   = Math.min(0, ...bars.map(b => b.segments[PBT_KEY] ?? 0))
  const Y_MIN    = minPbt < -0.5 ? Math.floor((minPbt - 2) / 5) * 5 : 0
  const RANGE    = Y_MAX - Y_MIN
  const pxPerPct = TOTAL_BAR_H / RANGE

  const yAt   = (pct: number) => MARGIN_T + TOTAL_BAR_H - (pct - Y_MIN) * pxPerPct
  const baseY = yAt(0)
  const y100  = yAt(100)

  const yTicks: number[] = []
  for (let t = Y_MIN; t < 0; t += 5)      yTicks.push(t)
  for (let t = 0; t <= 100.001; t += 20)  yTicks.push(t)

  const chartBottom = MARGIN_T + TOTAL_BAR_H
  const badgeY      = chartBottom + BADGE_GAP + BADGE_R

  const onMove = useCallback((
    e: React.MouseEvent<SVGElement>, barKey: string, label: string,
    pctRev: number, pctCost: number, absVal: number,
  ) => {
    const rect = svgRef.current!.getBoundingClientRect()
    setTt({ svgX: e.clientX - rect.left + 14, svgY: e.clientY - rect.top - 8,
      label, pctRev, pctCost, absVal, barKey, div, unitLabel })
  }, [div, unitLabel, svgRef])
  const onLeave = useCallback(() => setTt(null), [])

  return (
    <Box sx={{ position:'relative', width:'100%', overflowX:'auto' }}>
      <Box sx={{ display:'flex', alignItems:'flex-start', gap: 2 }}>
        <svg ref={svgRef} width={svgW} height={svgH}
          style={{ fontFamily:'Inter, sans-serif', display:'block', flexShrink: 0 }}>

        {/* ── Y-axis ── */}
        {yTicks.map(t => {
          const yp    = yAt(t)
          const is100 = t === 100
          const is0   = t === 0
          return (
            <g key={t}>
              <line x1={MARGIN_L} x2={svgW - 6} y1={yp} y2={yp}
                stroke={is100 ? C.line100 : is0 ? C.line0 : C.gridLine}
                strokeWidth={is100 || is0 ? 1.5 : 1}
                strokeDasharray={is100 ? '5 3' : undefined} />
              <text x={MARGIN_L - 6} y={yp + 4} textAnchor="end"
                fontSize={11} fontWeight={is100 || is0 ? 700 : 400}
                fill={C.axisLabel}>{t}%</text>
            </g>
          )
        })}
        <text x={14} y={MARGIN_T + TOTAL_BAR_H / 2} textAnchor="middle"
          fontSize={11} fill={C.axisLabel}
          transform={`rotate(-90,14,${MARGIN_T + TOTAL_BAR_H / 2})`}>{yAxisLabel}</text>

        {/* ── Row labels ── */}
        <text x={MARGIN_L - 10} y={MARGIN_T - 18} textAnchor="end"
          fontSize={12} fontWeight={600} fill={C.axisLabel}>Ops Revenue</text>
        <text x={MARGIN_L - 10} y={badgeY + 4} textAnchor="end"
          fontSize={12} fontWeight={700} fill={C.ebitdaGreen}>EBITDA %</text>

        {bars.map((bar, bi) => {
          const barX    = MARGIN_L + bi * (BAR_W + BAR_GAP)
          const xOffset = bar.isAverage ? barX + 14 : barX
          const isAvg   = !!bar.isAverage
          const rv      = bar.revenue || 0
          const em      = bar.ebitdaMargin

          const costSegs = COST_DEFS
            .map(d => ({ ...d, pct: segPct(bar.segments, d.sourceKeys) }))
            .filter(s => s.pct > 0)
          const C_cost  = costSegs.reduce((s, x) => s + x.pct, 0)
          const pbtPct  = bar.segments[PBT_KEY] ?? 0
          const isLoss  = pbtPct < 0
          const pbtDef  = STACK_ORDER.find(s => s.displayKey === PBT_KEY)!

          // Normalise so all bars sum to 100%.
          // • Positive-PBT: if (costs + PBT) > 100 scale everything down.
          // • Loss bar: costs should reach exactly (100 − |PBT|); if the warehouse
          //   line items sum to more (data gap where sub-items exceed Total Cost),
          //   scale them down proportionally so the bar still reaches 100%.
          const stackTotal   = !isLoss ? (C_cost + Math.max(0, pbtPct)) : 0
          const lossExpected = isLoss  ? (100 - pbtPct) : 0   // e.g. 105 when pbtPct=-5
          const scale = (!isLoss && stackTotal > 100.1)         ? 100 / stackTotal
            : (isLoss && lossExpected > 0 && C_cost > lossExpected + 0.5) ? lossExpected / C_cost
            : 1.0

          const drawSegs = (!isLoss && pbtPct > 0)
            ? [...costSegs, { ...pbtDef, pct: pbtPct }]
            : costSegs

          // ── Build segment elements + collect leaders ──────────────────────
          const leaders: Leader[] = []
          let cum = 0

          const segEls = drawSegs.map((seg) => {
            const origPct    = seg.pct
            const displayPct = origPct * scale
            const labelPct   = Math.round(displayPct)   // label matches the normalised bar height
            const yB  = yAt(cum)
            const yT  = yAt(cum + displayPct)
            cum += displayPct
            const h    = yB - yT                        // pixel height of segment
            const midY = (yB + yT) / 2
            const pctCost = C_cost > 0 && seg.displayKey !== PBT_KEY
              ? (origPct / C_cost) * 100 : 0
            const absVal  = rv ? (origPct / 100) * rv : 0
            const lightText = LIGHT_SEGS.has(seg.color)

            // Use pixel height to decide inside vs. leader (immune to Y-range changes)
            const useLeader = h < MIN_LABEL_H
            if (useLeader) {
              leaders.push({ midY, labelY: midY,
                text: `${labelPct}%`, color: seg.color })
            }

            return (
              <g key={seg.displayKey}
                onMouseMove={e => onMove(e as any, bar.barKey, seg.label, origPct, pctCost, absVal)}
                onMouseLeave={onLeave} style={{ cursor:'default' }}>
                <rect x={xOffset} y={yT} width={BAR_W} height={Math.max(h, 0.5)}
                  fill={seg.color} fillOpacity={isAvg ? 0.70 : 1}
                  stroke={isAvg ? 'none' : 'rgba(255,255,255,0.25)'} strokeWidth={0.5} />
                {!useLeader && (
                  <text x={xOffset + BAR_W / 2} y={midY}
                    textAnchor="middle" dominantBaseline="central"
                    fontSize={LABEL_PX} fontWeight={800}
                    fill={lightText ? '#3a2000' : '#ffffff'}
                    stroke={lightText ? 'none' : 'rgba(0,0,0,0.35)'}
                    strokeWidth={lightText ? 0 : 2.5} strokeLinejoin="round" paintOrder="stroke"
                    pointerEvents="none">
                    {labelPct}%
                  </text>
                )}
              </g>
            )
          })

          // ── Negative PBT box below the 0% baseline ───────────────────────
          let lossEl: React.ReactNode = null
          if (isLoss) {
            const yTop  = baseY
            const yBot  = yAt(pbtPct)
            const hLoss = yBot - yTop
            const midY  = (yTop + yBot) / 2
            const showInside = hLoss >= MIN_LABEL_H
            lossEl = (
              <g onMouseMove={e => onMove(e as any, bar.barKey, 'Operational PBT',
                    pbtPct, 0, rv ? (pbtPct / 100) * rv : 0)}
                 onMouseLeave={onLeave} style={{ cursor:'default' }}>
                <rect x={xOffset} y={yTop} width={BAR_W} height={Math.max(hLoss, 0.5)}
                  fill={OP_PBT_COLOR} fillOpacity={0.45}
                  stroke={isLight ? '#b7791f' : '#FCD34D'} strokeWidth={1.4}
                  strokeDasharray="4 2" />
                {showInside ? (
                  <text x={xOffset + BAR_W / 2} y={midY}
                    textAnchor="middle" dominantBaseline="central"
                    fontSize={LABEL_PX} fontWeight={800} fill="#3a2000" pointerEvents="none">
                    {Math.round(pbtPct)}%
                  </text>
                ) : (
                  // Small loss: straight leader line in the negative zone
                  <g pointerEvents="none">
                    <line x1={xOffset + BAR_W} y1={midY}
                      x2={xOffset + BAR_W + LEADER_X - 3} y2={midY}
                      stroke={OP_PBT_COLOR} strokeWidth={1} opacity={0.8} />
                    <text x={xOffset + BAR_W + LEADER_X} y={midY}
                      dominantBaseline="central"
                      fontSize={LABEL_PX} fontWeight={700} fill={C.legendText}>
                      {Math.round(pbtPct)}%
                    </text>
                  </g>
                )}
              </g>
            )
          }

          // ── De-overlap cost-zone leaders, then render as diagonal lines ───
          // Clamp zone: from just below y100 down to 8px above baseY (clear of negative PBT zone)
          deOverlap(leaders, y100 + 2, baseY - 8)

          const xStem  = xOffset + BAR_W          // connector starts at bar edge
          const xLabel = xStem + LEADER_X          // label column (fixed offset)

          const leaderEls = leaders.map((l, li) => (
            <g key={`ld-${li}`} pointerEvents="none">
              {/* Diagonal line from segment midpoint to label */}
              <line x1={xStem} y1={l.midY} x2={xLabel - 3} y2={l.labelY}
                stroke={l.color} strokeWidth={1} opacity={0.75} />
              {/* Dot at bar edge to anchor the line */}
              <circle cx={xStem} cy={l.midY} r={1.8}
                fill={l.color} opacity={0.85} />
              <text x={xLabel} y={l.labelY} dominantBaseline="central"
                fontSize={LABEL_PX} fontWeight={700} fill={C.legendText}>
                {l.text}
              </text>
            </g>
          ))

          // Revenue label
          const rvCr  = rv / 10
          const rvFmt = rv > 0
            ? `₹${rvCr.toLocaleString('en-IN', { maximumFractionDigits: 0 })} Cr` : null

          // Average bar outline: 0%–100% zone only
          const avgOutline = isAvg ? (
            <rect x={xOffset} y={y100} width={BAR_W} height={baseY - y100}
              fill="none" stroke="#F97316" strokeWidth={2.5} rx={2} />
          ) : null
          const separator = isAvg ? (
            <line x1={xOffset - 10} x2={xOffset - 10} y1={MARGIN_T} y2={chartBottom}
              stroke={C.avgSeparator} strokeWidth={1} strokeDasharray="4 3" />
          ) : null

          const badgeText = em != null ? `${em.toFixed(1)}%` : null
          const emNeg     = em != null && em < 0

          return (
            <g key={bar.barKey}>
              {separator}
              {segEls}
              {lossEl}
              {leaderEls}
              {avgOutline}

              {rvFmt && (
                <text x={xOffset + BAR_W / 2} y={MARGIN_T - 18} textAnchor="middle"
                  fontSize={12} fontWeight={700} fill={C.revLabel}>{rvFmt}</text>
              )}

              {badgeText && (
                <g>
                  <circle cx={xOffset + BAR_W / 2} cy={badgeY} r={BADGE_R}
                    fill={emNeg ? 'rgba(220,38,38,0.15)' : isAvg ? 'rgba(249,115,22,0.15)' : 'rgba(5,150,105,0.15)'}
                    stroke={emNeg ? '#DC2626' : isAvg ? '#F97316' : '#059669'} strokeWidth={2.2} />
                  <text x={xOffset + BAR_W / 2} y={badgeY} textAnchor="middle" dominantBaseline="central"
                    fontSize={13} fontWeight={700}
                    fill={emNeg ? '#DC2626' : isAvg ? '#EA580C' : '#059669'}>{badgeText}</text>
                </g>
              )}

              <text x={xOffset + BAR_W / 2} y={badgeY + BADGE_R + 14} textAnchor="middle"
                fontSize={13} fontWeight={700} fontStyle={isAvg ? 'italic' : 'normal'}
                fill={isAvg ? C.avgYearLabel : C.yearLabel}>{bar.barKey}</text>
            </g>
          )
        })}
        </svg>

        {/* ── Legend ── */}
        <Box sx={{ display:'flex', flexDirection:'column', gap:'8px',
          pt:`${MARGIN_T + 8}px`, flexShrink:0, minWidth:168 }}>
          {[...STACK_ORDER].reverse().map(s => (
            <Stack key={s.displayKey} direction="row" spacing={0.8} alignItems="center">
              <Box sx={{ width:14, height:14, borderRadius:'3px', bgcolor:s.color,
                flexShrink:0, border:`1px solid ${C.legendBorder}` }} />
              <Typography fontSize={12} fontWeight={600} sx={{ color:C.legendText }} lineHeight={1.2}>
                {s.label}
              </Typography>
            </Stack>
          ))}
        </Box>
      </Box>

      {/* ── Tooltip ── */}
      {tt && (
        <Box sx={{ position:'absolute', left:tt.svgX, top:tt.svgY,
          bgcolor:C.tooltipBg, color:C.tooltipText, borderRadius:'6px', p:'8px 12px',
          fontSize:12, lineHeight:1.7, pointerEvents:'none', zIndex:200,
          boxShadow:'0 4px 14px rgba(0,0,0,0.4)', minWidth:164 }}>
          <Typography fontSize={14} fontWeight={700} sx={{ color:C.tooltipText }} mb={0.2}>
            {tt.barKey}
          </Typography>
          <Typography fontSize={13} fontWeight={600} sx={{ color:'#CBD5E1' }} mb={0.1}>
            {tt.label}
          </Typography>
          {Math.abs(tt.absVal) > 0 && (
            <Typography fontSize={12} sx={{ color:'#CBD5E1' }}>
              ₹{(tt.absVal / tt.div).toLocaleString('en-IN', { maximumFractionDigits: 0 })} {tt.unitLabel}
            </Typography>
          )}
          <Typography fontSize={12} sx={{ color:'#CBD5E1' }}>
            {tt.pctRev.toFixed(1)}% of Revenue
          </Typography>
          {tt.pctCost > 0 && (
            <Typography fontSize={12} sx={{ color:'#CBD5E1' }}>
              {tt.pctCost.toFixed(1)}% of Total Cost
            </Typography>
          )}
        </Box>
      )}
    </Box>
  )
}

export default CostStructureChart
