import React, { useState, useEffect } from 'react'
import {
  Box, Typography, Stack, Button, Card, CardContent, Grid, Alert,
  CircularProgress, Snackbar, Chip, Paper, Table, TableHead, TableRow,
  TableCell, TableBody, LinearProgress, Tooltip, IconButton
} from '@mui/material'
import DownloadIcon     from '@mui/icons-material/Download'
import TableChartIcon   from '@mui/icons-material/TableChart'
import PictureAsPdfIcon from '@mui/icons-material/PictureAsPdf'
import RefreshIcon      from '@mui/icons-material/Refresh'
import ReplayIcon       from '@mui/icons-material/Replay'
import CheckCircleIcon  from '@mui/icons-material/CheckCircle'
import ErrorIcon        from '@mui/icons-material/Error'
import { useFilter } from '../../App'
import { exportExcel, exportPDF, fetchExportLogs, downloadBlob } from '../../api/client'

interface ExportJob {
  format: string
  status: 'idle' | 'running' | 'done' | 'error'
  error?: string
  progress: number
}

const EXPORTS = [
  {
    format: 'excel',
    icon: <TableChartIcon sx={{ fontSize:40, color:'#059669' }} />,
    title: 'Excel Analysis Workbook',
    desc: 'Full Output_Analysis workbook with live formulas, Altman Z formatting, 3 sheets (Altman Z, P&L Consolidated, P&L Standalone).',
    color: '#059669', bgColor: '#ECFDF5',
    fn: (id:string, period?:string, rt?:string) => exportExcel(id, period, rt),
    filename: (id:string) => `Output_Analysis_${id}.xlsx`,
  },
  {
    format: 'pdf',
    icon: <PictureAsPdfIcon sx={{ fontSize:40, color:'#DC2626' }} />,
    title: 'PDF Management Report',
    desc: 'Executive summary PDF: KPI table, cost breakdown, Altman Z score with zone interpretation.',
    color: '#DC2626', bgColor: '#FEF2F2',
    fn: (id:string, period?:string, rt?:string) => exportPDF(id, period, rt),
    filename: (id:string) => `Report_${id}.pdf`,
  },
]

export default function ExportPage() {
  const { filter } = useFilter()
  const companyId = filter.company

  const [jobs, setJobs]   = useState<Record<string, ExportJob>>({
    excel: { format:'excel', status:'idle', progress:0 },
    pdf:   { format:'pdf',   status:'idle', progress:0 },
  })
  const [logs, setLogs]   = useState<any[]>([])
  const [snack, setSnack] = useState<{msg:string; sev:'success'|'error'|'info'}|null>(null)

  const loadLogs = () => {
    if (!companyId) return
    fetchExportLogs(companyId).then(setLogs).catch(()=>{})
  }

  useEffect(() => { loadLogs() }, [companyId])

  const setJob = (fmt: string, patch: Partial<ExportJob>) =>
    setJobs(j => ({ ...j, [fmt]: { ...j[fmt], ...patch } }))

  const doExport = async (exp: typeof EXPORTS[0]) => {
    if (!companyId) { setSnack({ msg:'Select a company in the top bar', sev:'info' }); return }
    setJob(exp.format, { status:'running', progress:0, error:undefined })

    // Simulate progress
    const tick = setInterval(() => {
      setJob(exp.format, { progress: Math.min(jobs[exp.format].progress + 15, 85) })
    }, 300)

    try {
      const blob = await exp.fn(companyId, filter.period, filter.reportType)
      clearInterval(tick)
      setJob(exp.format, { status:'done', progress:100 })
      downloadBlob(blob, exp.filename(companyId))
      setSnack({ msg:`${exp.title} downloaded`, sev:'success' })
      setTimeout(loadLogs, 500)
    } catch (e: any) {
      clearInterval(tick)
      const errMsg = e.response?.data?.detail || e.message || 'Export failed'
      setJob(exp.format, { status:'error', progress:0, error:errMsg })
      setSnack({ msg:errMsg, sev:'error' })
    }
  }

  const statusIcon = (status: string) => {
    if (status==='done')    return <CheckCircleIcon sx={{color:'#059669',fontSize:18}} />
    if (status==='error')   return <ErrorIcon sx={{color:'#DC2626',fontSize:18}} />
    if (status==='running') return <CircularProgress size={16} />
    return null
  }

  return (
    <Box>
      <Typography variant="h5" fontWeight={800} color="text.primary" mb={1}>Export</Typography>
      <Typography variant="body2" color="text.secondary" mb={3}>
        {companyId ? `${companyId} · Run Analyze first, then export in any format` : 'Select a company in the top bar'}
      </Typography>

      {!companyId && (
        <Alert severity="warning" sx={{mb:2}}>Select a company in the top bar first</Alert>
      )}

      {/* Export Cards */}
      <Grid container spacing={2.5} mb={4}>
        {EXPORTS.map(exp => {
          const job = jobs[exp.format]
          return (
            <Grid item xs={12} md={4} key={exp.format}>
              <Card sx={{ height:'100%', border:`1px solid ${exp.bgColor}`, boxShadow:'0 2px 8px rgba(0,0,0,0.06)' }}>
                <CardContent>
                  <Box sx={{ bgcolor:exp.bgColor, borderRadius:2, p:2, mb:2, display:'flex', justifyContent:'center' }}>
                    {exp.icon}
                  </Box>
                  <Stack direction="row" alignItems="center" spacing={1} mb={0.5}>
                    <Typography variant="h6" fontWeight={700}>{exp.title}</Typography>
                    {statusIcon(job.status)}
                  </Stack>
                  <Typography variant="body2" color="text.secondary" mb={2}>{exp.desc}</Typography>

                  {job.status === 'running' && (
                    <Box mb={1.5}>
                      <LinearProgress variant="determinate" value={job.progress}
                        sx={{ borderRadius:4, height:6, bgcolor:`${exp.color}20`,
                          '& .MuiLinearProgress-bar':{ bgcolor:exp.color } }} />
                      <Typography variant="caption" color="text.secondary" mt={0.5} display="block">
                        Generating… {job.progress}%
                      </Typography>
                    </Box>
                  )}

                  {job.status === 'error' && (
                    <Alert severity="error" sx={{ mb:1.5, py:0.5, fontSize:11 }}>
                      {job.error}
                    </Alert>
                  )}

                  {job.status === 'done' && (
                    <Alert severity="success" sx={{ mb:1.5, py:0.5, fontSize:11 }}>
                      Downloaded successfully
                    </Alert>
                  )}

                  <Stack direction="row" spacing={1}>
                    <Button variant="contained" fullWidth
                      startIcon={job.status==='running' ? <CircularProgress size={14} color="inherit" /> : <DownloadIcon />}
                      onClick={() => doExport(exp)}
                      disabled={job.status==='running' || !companyId}
                      sx={{ bgcolor:exp.color, '&:hover':{ filter:'brightness(0.92)', bgcolor:exp.color } }}>
                      {job.status==='running' ? 'Generating…' : job.status==='done' ? 'Download Again' : 'Download'}
                    </Button>
                    {job.status==='error' && (
                      <Tooltip title="Retry">
                        <IconButton onClick={() => doExport(exp)} color="error" size="small">
                          <ReplayIcon />
                        </IconButton>
                      </Tooltip>
                    )}
                  </Stack>
                </CardContent>
              </Card>
            </Grid>
          )
        })}
      </Grid>

      {/* Export Logs */}
      <Paper sx={{ p:2 }}>
        <Stack direction="row" justifyContent="space-between" alignItems="center" mb={1.5}>
          <Typography variant="subtitle1" fontWeight={700}>Export History</Typography>
          <Button startIcon={<RefreshIcon />} size="small" onClick={loadLogs} variant="outlined">Refresh</Button>
        </Stack>
        {logs.length === 0 ? (
          <Typography color="text.secondary" fontSize={13}>No exports yet for this company</Typography>
        ) : (
          <Table size="small">
            <TableHead>
              <TableRow sx={{'& th':{fontWeight:600,bgcolor:'#181a20',color:'#707a8a',fontSize:12}}}>
                <TableCell>Format</TableCell>
                <TableCell>Status</TableCell>
                <TableCell>Date / Time</TableCell>
                <TableCell>Error</TableCell>
              </TableRow>
            </TableHead>
            <TableBody>
              {logs.map((log, i) => (
                <TableRow key={i}>
                  <TableCell><Chip label={log.format.toUpperCase()} size="small"
                    sx={{ fontWeight:700, bgcolor:log.format==='excel'?'#ECFDF5':log.format==='ppt'?'#FFFBEB':'#FEF2F2',
                      color:log.format==='excel'?'#059669':log.format==='ppt'?'#D97706':'#DC2626' }} /></TableCell>
                  <TableCell>
                    <Stack direction="row" spacing={0.5} alignItems="center">
                      {log.status==='success'
                        ? <CheckCircleIcon sx={{color:'#059669',fontSize:16}} />
                        : <ErrorIcon sx={{color:'#DC2626',fontSize:16}} />}
                      <Typography fontSize={12}>{log.status}</Typography>
                    </Stack>
                  </TableCell>
                  <TableCell><Typography fontSize={11} color="text.secondary">{log.created_at}</Typography></TableCell>
                  <TableCell><Typography fontSize={11} color="error.main" sx={{maxWidth:300,overflow:'hidden',textOverflow:'ellipsis',whiteSpace:'nowrap'}}>{log.error_msg||'—'}</Typography></TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        )}
      </Paper>

      <Snackbar open={!!snack} autoHideDuration={4000} onClose={()=>setSnack(null)}
        anchorOrigin={{ vertical:'bottom', horizontal:'right' }}>
        <Alert severity={snack?.sev} onClose={()=>setSnack(null)} variant="filled">{snack?.msg}</Alert>
      </Snackbar>
    </Box>
  )
}
