import React, { useState, useMemo } from 'react'
import {
  Box, Drawer, AppBar, Toolbar, Typography, List, ListItem,
  ListItemButton, ListItemIcon, ListItemText, Select, MenuItem,
  FormControl, Divider, Button, Dialog, DialogTitle, DialogContent,
  DialogActions, TextField, Stack, Chip, Avatar, IconButton,
  ToggleButton, ToggleButtonGroup, Paper, Tooltip, Badge, Autocomplete
} from '@mui/material'
import SearchIcon      from '@mui/icons-material/Search'
import DarkModeIcon    from '@mui/icons-material/DarkMode'
import LightModeIcon   from '@mui/icons-material/LightMode'
import { useNavigate, useLocation } from 'react-router-dom'
import TableChartIcon    from '@mui/icons-material/TableChart'
import DashboardIcon     from '@mui/icons-material/Dashboard'
import FileDownloadIcon  from '@mui/icons-material/FileDownload'
import AddBusinessIcon   from '@mui/icons-material/AddBusiness'
import BarChartIcon      from '@mui/icons-material/BarChart'
import GroupsIcon        from '@mui/icons-material/Groups'
import AddIcon           from '@mui/icons-material/Add'
import DeleteIcon        from '@mui/icons-material/Delete'
import TrendingUpIcon    from '@mui/icons-material/TrendingUp'
import { useFilter, getPeriods, useThemeMode } from '../../App'
import { createCompany, deleteCompany } from '../../api/client'

const DRAWER_W = 220

const NAV = [
  { path: '/input',     label: 'Data Input',     icon: <TableChartIcon />,   badge: 0 },
  { path: '/dashboard', label: 'Dashboard',       icon: <DashboardIcon />,    badge: 0 },
  { path: '/peer',      label: 'Peer Comparison', icon: <GroupsIcon />,       badge: 0 },
  { path: '/export',    label: 'Export',          icon: <FileDownloadIcon />, badge: 0 },
]

const DARK_C = {
  navBg:       '#1e2329',
  canvas:      '#0b0e11',
  elevated:    '#2b3139',
  border:      '#2b3139',
  yellow:      '#FCD535',
  yellowHover: '#f0b90b',
  text:        '#ffffff',
  muted:       '#b0b8c1',
  sub:         '#b0b8c1',
  white:       '#ffffff',
  activeBg:    'rgba(252,213,53,0.10)',
  hoverBg:     'rgba(255,255,255,0.04)',
  iconColor:   '#ffffff',
  accentText:  '#FCD535',
  accentBg:    'rgba(252,213,53,0.12)',
  deleteColor: '#f6465d',
  toggleBg:    '#2b3139',
}

const LIGHT_C = {
  navBg:       '#000000',            // Apple global nav: pure black
  canvas:      '#f5f5f7',            // parchment page canvas
  elevated:    'rgba(255,255,255,0.10)', // chips/option-hover on black nav
  border:      '#e0e0e0',            // hairline divider
  yellow:      '#0066cc',            // Action Blue (single interactive color)
  yellowHover: '#0071e3',            // primary-focus
  text:        '#ffffff',            // white text on black nav
  muted:       '#cccccc',            // body-muted on dark nav
  sub:         '#cccccc',            // secondary muted on dark nav
  white:       '#ffffff',
  activeBg:    'rgba(0,102,204,0.22)', // selected nav item on black
  hoverBg:     'rgba(255,255,255,0.07)',
  iconColor:   '#ffffff',
  accentText:  '#2997ff',            // sky link blue (legible on black)
  accentBg:    'rgba(41,151,255,0.15)',
  deleteColor: '#ff3b30',            // Apple system red
  toggleBg:    'rgba(255,255,255,0.12)',
}

const emptySector = () => ({ sector: '', sub_sector: '' })

export default function AppShell({ children }: { children: React.ReactNode }) {
  const nav = useNavigate()
  const loc = useLocation()
  const { filter, setFilter, companies, refreshCompanies } = useFilter()
  const { mode, toggleTheme } = useThemeMode()

  const C = mode === 'dark' ? DARK_C : LIGHT_C

  const [addOpen, setAddOpen]       = useState(false)
  const [newCo, setNewCo]           = useState({ company_id: '', company_name: '', ticker: '' })
  const [sectorRows, setSectorRows] = useState([emptySector()])
  const [saving, setSaving]         = useState(false)
  const [delOpen, setDelOpen]       = useState(false)
  const [deleting, setDeleting]     = useState(false)

  const periods = useMemo(() => getPeriods(filter.periodType), [filter.periodType])

  const handleDelete = async () => {
    if (!filter.company) return
    setDeleting(true)
    try {
      await deleteCompany(filter.company)
      await refreshCompanies()
      setFilter({ company: '' })
      setDelOpen(false)
    } catch (e: any) {
      alert(`Delete failed: ${e?.response?.data?.detail || e?.message || 'Unknown error'}`)
    } finally { setDeleting(false) }
  }

  const handlePeriodType = (val: 'annual' | 'quarterly') => {
    setFilter({ periodType: val, period: getPeriods(val)[0] })
  }

  const handleAdd = async () => {
    if (!newCo.company_id || !newCo.company_name) return
    setSaving(true)
    try {
      await createCompany({
        ...newCo,
        company_id: newCo.company_id.toUpperCase(),
        sectors: sectorRows.filter(s => s.sector.trim()),
      })
      setAddOpen(false)
      setNewCo({ company_id: '', company_name: '', ticker: '' })
      setSectorRows([emptySector()])
      refreshCompanies()
    } catch (e: any) {
      alert('Error: ' + (e.response?.data?.detail || e.message))
    } finally { setSaving(false) }
  }

  const selectedCo = companies.find(c => c.company_id === filter.company)

  return (
    <Box sx={{ display: 'flex', minHeight: '100vh' }}>

      {/* ════════════════ SIDEBAR ════════════════ */}
      <Drawer variant="permanent" sx={{
        width: DRAWER_W, flexShrink: 0,
        '& .MuiDrawer-paper': {
          width: DRAWER_W,
          bgcolor: C.navBg,
          borderRight: `1px solid ${C.border}`,
          overflowX: 'hidden',
          display: 'flex',
          flexDirection: 'column',
        }
      }}>
        {/* ── Logo ── */}
        <Box sx={{ px: 2.5, py: 2.5, display: 'flex', justifyContent: 'center' }}>
          <Box sx={{
            width: 36, height: 36, borderRadius: '8px',
            bgcolor: mode === 'dark' ? '#FCD535' : '#0066cc',
            display: 'flex', alignItems: 'center', justifyContent: 'center',
          }}>
            <TrendingUpIcon sx={{ color: '#ffffff', fontSize: 20 }} />
          </Box>
        </Box>

        <Box sx={{ borderBottom: `1px solid ${C.border}`, mx: 2, mb: 1.5 }} />

        {/* ── Company selector ── */}
        <Box sx={{ px: 2, mb: 1.5 }}>
          <Typography sx={{ color: C.muted, fontSize: 9, fontWeight: 600, letterSpacing: 1.2, mb: 0.8, textTransform: 'uppercase' }}>
            Company
          </Typography>
          <Autocomplete
            options={companies}
            getOptionLabel={(opt) => opt.company_id}
            value={selectedCo || null}
            onChange={(_, val) => setFilter({ company: val?.company_id || '' })}
            isOptionEqualToValue={(opt, val) => opt.company_id === val.company_id}
            PaperComponent={({ children }) => (
              <Paper sx={{
                bgcolor: C.navBg,
                border: `1px solid ${C.border}`,
                '& .MuiAutocomplete-option': {
                  color: C.text, fontSize: 13,
                  '&:hover': { bgcolor: C.elevated },
                  '&[aria-selected="true"]': { bgcolor: C.accentBg, color: C.accentText },
                },
              }}>{children}</Paper>
            )}
            renderInput={(params) => (
              <TextField
                {...params}
                placeholder="Search company…"
                variant="standard"
                InputProps={{
                  ...params.InputProps,
                  disableUnderline: true,
                  startAdornment: <SearchIcon sx={{ color: C.muted, fontSize: 15, mr: 0.5 }} />,
                }}
                sx={{
                  '& input': { color: C.text, fontWeight: 600, fontSize: 13, py: 0 },
                  '& input::placeholder': { color: C.muted, opacity: 1 },
                }}
              />
            )}
            renderOption={(props, opt) => (
              <li {...props} key={opt.company_id}>
                <Stack>
                  <Typography fontSize={13} fontWeight={600} color={C.text}>{opt.company_id}</Typography>
                  <Typography fontSize={11} noWrap sx={{ maxWidth: 160, color: C.muted }}>{opt.company_name}</Typography>
                </Stack>
              </li>
            )}
            sx={{
              bgcolor: mode === 'dark' ? '#0b0e11' : '#1d1d1f',
              border: `1px solid ${C.border}`,
              borderRadius: '6px', px: 1.2, py: 0.8,
              transition: 'border-color 0.2s',
              '&:hover': { borderColor: C.yellow },
              '& .MuiAutocomplete-popupIndicator': { color: C.muted },
              '& .MuiAutocomplete-clearIndicator': { color: C.muted },
            }}
          />
          {selectedCo && (
            <Typography fontSize={11} noWrap sx={{ color: C.muted, mt: 0.4, px: 0.5 }}>
              {selectedCo.sectors_display || 'No sector'}
            </Typography>
          )}
          <Button
            startIcon={<AddBusinessIcon sx={{ fontSize: '13px !important' }} />}
            onClick={() => setAddOpen(true)} fullWidth size="small"
            variant="contained"
            sx={{
              mt: 0.8, bgcolor: C.yellow, color: '#ffffff', fontSize: 12,
              textTransform: 'none', borderRadius: '6px', fontWeight: 600,
              '&:hover': { bgcolor: C.yellowHover },
            }}
          >
            Add Company
          </Button>
          {filter.company && (
            <Button
              startIcon={<DeleteIcon sx={{ fontSize: '13px !important' }} />}
              onClick={() => setDelOpen(true)} fullWidth size="small"
              sx={{
                mt: 0.5, color: C.deleteColor,
                borderColor: mode === 'dark' ? 'rgba(246,70,93,0.4)' : 'rgba(229,62,62,0.4)',
                fontSize: 12, textTransform: 'none', borderRadius: '6px',
                '&:hover': { bgcolor: mode === 'dark' ? 'rgba(246,70,93,0.08)' : 'rgba(229,62,62,0.06)', borderColor: C.deleteColor },
              }}
              variant="outlined"
            >
              Delete Company
            </Button>
          )}
        </Box>

        <Box sx={{ borderBottom: `1px solid ${C.border}`, mx: 2, mb: 1 }} />

        {/* ── Navigation ── */}
        <List sx={{ px: 1.5, flexGrow: 1 }}>
          {NAV.map(item => {
            const active = loc.pathname === item.path
            return (
              <ListItem key={item.path} disablePadding sx={{ mb: 0.4 }}>
                <ListItemButton
                  onClick={() => nav(item.path)}
                  sx={{
                    borderRadius: '6px', py: 0.9, px: 1.2,
                    transition: 'background-color 0.2s',
                    bgcolor: active ? C.activeBg : 'transparent',
                    borderLeft: active ? `3px solid ${C.yellow}` : '3px solid transparent',
                    '&:hover': {
                      bgcolor: C.hoverBg,
                      borderLeftColor: C.yellow,
                      '& .nav-icon': { color: C.accentText },
                    },
                  }}
                >
                  <ListItemIcon
                    className="nav-icon"
                    sx={{ color: active ? C.accentText : C.muted, minWidth: 32, transition: 'color 0.2s' }}
                  >
                    {React.cloneElement(item.icon as React.ReactElement, { sx: { fontSize: 18 } })}
                  </ListItemIcon>
                  <ListItemText
                    primary={item.label}
                    primaryTypographyProps={{
                      fontSize: 14,
                      fontWeight: active ? 600 : 400,
                      color: active ? C.text : C.sub,
                    }}
                  />
                  {active && (
                    <Box sx={{ width: 5, height: 5, borderRadius: '50%', bgcolor: C.yellow, ml: 0.5 }} />
                  )}
                </ListItemButton>
              </ListItem>
            )
          })}
        </List>

      </Drawer>

      {/* ════════════════ MAIN AREA ════════════════ */}
      <Box sx={{ flexGrow: 1, display: 'flex', flexDirection: 'column', overflow: 'hidden', bgcolor: C.canvas }}>

        {/* ── Top filter bar ── */}
        <Paper elevation={0} sx={{
          borderBottom: `1px solid ${C.border}`, borderRadius: 0,
          px: 3, py: 1, bgcolor: C.navBg,
        }}>
          <Stack direction="row" spacing={2} alignItems="center" flexWrap="wrap">
            {/* Period type */}
            <ToggleButtonGroup
              value={filter.periodType} exclusive size="small"
              onChange={(_, v) => v && handlePeriodType(v)}
              sx={{
                '& .MuiToggleButton-root': {
                  px: 1.8, py: 0.5, fontSize: 12, textTransform: 'none',
                  border: '1px solid rgba(255,255,255,0.25)', color: '#cccccc', borderRadius: '6px',
                  transition: 'background-color 0.2s, color 0.2s',
                  '&.Mui-selected': { bgcolor: C.yellow, color: '#ffffff', borderColor: C.yellow, fontWeight: 600 },
                }
              }}
            >
              <ToggleButton value="annual">Annual</ToggleButton>
              <ToggleButton value="quarterly">Quarterly</ToggleButton>
            </ToggleButtonGroup>

            {/* Period */}
            <FormControl size="small" sx={{ minWidth: 110 }}>
              <Select
                value={filter.period}
                onChange={e => setFilter({ period: e.target.value })}
                sx={{
                  fontSize: 13,
                  borderRadius: '6px',
                  color: '#ffffff',
                  bgcolor: 'rgba(255,255,255,0.08)',
                  '& .MuiSelect-select': { color: '#ffffff' },
                  '& .MuiSvgIcon-root': { color: '#cccccc' },
                  '& .MuiOutlinedInput-notchedOutline': { borderColor: 'rgba(255,255,255,0.20)' },
                  '&:hover .MuiOutlinedInput-notchedOutline': { borderColor: 'rgba(255,255,255,0.45)' },
                  '&.Mui-focused .MuiOutlinedInput-notchedOutline': { borderColor: C.yellow, borderWidth: 2 },
                }}
              >
                {periods.map(p => <MenuItem key={p} value={p} sx={{ fontSize: 13 }}>{p}</MenuItem>)}
              </Select>
            </FormControl>

            {/* Report type */}
            <ToggleButtonGroup
              value={filter.reportType} exclusive size="small"
              onChange={(_, v) => v && setFilter({ reportType: v })}
              sx={{
                '& .MuiToggleButton-root': {
                  px: 1.8, py: 0.5, fontSize: 12, textTransform: 'none',
                  border: '1px solid rgba(255,255,255,0.25)', color: '#cccccc', borderRadius: '6px',
                  transition: 'background-color 0.2s, color 0.2s',
                  '&.Mui-selected': { bgcolor: C.yellow, color: '#ffffff', borderColor: C.yellow, fontWeight: 600 },
                }
              }}
            >
              <ToggleButton value="consolidated">Consolidated</ToggleButton>
              <ToggleButton value="standalone">Standalone</ToggleButton>
            </ToggleButtonGroup>

            <Box sx={{ flexGrow: 1 }} />

            {/* Active filter chips */}
            <Chip
              label={filter.company || '—'} size="small"
              sx={{ bgcolor: C.accentBg, color: C.accentText, fontWeight: 600, fontSize: 11, height: 24, borderRadius: '6px' }}
            />
            <Chip
              label={filter.period} size="small"
              sx={{ bgcolor: C.elevated, color: C.text, fontWeight: 500, fontSize: 11, height: 24, borderRadius: '6px' }}
            />
            <Chip
              label={filter.reportType === 'consolidated' ? 'Consol.' : 'Standalone'} size="small"
              sx={{ bgcolor: C.elevated, color: C.text, fontWeight: 500, fontSize: 11, height: 24, borderRadius: '6px' }}
            />

            {/* Theme toggle */}
            <Tooltip title={mode === 'dark' ? 'Switch to Light theme' : 'Switch to Dark theme'}>
              <IconButton
                onClick={toggleTheme} size="small"
                sx={{
                  bgcolor: C.toggleBg, color: C.iconColor,
                  border: `1px solid ${C.border}`, borderRadius: '8px',
                  width: 32, height: 32,
                  '&:hover': { bgcolor: C.elevated, color: C.accentText },
                }}
              >
                {mode === 'dark'
                  ? <LightModeIcon sx={{ fontSize: 16 }} />
                  : <DarkModeIcon  sx={{ fontSize: 16 }} />
                }
              </IconButton>
            </Tooltip>
          </Stack>
        </Paper>

        {/* ── Page content ── */}
        <Box sx={{ flexGrow: 1, overflow: 'auto', p: 3 }}>
          {children}
        </Box>
      </Box>

      {/* ════════ Add Company Dialog ════════ */}
      <Dialog open={addOpen} onClose={() => setAddOpen(false)} maxWidth="sm" fullWidth>
        <DialogTitle sx={{ borderBottom: `1px solid ${C.border}`, color: C.text, py: 2, fontSize: 16, fontWeight: 600 }}>
          Add New Company
        </DialogTitle>
        <DialogContent sx={{ mt: 2 }}>
          <Stack spacing={2} sx={{ mt: 0.5 }}>
            <Stack direction="row" spacing={1.5}>
              <TextField label="Company ID *" value={newCo.company_id} size="small"
                onChange={e => setNewCo({ ...newCo, company_id: e.target.value.toUpperCase() })}
                placeholder="e.g. CIPLA" sx={{ flex: 1 }} />
              <TextField label="Ticker" value={newCo.ticker} size="small"
                onChange={e => setNewCo({ ...newCo, ticker: e.target.value })}
                placeholder="e.g. CIPLA.NS" sx={{ flex: 1 }} />
            </Stack>
            <TextField label="Company Name *" value={newCo.company_name} size="small"
              onChange={e => setNewCo({ ...newCo, company_name: e.target.value })}
              placeholder="e.g. Cipla Ltd" fullWidth />
            <Box>
              <Stack direction="row" justifyContent="space-between" alignItems="center" mb={0.5}>
                <Typography variant="caption" fontWeight={600} color="text.secondary">SECTORS</Typography>
                <Button size="small" startIcon={<AddIcon />}
                  onClick={() => setSectorRows(r => [...r, emptySector()])}
                  sx={{ fontSize: 11, textTransform: 'none' }}>
                  Add Sector
                </Button>
              </Stack>
              {sectorRows.map((s, i) => (
                <Stack key={i} direction="row" spacing={1} mb={1} alignItems="center">
                  <TextField label="Sector" value={s.sector} size="small" placeholder="Pharma"
                    onChange={e => setSectorRows(r => r.map((x, j) => j===i ? {...x, sector: e.target.value} : x))}
                    sx={{ flex: 2 }} />
                  <TextField label="Sub-sector" value={s.sub_sector} size="small" placeholder="Generics"
                    onChange={e => setSectorRows(r => r.map((x, j) => j===i ? {...x, sub_sector: e.target.value} : x))}
                    sx={{ flex: 2 }} />
                  {sectorRows.length > 1 && (
                    <IconButton size="small" color="error"
                      onClick={() => setSectorRows(r => r.filter((_, j) => j !== i))}>
                      <DeleteIcon fontSize="small" />
                    </IconButton>
                  )}
                </Stack>
              ))}
            </Box>
          </Stack>
        </DialogContent>
        <DialogActions sx={{ p: 2, borderTop: `1px solid ${C.border}` }}>
          <Button onClick={() => setAddOpen(false)} sx={{ color: C.muted }}>Cancel</Button>
          <Button onClick={handleAdd} variant="contained" color="primary"
            disabled={saving || !newCo.company_id || !newCo.company_name}>
            {saving ? 'Adding…' : 'Add Company'}
          </Button>
        </DialogActions>
      </Dialog>

      {/* ════════ Delete Company Dialog ════════ */}
      <Dialog open={delOpen} onClose={() => setDelOpen(false)} maxWidth="xs" fullWidth>
        <DialogTitle sx={{ fontWeight: 600, color: C.deleteColor, borderBottom: `1px solid ${C.border}` }}>
          Delete Company
        </DialogTitle>
        <DialogContent>
          <Typography fontSize={14} color="text.secondary" mt={2}>
            Permanently delete <strong style={{ color: C.text }}>{filter.company}</strong> and all its data?
          </Typography>
          <Typography fontSize={12} color="error" mt={1}>
            This removes all warehouse data, staged inputs, and analysis results.
            This action cannot be undone.
          </Typography>
        </DialogContent>
        <DialogActions sx={{ p: 2, borderTop: `1px solid ${C.border}` }}>
          <Button onClick={() => setDelOpen(false)} disabled={deleting} sx={{ color: C.muted }}>Cancel</Button>
          <Button onClick={handleDelete} variant="contained"
            disabled={deleting}
            sx={{ bgcolor: C.deleteColor, color: '#fff', '&:hover': { opacity: 0.9 } }}>
            {deleting ? 'Deleting…' : 'Delete'}
          </Button>
        </DialogActions>
      </Dialog>
    </Box>
  )
}
