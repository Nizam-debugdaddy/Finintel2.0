import Plot from "react-plotly.js"
import React, { useState, useEffect } from 'react'
import {
  Box, Typography, Grid, Paper, Stack, Chip, CircularProgress, Alert,
  Table, TableHead, TableRow, TableCell, TableBody, FormControl,
  InputLabel, Select, MenuItem
} from '@mui/material'
import { fetchDashboard, DashboardData } from '../../api/client'
import { useFilter } from '../../App'




function calcCAGR(start: number, end: number, n: number) {
  if (!start || !end || n <= 0) return null
  return (Math.pow(end / start, 1 / n) - 1) * 100
}


export default function AdvancedAnalyticsPage() {
  const { filter } = useFilter()
  const companyId = filter.company
  const [data, setData]     = useState<DashboardData|null>(null)
  const [loading, setLoading] = useState(false)
  const [metric, setMetric] = useState('Revenue from Operations')

  useEffect(() => {
    if (!companyId) return
    setLoading(true)
    fetchDashboard(companyId).then(setData).catch(console.error).finally(() => setLoading(false))
  }, [companyId])

  if (!companyId) return (
    <Box sx={{ display:'flex', alignItems:'center', justifyContent:'center', height:300 }}>
      <Typography color="text.secondary">Select a company</Typography>
    </Box>
  )
  if (loading) return <Box sx={{ display:'flex', justifyContent:'center', py:8 }}><CircularProgress /></Box>
  if (!data) return <Alert severity="info">Run analysis first</Alert>

  const trend = data.trend || {}
  const available = Object.keys(trend).filter(k => trend[k].length >= 2)

  // Deduplicated metric data — already deduplicated in backend
  const metricData = [...(trend[metric]||[])].sort((a,b)=>a.year.localeCompare(b.year))
  const years = metricData.map(d => d.year)
  const values = metricData.map(d => d.value)

  const cagr = metricData.length >= 2
    ? calcCAGR(metricData[0].value, metricData[metricData.length-1].value, metricData.length-1)
    : null

  // YoY — one entry per year transition, no duplicates
  const yoyRates = metricData.slice(1).map((d, i) => ({
    year: d.year,
    rate: metricData[i].value ? ((d.value - metricData[i].value) / Math.abs(metricData[i].value)) * 100 : 0,
  }))

  const rolling = metricData.map((d,i) => {
    if (i < 2) return null
    const avg = (metricData[i].value + metricData[i-1].value + metricData[i-2].value) / 3
    return { year: d.year, value: avg }
  }).filter(Boolean) as Array<{year:string;value:number}>

  const fmt = (v: any) => v==null ? '—' : Number(v).toLocaleString('en-IN',{maximumFractionDigits:1})

  return (
    <Box>
      <Typography variant="h5" fontWeight={700} color="#ffffff" mb={1}>Advanced Analytics</Typography>
      <Typography variant="body2" color="text.secondary" mb={3}>{companyId} · Trend Analysis · CAGR</Typography>

      <Stack direction="row" spacing={2} mb={3}>
        <FormControl size="small" sx={{ minWidth:280 }}>
          <InputLabel>Metric</InputLabel>
          <Select value={metric} label="Metric" onChange={e => setMetric(e.target.value)}>
            {available.map(m => <MenuItem key={m} value={m}>{m}</MenuItem>)}
          </Select>
        </FormControl>
      </Stack>

      <Grid container spacing={3}>
        {/* Trend chart */}
        <Grid item xs={12} md={8}>
          <Paper sx={{ p:2 }}>
            <Typography variant="subtitle1" fontWeight={700} mb={1}>Trend + 3-Period Rolling Average</Typography>
            {metricData.length>0 ? (
              <Plot
                data={[
                  { x:years, y:values, type:'scatter', mode:'lines+markers', name:metric.split(' ').slice(0,2).join(' '),
                    line:{color:'#1A56DB',width:3}, marker:{size:8} } as any,
                  rolling.length>0 ? {
                    x:rolling.map(r=>r.year), y:rolling.map(r=>r.value),
                    type:'scatter', mode:'lines', name:'3-Period Avg',
                    line:{color:'#D97706',width:2,dash:'dash'},
                  } as any : null,
                ].filter(Boolean)}
                layout={{ height:300, margin:{t:10,b:40,l:80,r:20}, paper_bgcolor:'transparent', plot_bgcolor:'transparent',
                  yaxis:{gridcolor:'#E2E8F0',title:'INR Mn'}, legend:{x:0,y:1.1,orientation:'h'},
                  font:{family:'Inter, sans-serif',size:12} } as any}
                style={{ width:'100%' }} config={{ displayModeBar: false, responsive: true } as any}
              />
            ) : <Box sx={{ height:300, display:'flex', alignItems:'center', justifyContent:'center' }}><Typography color="text.secondary">No data</Typography></Box>}
          </Paper>
        </Grid>

        {/* Stats */}
        <Grid item xs={12} md={4}>
          <Stack spacing={2}>
            <Paper sx={{ p:2, border:`1px solid ${cagr&&cagr>=0?'#DCFCE7':'#FEE2E2'}` }}>
              <Typography variant="caption" color="text.secondary" fontWeight={600}>CAGR ({metricData.length>=2?`${years[0]}→${years[years.length-1]}`:''})</Typography>
              <Stack direction="row" alignItems="center" spacing={1} mt={0.5}>
                {cagr!=null ? (
                  <Typography variant="h4" fontWeight={700} sx={{color:cagr>=0?'#059669':'#DC2626'}}>
                    {cagr>=0?'+':''}{cagr.toFixed(1)}%
                  </Typography>
                ) : <Typography color="text.secondary">Insufficient data</Typography>}
              </Stack>
            </Paper>

            {metricData.length>=2 && (
              <Paper sx={{ p:2 }}>
                <Typography variant="caption" color="text.secondary" fontWeight={600}>LATEST VS PRIOR</Typography>
                <Box mt={1}>
                  <Stack direction="row" justifyContent="space-between">
                    <Typography variant="body2">{years[years.length-1]}</Typography>
                    <Typography variant="body2" fontWeight={700}>{fmt(values[values.length-1])}</Typography>
                  </Stack>
                  <Stack direction="row" justifyContent="space-between">
                    <Typography variant="body2" color="text.secondary">{years[years.length-2]}</Typography>
                    <Typography variant="body2" color="text.secondary">{fmt(values[values.length-2])}</Typography>
                  </Stack>
                </Box>
              </Paper>
            )}

          </Stack>
        </Grid>

        {/* YoY Table — deduplicated */}
        <Grid item xs={12} md={6}>
          <Paper sx={{ p:2 }}>
            <Typography variant="subtitle1" fontWeight={700} mb={1}>YoY Growth Rates</Typography>
            <Table size="small">
              <TableHead>
                <TableRow sx={{ '& th':{ fontWeight:700, bgcolor:'#F1F5F9' } }}>
                  <TableCell>Period</TableCell>
                  <TableCell align="right">Value (INR Mn)</TableCell>
                  <TableCell align="right">YoY Growth</TableCell>
                </TableRow>
              </TableHead>
              <TableBody>
                {[...metricData].reverse().map(d => {
                  const yoy = yoyRates.find(y => y.year === d.year)
                  return (
                    <TableRow key={d.year}>
                      <TableCell>{d.year}</TableCell>
                      <TableCell align="right">{fmt(d.value)}</TableCell>
                      <TableCell align="right">
                        {yoy ? (
                          <Chip label={`${yoy.rate>=0?'+':''}${yoy.rate.toFixed(1)}%`} size="small"
                            sx={{ bgcolor:yoy.rate>=0?'#ECFDF5':'#FEF2F2', color:yoy.rate>=0?'#059669':'#DC2626',
                              fontWeight:700, height:20, fontSize:11 }} />
                        ) : <Typography variant="caption" color="text.secondary">—</Typography>}
                      </TableCell>
                    </TableRow>
                  )
                })}
              </TableBody>
            </Table>
          </Paper>
        </Grid>

        {/* YoY bar chart */}
        <Grid item xs={12} md={6}>
          <Paper sx={{ p:2 }}>
            <Typography variant="subtitle1" fontWeight={700} mb={1}>YoY Growth Visualization</Typography>
            {yoyRates.length>0 ? (
              <Plot
                data={[{
                  x:yoyRates.map(d=>d.year), y:yoyRates.map(d=>d.rate), type:'bar',
                  marker:{color:yoyRates.map(d=>d.rate>=0?'#059669':'#DC2626')},
                  text:yoyRates.map(d=>`${d.rate.toFixed(1)}%`), textposition:'outside',
                } as any]}
                layout={{ height:260, margin:{t:20,b:40,l:60,r:20}, paper_bgcolor:'transparent', plot_bgcolor:'transparent',
                  yaxis:{gridcolor:'#E2E8F0',title:'Growth %',zeroline:true,zerolinecolor:'#94A3B8'},
                  font:{family:'Inter, sans-serif',size:12} } as any}
                style={{ width:'100%' }} config={{ displayModeBar: false, responsive: true } as any}
              />
            ) : <Box sx={{height:260,display:'flex',alignItems:'center',justifyContent:'center'}}><Typography color="text.secondary">Need 2+ years</Typography></Box>}
          </Paper>
        </Grid>
      </Grid>
    </Box>
  )
}
