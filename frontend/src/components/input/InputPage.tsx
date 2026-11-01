import React, {
  useState, useEffect, useCallback, useRef, useMemo
} from 'react'
import {
  Box, Stack, Button, Typography, Alert, CircularProgress, Chip,
  Snackbar, Paper, Tabs, Tab, ToggleButton, ToggleButtonGroup,
  Dialog, DialogTitle, DialogContent, DialogActions, TextField,
  MenuItem, Tooltip, Menu, ListItemIcon, ListItemText,
  Divider as MuiDivider, InputAdornment, IconButton as MuiIconButton,
  LinearProgress
} from '@mui/material'
import { AgGridReact } from 'ag-grid-react'
import { ColDef, CellValueChangedEvent, ICellRendererParams } from 'ag-grid-community'
import 'ag-grid-community/styles/ag-grid.css'
import 'ag-grid-community/styles/ag-theme-alpine.css'

// ── AG Grid cell border override — theme-aware ─────────────────────────────────
function getGridStyles(mode: 'dark' | 'light'): string {
  if (mode === 'dark') return `
    .ag-theme-alpine .ag-cell {
      border-right: 1px solid #2b3139 !important;
      border-bottom: 1px solid #2b3139 !important;
      background-color: #1e2329 !important;
      color: #ffffff !important;
    }
    .ag-theme-alpine .ag-header-cell {
      border-right: 1px solid #2b3139 !important;
      background-color: #181a20 !important;
      color: #eaecef !important;
    }
    .ag-theme-alpine .ag-row {
      border-bottom: 1px solid #2b3139 !important;
    }
    .ag-theme-alpine .ag-row:hover .ag-cell {
      background-color: #2b3139 !important;
    }
    .ag-theme-alpine .computed-row .ag-cell {
      cursor: not-allowed !important;
    }
    .ag-theme-alpine .section-header-row .ag-cell {
      background-color: #181a20 !important;
      color: #FCD535 !important;
      font-weight: 800 !important;
      font-size: 11px !important;
      letter-spacing: 0.8px !important;
      text-transform: uppercase !important;
      cursor: default !important;
      border-bottom: 1px solid #FCD535 !important;
      text-shadow: -1px -1px 0 rgba(0,0,0,0.7), 1px -1px 0 rgba(0,0,0,0.7), -1px 1px 0 rgba(0,0,0,0.7), 1px 1px 0 rgba(0,0,0,0.7) !important;
    }
    .ag-theme-alpine .section-header-row:hover .ag-cell {
      background-color: #181a20 !important;
    }
  `
  return `
    .ag-theme-alpine .ag-root-wrapper {
      border: 1px solid #e0e0e0 !important;
      border-radius: 12px !important;
      overflow: hidden !important;
    }
    .ag-theme-alpine .ag-cell {
      border-right: 1px solid #e0e0e0 !important;
      border-bottom: 1px solid #e0e0e0 !important;
      background-color: #ffffff !important;
      color: #1d1d1f !important;
      font-family: "SF Pro Text", system-ui, -apple-system, sans-serif !important;
      font-size: 14px !important;
      letter-spacing: -0.224px !important;
    }
    .ag-theme-alpine .ag-header-cell {
      border-right: 1px solid #e0e0e0 !important;
      background-color: #f5f5f7 !important;
      color: #6e6e73 !important;
      font-family: "SF Pro Text", system-ui, -apple-system, sans-serif !important;
      font-size: 12px !important;
      font-weight: 600 !important;
      letter-spacing: -0.12px !important;
    }
    .ag-theme-alpine .ag-header-row {
      background-color: #f5f5f7 !important;
      border-bottom: 1px solid #e0e0e0 !important;
    }
    .ag-theme-alpine .ag-row {
      border-bottom: 1px solid #e0e0e0 !important;
    }
    .ag-theme-alpine .ag-row:hover .ag-cell {
      background-color: #f9f9fb !important;
    }
    .ag-theme-alpine .computed-row .ag-cell {
      cursor: not-allowed !important;
      background-color: #fafafa !important;
      color: #6e6e73 !important;
    }
    .ag-theme-alpine .section-header-row .ag-cell {
      background-color: #eff6ff !important;
      color: #0066cc !important;
      font-weight: 800 !important;
      font-size: 11px !important;
      letter-spacing: 0.6px !important;
      text-transform: uppercase !important;
      cursor: default !important;
      border-bottom: 1px solid #d0d8e8 !important;
      border-left: none !important;
    }
    .ag-theme-alpine .section-header-row:hover .ag-cell {
      background-color: #eff6ff !important;
    }
  `
}
import { bulkSave, InputRow, api, fetchWorkspace, invalidateCache, calculateAllCompanies } from '../../api/client'
import { useFilter, useThemeMode } from '../../App'
import { useNavigate } from 'react-router-dom'

import PlayArrowIcon      from '@mui/icons-material/PlayArrow'
import SaveIcon           from '@mui/icons-material/Save'
import AddIcon            from '@mui/icons-material/Add'
import UndoIcon           from '@mui/icons-material/Undo'
import RedoIcon           from '@mui/icons-material/Redo'
import ContentCopyIcon    from '@mui/icons-material/ContentCopy'
import DeleteOutlineIcon  from '@mui/icons-material/DeleteOutline'
import SearchIcon         from '@mui/icons-material/Search'
import ClearIcon          from '@mui/icons-material/Clear'
import LockIcon           from '@mui/icons-material/Lock'
import LockOpenIcon       from '@mui/icons-material/LockOpen'
import DiscardIcon        from '@mui/icons-material/Restore'
import WarningIcon        from '@mui/icons-material/Warning'
import SubdirectoryArrowRightIcon from '@mui/icons-material/SubdirectoryArrowRight'
import ExpandMoreIcon     from '@mui/icons-material/ExpandMore'
import ChevronRightIcon   from '@mui/icons-material/ChevronRight'

// ─── Types ────────────────────────────────────────────────────────────────────
type GRow    = Record<string, any>
type HistEntry = { rows: GRow[]; desc: string }
type FreezeMode = 'frozen' | 'editing'
type RowSource  = 'warehouse' | 'staged' | 'empty'

interface CellCoord { row: number; col: string }
interface SelRange  { start: CellCoord; end: CellCoord }

// ─── Constants ────────────────────────────────────────────────────────────────
const CRORE_TO_MN = 10
const CATS        = ['Altman Z', 'P&L Consolidated', 'P&L Standalone']
const UNIT_OPTS   = ['INR Million', 'INR Crore', '%', 'Ratio', 'Days']
const MAX_DEPTH   = 3
const INDENT_PX   = 20

// Items subtracted from Total Cost to get Remaining Expenses
const RE_SUBTRACTORS = [
  'Cost of Materials Consumed',
  'Purchases of Stock-in-Trade',
  'Changes in Inventories',
  'Employee Benefit Expenses',
  'Finance Costs',
  'Depreciation and Amortisation',
  'Other Expenses',
]

// Altman Z section grouping for the input grid
const ALTMAN_SECTIONS = [
  {
    label: 'Income Statement',
    items: ['Revenue from Operations','EBITDA','Depreciation and Amortisation','PAT','Finance Costs'],
  },
  {
    label: 'Balance Sheet: Assets',
    items: ['Total Assets','Current Assets','Debtors (Receivables)','Inventory'],
  },
  {
    label: 'Balance Sheet: Liabilities',
    items: ['Current Liabilities','Short Term Borrowings','Creditors (Payables)','Non Current Liability'],
  },
  {
    label: 'Balance Sheet: Equity',
    items: ['Net Worth','Other Equity (Includes Reserves)','Retained Earnings'],
  },
  {
    label: 'Market Valuation Metrics',
    items: ['Market Capitalization'],
  },
]
// Selection style — mode injected at render time in cellStyle callback
const SEL_COLOR_DARK  = 'rgba(252,213,53,0.15)'
const SEL_BORDER_DARK = '1.5px solid #FCD535'
const SEL_COLOR_LIGHT = 'rgba(0,102,204,0.10)'
const SEL_BORDER_LIGHT = '1.5px solid #0066cc'

// Cell backgrounds by source + freeze mode
const BG_DARK = {
  frozen_warehouse: '#1e2329',
  frozen_staged:    '#2b3139',
  frozen_empty:     '#1e2329',
  editing_modified: 'rgba(252,213,53,0.18)',
  editing_value:    'rgba(255,255,255,0.05)',
  editing_empty:    '#1e2329',
}
const BG_LIGHT = {
  frozen_warehouse: '#ffffff',
  frozen_staged:    '#f0f8ff',
  frozen_empty:     '#ffffff',
  editing_modified: 'rgba(0,102,204,0.07)',
  editing_value:    '#ffffff',
  editing_empty:    '#ffffff',
}

// ─── Range helpers ────────────────────────────────────────────────────────────
function rangeToSet(range: SelRange | null, years: string[]): Set<string> {
  if (!range) return new Set()
  const r0 = Math.min(range.start.row, range.end.row)
  const r1 = Math.max(range.start.row, range.end.row)
  const c0 = Math.min(years.indexOf(range.start.col), years.indexOf(range.end.col))
  const c1 = Math.max(years.indexOf(range.start.col), years.indexOf(range.end.col))
  const s = new Set<string>()
  for (let r = r0; r <= r1; r++)
    for (let c = c0; c <= c1; c++)
      s.add(`${r}::${years[c]}`)
  return s
}

function cellCount(range: SelRange | null, years: string[]): number {
  if (!range) return 0
  const r = Math.abs(range.end.row - range.start.row) + 1
  const c0 = years.indexOf(range.start.col); const c1 = years.indexOf(range.end.col)
  if (c0 < 0 || c1 < 0) return 0
  return r * (Math.abs(c1 - c0) + 1)
}

// ─── Tree helpers ─────────────────────────────────────────────────────────────
function buildTree(flat: GRow[]): GRow[] {
  const byKey      = new Map<string, GRow>()
  const childrenOf = new Map<string, GRow[]>()
  const roots: GRow[] = []
  flat.forEach(r => byKey.set(r.financial_item, r))
  flat.forEach(r => {
    const p = r.parent_item
    if (!p || !byKey.has(p)) roots.push(r)
    else { if (!childrenOf.has(p)) childrenOf.set(p, []); childrenOf.get(p)!.push(r) }
  })
  const out: GRow[] = []
  function walk(rows: GRow[], depth: number) {
    rows.forEach(r => {
      const ch = childrenOf.get(r.financial_item) || []
      out.push({ ...r, _depth: depth, _hasChildren: ch.length > 0 })
      if (!r._collapsed && ch.length) walk(ch, depth + 1)
    })
  }
  walk(roots, 0)
  return out
}

function sumChildren(rows: GRow[], parent: GRow, years: string[]): GRow {
  const ch = rows.filter(r => r.parent_item === parent.financial_item)
  if (!ch.length) return parent
  const u = { ...parent }
  years.forEach(y => {
    if (ch.some(c => c[y] != null)) u[y] = ch.reduce((s, c) => s + (c[y] ?? 0), 0)
  })
  return u
}

// ─── Particulars cell renderer ─────────────────────────────────────────────
function ParticularsRenderer(p: ICellRendererParams & {
  onToggle: (item: string) => void
  onRename: (item: string, name: string) => void
  editingRow: string | null
  setEditingRow: (v: string | null) => void
  frozen: boolean
}) {
  const { data, onToggle, onRename, editingRow, setEditingRow, frozen } = p
  const { mode: themeMode } = useThemeMode()
  const isLight = themeMode === 'light'
  const accentColor  = isLight ? '#0066cc' : '#FCD535'
  const iconColor    = isLight ? '#0066cc' : '#FCD535'
  const sectionColor = isLight ? '#0066cc' : '#FCD535'
  if (!data) return null
  if (data._isSection) return (
    <Box sx={{ display:'flex', alignItems:'center', height:'100%', pl:'8px' }}>
      <span style={{ fontSize:11, fontWeight:700, color: sectionColor, letterSpacing:'0.8px', textTransform:'uppercase' }}>
        {data.financial_item}
      </span>
    </Box>
  )
  const depth = data._depth || 0
  const [draft, setDraft] = useState(data.financial_item)
  const isEditing = !frozen && editingRow === data.financial_item
  return (
    <Box sx={{ display:'flex', alignItems:'center', pl:`${depth*INDENT_PX}px`, height:'100%', gap:0.3 }}>
      {data._hasChildren
        ? <Box component="span" onClick={() => onToggle(data.financial_item)}
            sx={{ cursor:'pointer', color: iconColor, display:'flex', alignItems:'center', flexShrink:0 }}>
            {data._collapsed ? <ChevronRightIcon sx={{fontSize:16}}/> : <ExpandMoreIcon sx={{fontSize:16}}/>}
          </Box>
        : depth > 0
          ? <SubdirectoryArrowRightIcon sx={{fontSize:13,color:'#94A3B8',flexShrink:0}}/>
          : <Box sx={{width:16,flexShrink:0}}/>
      }
      {isEditing
        ? <input autoFocus value={draft}
            onChange={e => setDraft(e.target.value)}
            onBlur={() => { onRename(data.financial_item, draft); setEditingRow(null) }}
            onKeyDown={e => {
              if (e.key==='Enter') { onRename(data.financial_item, draft); setEditingRow(null) }
              if (e.key==='Escape') setEditingRow(null)
            }}
            style={{ flex:1, border:`1px solid ${accentColor}`, borderRadius:4, padding:'2px 6px',
              fontSize:13, fontWeight:depth===0?600:400, outline:'none' }}
          />
        : <span
            onDoubleClick={() => { if (!frozen) { setDraft(data.financial_item); setEditingRow(data.financial_item) } }}
            style={{ flex:1, overflow:'hidden', textOverflow:'ellipsis', whiteSpace:'nowrap',
              fontSize:13, fontWeight:depth===0?600:400,
              cursor: frozen ? 'default' : 'text' }}
            title={frozen ? data.financial_item : 'Double-click to rename'}>
            {data.financial_item}
          </span>
      }
    </Box>
  )
}

// ─── Main Component ────────────────────────────────────────────────────────────
export default function InputPage() {
  const { filter } = useFilter()
  const { company: companyId, periodType: mode, reportType } = filter
  const { mode: themeMode } = useThemeMode()
  const navigate = useNavigate()
  const BG       = themeMode === 'dark' ? BG_DARK : BG_LIGHT
  const SEL_COLOR  = themeMode === 'dark' ? SEL_COLOR_DARK  : SEL_COLOR_LIGHT
  const SEL_BORDER = themeMode === 'dark' ? SEL_BORDER_DARK : SEL_BORDER_LIGHT

  const [rows, setRows]             = useState<GRow[]>([])
  const [years, setYears]           = useState<string[]>([])
  const [activeTab, setActiveTab]   = useState(0)
  const [unit, setUnit]             = useState<'million'|'crore'>('million')
  const [loading, setLoading]       = useState(false)
  const [analyzing, setAnalyzing]   = useState(false)
  const [saving, setSaving]         = useState(false)
  const [dirty, setDirty]           = useState(false)
  const [hadDeletes, setHadDeletes] = useState(false) // track if user deleted cells
  const [freezeMode, setFreezeMode] = useState<FreezeMode>('frozen')
  const [dataSource, setDataSource] = useState<'warehouse'|'staged'|'empty'>('empty')
  const [snack, setSnack]           = useState<{msg:string;sev:'success'|'error'|'info'|'warning'}|null>(null)
  const [addYearOpen, setAddYearOpen]   = useState(false)
  const [newYearVal, setNewYearVal]     = useState('')
  const [search, setSearch]             = useState('')
  const [editingRow, setEditingRow]     = useState<string|null>(null)
  const [ctxMenu, setCtxMenu]           = useState<{x:number;y:number;rowData:GRow}|null>(null)
  const [deleteColDlg, setDeleteColDlg] = useState<string|null>(null)
  const [discardDlg, setDiscardDlg]     = useState(false)
  const [modifiedCells, setModifiedCells] = useState<Set<string>>(new Set())

  // Selection
  const [selRange, setSelRange]   = useState<SelRange|null>(null)
  const selCellsRef = useRef<Set<string>>(new Set())
  const isDragging  = useRef(false)
  const dragStart   = useRef<CellCoord|null>(null)

  // History
  const history    = useRef<HistEntry[]>([])
  const histIdx    = useRef<number>(-1)
  const gridRef    = useRef<any>(null)
  const rowsRef     = useRef<GRow[]>([])
  const yearsRef    = useRef<string[]>([])
  const origRowsRef = useRef<GRow[]>([])
  const treeRowsRef   = useRef<GRow[]>([])  // mirrors displayed treeRows for rowIndex-based ops
  const saveTimer     = useRef<ReturnType<typeof setTimeout>>()
  const reqCompanyRef = useRef<string>('')  // latest requested company — guards stale responses
  // Always points at the CURRENT-render doSave. applyRows is memoized with [] deps
  // and would otherwise capture the first render's doSave (companyId='') forever,
  // making the debounced auto-save a silent no-op — or worse, persist under a stale
  // company id. Routing the timer through this ref guarantees auto-save uses the
  // live companyId every time.
  const doSaveRef     = useRef<(rows: GRow[], explicit?: boolean) => Promise<void>>()

  useEffect(() => { yearsRef.current = years }, [years])

  // ── History helpers ──────────────────────────────────────────────
  const snapshot = (desc: string, data: GRow[]) => {
    history.current = history.current.slice(0, histIdx.current + 1)
    history.current.push({ rows: JSON.parse(JSON.stringify(data)), desc })
    if (history.current.length > 50) history.current.shift()
    histIdx.current = history.current.length - 1
  }

  const applyRows = useCallback((newRows: GRow[], autoSave = true) => {
    rowsRef.current = newRows
    setRows([...newRows])
    setDirty(true)
    if (autoSave) {
      clearTimeout(saveTimer.current)
      // Call through the ref so the auto-save always uses the latest doSave
      // (bound to the current companyId), not the first-render closure.
      saveTimer.current = setTimeout(() => doSaveRef.current?.(newRows, false), 1200)
    }
  }, [])

  const undo = useCallback(() => {
    if (histIdx.current <= 0) return
    histIdx.current--
    applyRows(history.current[histIdx.current].rows, false)
    setSnack({ msg: `Undo: ${history.current[histIdx.current].desc}`, sev: 'info' })
  }, [applyRows])

  const redo = useCallback(() => {
    if (histIdx.current >= history.current.length - 1) return
    histIdx.current++
    applyRows(history.current[histIdx.current].rows, false)
    setSnack({ msg: `Redo: ${history.current[histIdx.current].desc}`, sev: 'info' })
  }, [applyRows])

  // ── Workspace load (warehouse → staging overlay) ─────────────────
  const loadWorkspace = useCallback(() => {
    if (!companyId) return
    // Cancel any pending auto-save before loading new company data.
    // Without this, a stale timer from the previous company fires doSave()
    // with old rows but the new companyId, corrupting the new company's data.
    clearTimeout(saveTimer.current)
    reqCompanyRef.current = companyId
    const loadedFor = companyId
    setLoading(true)
    fetchWorkspace(companyId, mode, reportType)
      .then((data: any) => {
        if (reqCompanyRef.current !== loadedFor) return
        const initial = data.rows.map((r: GRow) => ({
          ...r, _depth:0, _hasChildren:false, _collapsed:false
        }))
        setYears(data.years)
        rowsRef.current    = initial
        origRowsRef.current = JSON.parse(JSON.stringify(initial))
        setRows(initial)
        history.current   = [{ rows: JSON.parse(JSON.stringify(initial)), desc: 'Load' }]
        histIdx.current   = 0
        setDirty(false)
        setHadDeletes(false)
        setModifiedCells(new Set())
        setSelRange(null)
        selCellsRef.current = new Set()

        // Surface warehouse-layer errors as non-blocking warnings
        if (data.warehouse_error) {
          setSnack({ msg: `Warehouse warning: ${data.warehouse_error}`, sev: 'warning' })
        }

        // Auto-freeze if any data loaded; blank companies open in edit mode
        if (data.has_warehouse_data || data.has_any_data) {
          setFreezeMode('frozen')
          setDataSource(data.has_warehouse_data ? 'warehouse' : 'staged')
          if (!data.warehouse_error) {
            const src = data.has_warehouse_data ? 'warehouse' : 'staging'
            const filled = (data.rows as GRow[]).filter((r: GRow) => r._source !== 'empty').length
            setSnack({ msg: `Loaded ${filled} rows from ${src}`, sev: 'success' })
          }
        } else {
          setFreezeMode('editing')
          setDataSource('empty')
          if (!data.warehouse_error) {
            setSnack({ msg: 'No warehouse data — enter values and click Analyze', sev: 'info' })
          }
        }
      })
      .catch((e: any) => {
        if (reqCompanyRef.current !== loadedFor) return
        const status = e?.response?.status
        const msg = status === 404
          ? 'Company not found in warehouse — enter data manually'
          : status === 500
            ? `Workspace load error: ${e?.response?.data?.detail || 'server error'}`
            : 'Cannot reach backend — is the server running?'
        setSnack({ msg, sev: 'error' })
        // Still open blank template so analyst can work
        setFreezeMode('editing')
        setDataSource('empty')
      })
      .finally(() => { if (reqCompanyRef.current === loadedFor) setLoading(false) })
  }, [companyId, mode, reportType])

  useEffect(() => { loadWorkspace() }, [loadWorkspace])

  // ── Freeze / Unfreeze ────────────────────────────────────────────
  const handleUnfreeze = () => {
    setFreezeMode('editing')
    setSnack({ msg: '🔓 Edit mode — changes will create a new version on save', sev: 'info' })
  }

  const handleDiscard = () => {
    rowsRef.current = JSON.parse(JSON.stringify(origRowsRef.current))
    setRows([...rowsRef.current])
    history.current = [{ rows: JSON.parse(JSON.stringify(origRowsRef.current)), desc: 'Discarded changes' }]
    histIdx.current = 0
    setDirty(false)
    setHadDeletes(false)
    setModifiedCells(new Set())
    setFreezeMode('frozen')
    setDiscardDlg(false)
    setSnack({ msg: 'Changes discarded', sev: 'info' })
  }

  // ── Selection display ────────────────────────────────────────────
  const updateSelectionDisplay = useCallback((range: SelRange | null, yrs: string[]) => {
    selCellsRef.current = rangeToSet(range, yrs)
    gridRef.current?.api?.refreshCells({ force: true, suppressFlash: true })
  }, [])

  // ── Mouse selection ──────────────────────────────────────────────
  const onCellMouseDown = useCallback((e: any) => {
    if (freezeMode === 'frozen') return
    const col = e.column?.getColId?.()
    if (!col || !yearsRef.current.includes(col)) return
    const row = e.rowIndex ?? 0
    isDragging.current = true
    dragStart.current  = { row, col }
    const range = { start: { row, col }, end: { row, col } }
    setSelRange(range)
    updateSelectionDisplay(range, yearsRef.current)
  }, [freezeMode, updateSelectionDisplay])

  const onCellMouseOver = useCallback((e: any) => {
    if (!isDragging.current || !dragStart.current) return
    const col = e.column?.getColId?.()
    if (!col || !yearsRef.current.includes(col)) return
    const row = e.rowIndex ?? 0
    const range = { start: dragStart.current, end: { row, col } }
    setSelRange(range)
    updateSelectionDisplay(range, yearsRef.current)
  }, [updateSelectionDisplay])

  useEffect(() => {
    const onUp = () => { isDragging.current = false }
    window.addEventListener('mouseup', onUp)
    return () => window.removeEventListener('mouseup', onUp)
  }, [])

  // ── Tree ops ─────────────────────────────────────────────────────
  const onToggle = useCallback((item: string) => {
    const u = rowsRef.current.map(r => r.financial_item===item ? {...r,_collapsed:!r._collapsed} : r)
    rowsRef.current = u; setRows([...u])
  }, [])

  const onRename = useCallback((oldName: string, newName: string) => {
    const t = newName.trim()
    if (!t || t===oldName) return
    if (rowsRef.current.some(r => r.financial_item===t)) { setSnack({msg:'Name exists',sev:'error'}); return }
    snapshot('Rename', rowsRef.current)
    applyRows(rowsRef.current.map(r => ({
      ...r,
      financial_item: r.financial_item===oldName ? t : r.financial_item,
      parent_item:    r.parent_item===oldName    ? t : r.parent_item,
    })))
  }, [applyRows])

  // ── Cell value change ─────────────────────────────────────────────
  const onCellValueChanged = useCallback((e: CellValueChangedEvent) => {
    if (freezeMode === 'frozen') return
    if ((e.data as any)?._isComputed || (e.data as any)?._isSection) return
    snapshot('Edit cell', rowsRef.current)
    const colId = e.column.getColId()
    let u = rowsRef.current.map((r: GRow) =>
      r.financial_item===e.data.financial_item && r.category===e.data.category
        ? { ...r, [colId]: e.newValue, _modified: true }
        : r
    )
    const changed = u.find(r => r.financial_item===e.data.financial_item)
    if (changed?.parent_item) {
      const parent = u.find(r => r.financial_item===changed.parent_item)
      if (parent) u = u.map(r => r.financial_item===parent.financial_item ? sumChildren(u, parent, years) : r)
    }
    // Track which cells were modified
    setModifiedCells(prev => new Set(prev).add(`${e.rowIndex}::${colId}`))
    applyRows(u)
  }, [freezeMode, years, applyRows])

  // ── Delete range ─────────────────────────────────────────────────
  const deleteRange = useCallback((range: SelRange | null) => {
    if (freezeMode === 'frozen') return
    if (!range) return
    const r0 = Math.min(range.start.row, range.end.row)
    const r1 = Math.max(range.start.row, range.end.row)
    const c0i = Math.min(years.indexOf(range.start.col), years.indexOf(range.end.col))
    const c1i = Math.max(years.indexOf(range.start.col), years.indexOf(range.end.col))
    if (c0i < 0 || c1i < 0) return
    const colsToClear = years.slice(c0i, c1i + 1)
    const rowKeys = new Set<string>()
    for (let ri = r0; ri <= r1; ri++) {
      const row = treeRowsRef.current[ri]
      if (row && !row._isSection && !row._isComputed) rowKeys.add(row.financial_item)
    }
    if (!rowKeys.size) return
    const total = rowKeys.size * colsToClear.length
    snapshot('Delete range', rowsRef.current)
    setHadDeletes(true)
    const u = rowsRef.current.map(r => {
      if (!rowKeys.has(r.financial_item) || r.category !== CATS[activeTab]) return r
      const patch = { ...r, _modified: true }
      colsToClear.forEach(col => { patch[col] = null })
      return patch
    })
    applyRows(u)
    setSnack({ msg: `Cleared ${total} cell${total>1?'s':''}`, sev: 'info' })
  }, [freezeMode, years, activeTab, applyRows])

  // ── Copy ─────────────────────────────────────────────────────────
  const copyRange = useCallback((range: SelRange | null) => {
    if (!range) return
    const r0 = Math.min(range.start.row, range.end.row)
    const r1 = Math.max(range.start.row, range.end.row)
    const c0 = Math.min(years.indexOf(range.start.col), years.indexOf(range.end.col))
    const c1 = Math.max(years.indexOf(range.start.col), years.indexOf(range.end.col))
    if (c0 < 0) return
    const lines: string[] = []
    for (let ri = r0; ri <= r1; ri++) {
      const row = treeRowsRef.current[ri]
      if (!row || row._isSection) continue
      const cells: string[] = []
      for (let ci = c0; ci <= c1; ci++) {
        const v = row[years[ci]]
        cells.push(v == null ? '' : unit==='crore' ? String(v/CRORE_TO_MN) : String(v))
      }
      lines.push(cells.join('\t'))
    }
    navigator.clipboard.writeText(lines.join('\n')).catch(() => {})
    setSnack({ msg: `Copied ${cellCount(range, years)} cells`, sev: 'info' })
  }, [years, activeTab, unit])

  // ── Paste ─────────────────────────────────────────────────────────
  useEffect(() => {
    const handler = (e: ClipboardEvent) => {
      if (freezeMode === 'frozen') return
      const text = e.clipboardData?.getData('text/plain')
      if (!text) return
      const api = gridRef.current?.api; if (!api) return
      let anchorRow = selRange?.start.row
      let anchorCol = selRange?.start.col
      if (anchorRow == null) {
        const fc = api.getFocusedCell()
        if (!fc || !years.includes(fc.column.getColId())) return
        anchorRow = fc.rowIndex ?? 0; anchorCol = fc.column.getColId()
      }
      if (anchorCol == null || !years.includes(anchorCol)) return
      e.preventDefault()
      snapshot('Paste', rowsRef.current)
      const pasteRows = text.trimEnd().split('\n').map((r: string) => r.split('\t'))
      const colStart  = years.indexOf(anchorCol)
      const colOrder  = years.slice(colStart)
      const u         = [...rowsRef.current]
      const newMod    = new Set(modifiedCells)
      pasteRows.forEach((pr: string[], ri: number) => {
        const target = treeRowsRef.current[anchorRow! + ri]
        if (!target || target._isSection || target._isComputed) return
        const mi = u.findIndex(r => r.financial_item === target.financial_item && r.category === target.category)
        if (mi < 0) return
        pr.forEach((cell: string, ci: number) => {
          const col = colOrder[ci]; if (!col) return
          const num = parseFloat(cell.replace(/,/g,'').trim())
          const val = isNaN(num) ? null : (unit==='crore' ? num*CRORE_TO_MN : num)
          u[mi] = { ...u[mi], [col]: val, _modified: true }
          newMod.add(`${anchorRow! + ri}::${col}`)
        })
      })
      setModifiedCells(newMod)
      applyRows(u)
      const lr = Math.min(anchorRow! + pasteRows.length - 1, treeRowsRef.current.length - 1)
      const lc = years[Math.min(colStart + (Math.max(...pasteRows.map((r:string[])=>r.length)) - 1), years.length-1)]
      setSelRange({ start:{row:anchorRow!,col:anchorCol}, end:{row:lr,col:lc} })
      setSnack({ msg: `Pasted ${pasteRows.length}×${pasteRows[0]?.length||1} cells`, sev: 'success' })
    }
    window.addEventListener('paste', handler)
    return () => window.removeEventListener('paste', handler)
  }, [freezeMode, years, activeTab, unit, selRange, modifiedCells, applyRows])

  // ── Keyboard shortcuts ────────────────────────────────────────────
  useEffect(() => {
    const handler = (e: KeyboardEvent) => {
      const tag = (e.target as HTMLElement)?.tagName
      if (['INPUT','TEXTAREA'].includes(tag)) return
      if ((e.ctrlKey||e.metaKey) && e.key==='z') { e.preventDefault(); undo(); return }
      if ((e.ctrlKey||e.metaKey) && e.key==='y') { e.preventDefault(); redo(); return }
      if ((e.ctrlKey||e.metaKey) && e.key==='c') { e.preventDefault(); copyRange(selRange); return }
      if ((e.key==='Delete'||e.key==='Backspace') && freezeMode!=='frozen') {
        if (selRange) { e.preventDefault(); deleteRange(selRange); return }
        const api = gridRef.current?.api; if (!api) return
        const fc = api.getFocusedCell()
        if (!fc || !years.includes(fc.column.getColId())) return
        e.preventDefault()
        const col = fc.column.getColId(); const ri = fc.rowIndex ?? 0
        const target = treeRowsRef.current[ri]
        if (!target || target._isSection || target._isComputed) return
        snapshot('Delete cell', rowsRef.current)
        setHadDeletes(true)
        applyRows(rowsRef.current.map(r =>
          r.financial_item===target.financial_item && r.category===target.category ? { ...r, [col]: null, _modified: true } : r
        ))
        return
      }
      if (e.shiftKey && ['ArrowRight','ArrowLeft','ArrowDown','ArrowUp'].includes(e.key)) {
        e.preventDefault()
        if (!selRange) return
        const { end } = selRange; const ci = years.indexOf(end.col)
        let nr = end.row, nc = ci
        if (e.key==='ArrowRight') nc = Math.min(ci+1, years.length-1)
        if (e.key==='ArrowLeft')  nc = Math.max(ci-1, 0)
        if (e.key==='ArrowDown')  nr = end.row + 1
        if (e.key==='ArrowUp')    nr = Math.max(end.row-1, 0)
        const newRange = { start: selRange.start, end: { row: nr, col: years[nc] } }
        setSelRange(newRange); updateSelectionDisplay(newRange, years)
      }
      if (e.key==='Escape') { setSelRange(null); updateSelectionDisplay(null, yearsRef.current) }
    }
    window.addEventListener('keydown', handler)
    return () => window.removeEventListener('keydown', handler)
  }, [undo, redo, copyRange, deleteRange, selRange, years, activeTab, freezeMode, applyRows, updateSelectionDisplay])

  // ── Save ──────────────────────────────────────────────────────────
  const doSave = async (current: GRow[], explicit = true) => {
    if (!companyId) return
    // Pin the company this save targets. Every persisted row is tagged with
    // saveFor (not the live companyId) so an in-flight save can never write the
    // previous company's grid under a newly-selected company.
    const saveFor = companyId
    setSaving(true)

    // Build what to save:
    // - Non-null values: normal rows
    // - Null values for warehouse items: NULL tombstones (explicit deletions)
    //   A tombstone tells the workspace overlay "user deleted this cell"
    //   so the warehouse value doesn't reappear on restart.
    const periodsWithData = new Set<string>()
    const toSave: InputRow[] = []

    // Build the set of (item, category, year) combinations that exist in warehouse
    // so we know which nulls need tombstones vs which are just blanks never entered
    // We write tombstones for ALL rows the user has seen in edit mode — this ensures
    // any cell they blanked out explicitly overrides warehouse on reload.

    for (const row of current) {
      if ((row as any)._isComputed) continue   // skip computed rows — never persist them
      for (const y of yearsRef.current) {
        const sortOrd = Math.round(row.sort_order ?? 0)   // must be int — backend rejects floats (422)
        if (row[y] != null) {
          // Real value — always save
          toSave.push({
            company_id: saveFor, period_label: y,
            financial_item: row.financial_item, category: row.category,
            value: row[y], units: 'INR Million', sort_order: sortOrd,
            parent_item: row.parent_item || null,
          })
          periodsWithData.add(y)
        } else if (row._source === 'warehouse' || row._source === 'staged') {
          // NULL tombstone — user cleared a cell that previously had warehouse data.
          // Store NULL explicitly so workspace overlay knows to show blank, not warehouse value.
          toSave.push({
            company_id: saveFor, period_label: y,
            financial_item: row.financial_item, category: row.category,
            value: null, units: 'INR Million', sort_order: sortOrd,
            parent_item: row.parent_item || null,
          })
        }
      }
    }

    // Periods where ALL values are now null/absent
    const periodsNowEmpty = yearsRef.current.filter(y => !periodsWithData.has(y))

    try {
      if (hadDeletes) {
        // 1. Clear SQLite staging for ALL periods (re-save remaining below)
        for (const y of yearsRef.current) {
          await api.delete(`/financial-input/${saveFor}/${y}`).catch(() => {})
        }

        // 2. Deactivate warehouse rows for each TRULY EMPTY period
        //    This is the key fix: warehouse must reflect the deletion
        for (const y of periodsNowEmpty) {
          await api.post(`/calculate/invalidate/${saveFor}?period=${y}`).catch(() => {})
        }

        // 3. If ALL periods empty, deactivate entire company in warehouse
        if (periodsWithData.size === 0) {
          await api.post(`/calculate/invalidate/${saveFor}`).catch(() => {})
        }
      }

      if (toSave.length) {
        const res = await bulkSave(toSave)
        if (explicit) {
          setDirty(false)
          setHadDeletes(false)
          setFreezeMode('frozen')
          origRowsRef.current = JSON.parse(JSON.stringify(current))
          setModifiedCells(new Set())
          const emptyNote = periodsNowEmpty.length > 0
            ? ` · ${periodsNowEmpty.join(', ')} cleared from dashboard`
            : ''
          setSnack({ msg: `Saved ${res.saved} cells${emptyNote}`, sev: 'success' })
        }
      } else if (hadDeletes) {
        // All values deleted — warehouse deactivated above
        if (explicit) {
          setDirty(false)
          setHadDeletes(false)
          setFreezeMode('frozen')
          setDataSource('empty')
          setSnack({ msg: 'All data cleared — dashboard will show empty', sev: 'warning' })
        }
      }
    } catch (e: any) {
      setSnack({ msg: `Save failed: ${e?.message || 'unknown error'}`, sev: 'error' })
    } finally { setSaving(false) }
  }
  // Keep the ref pointed at the live doSave so the debounced auto-save in
  // applyRows (memoized with [] deps) never fires a stale-company closure.
  doSaveRef.current = doSave

  // ── Analyze ───────────────────────────────────────────────────────
  const handleAnalyze = async () => {
    setAnalyzing(true)
    try {
      // 1. Save current company's staged data first
      await doSave(rowsRef.current, false)
      // 2. Analyze ALL companies in one backend call
      const res = await calculateAllCompanies()
      const total    = res.analyzed?.length ?? 0
      const failed   = Object.keys(res.failed ?? {}).length
      const elapsed  = res.elapsed_s ?? 0
      const msg = failed > 0
        ? `Analysis done: ${total} ok, ${failed} failed (${elapsed}s) — check Dashboard`
        : `All ${total} companies analyzed in ${elapsed}s — opening Dashboard…`
      setSnack({ msg, sev: failed > 0 ? 'warning' : 'success' })
      // 3. Navigate to Dashboard so user sees results immediately
      setTimeout(() => navigate('/dashboard'), 600)
    } catch (e: any) {
      setSnack({ msg: e.response?.data?.detail || 'Analysis failed', sev: 'error' })
    } finally { setAnalyzing(false) }
  }

  // ── Column management ─────────────────────────────────────────────
  const handleAddYear = () => {
    const y = newYearVal.trim().toUpperCase()
    if (!y || years.includes(y)) return
    setYears([y, ...years])
    applyRows(rowsRef.current.map(r => ({ ...r, [y]: null })))
    setNewYearVal(''); setAddYearOpen(false)
  }

  const deleteColumn = (col: string) => {
    snapshot('Delete column', rowsRef.current)
    setYears(prev => prev.filter(y => y !== col))
    setHadDeletes(true)
    applyRows(rowsRef.current.map(r => { const n={...r}; delete n[col]; return n }))
    setDeleteColDlg(null)
  }

  // ── Row management ────────────────────────────────────────────────
  const insertRow = (parentName?: string) => {
    if (freezeMode === 'frozen') return
    const api   = gridRef.current?.api
    const sel   = api?.getSelectedNodes()
    const idx   = sel?.length ? (sel[0].rowIndex ?? 0) : 0
    const name  = `New Item ${Date.now().toString().slice(-4)}`
    const depth = parentName
      ? Math.min((rowsRef.current.find(r=>r.financial_item===parentName)?._depth||0)+1, MAX_DEPTH) : 0
    const blank: GRow = {
      financial_item: name, category: CATS[activeTab],
      units: 'INR Million', sort_order: idx + 1,
      parent_item: parentName||null, _depth: depth, _hasChildren: false, _collapsed: false,
    }
    yearsRef.current.forEach(y => { blank[y] = null })
    snapshot('Insert row', rowsRef.current)
    const filt  = rowsRef.current.filter(r => r.category===CATS[activeTab])
    const after = filt[idx]
    const mi    = after ? rowsRef.current.indexOf(after) : rowsRef.current.length-1
    applyRows([...rowsRef.current.slice(0,mi+1), blank, ...rowsRef.current.slice(mi+1)])
    setTimeout(() => setEditingRow(name), 50)
  }

  const addChildRow = (parent: GRow) => {
    if (parent._depth >= MAX_DEPTH-1) { setSnack({msg:`Max depth ${MAX_DEPTH}`,sev:'info'}); return }
    applyRows(rowsRef.current.map(r => r.financial_item===parent.financial_item ? {...r,_hasChildren:true} : r))
    insertRow(parent.financial_item)
  }

  const deleteRow = (rowData?: GRow) => {
    if (freezeMode === 'frozen') return
    const targets = new Set<string>()
    if (rowData) {
      if (rowData._isSection || rowData._isComputed) return
      targets.add(rowData.financial_item)
      const addCh = (n: string) => rowsRef.current.filter(r=>r.parent_item===n).forEach(c => { targets.add(c.financial_item); addCh(c.financial_item) })
      addCh(rowData.financial_item)
    } else {
      gridRef.current?.api?.getSelectedNodes()?.forEach((n:any) => targets.add(n.data.financial_item))
    }
    if (!targets.size) return
    snapshot('Delete row', rowsRef.current)
    setHadDeletes(true)
    applyRows(rowsRef.current.filter(r => !targets.has(r.financial_item)))
  }

  const duplicateRow = (rowData: GRow) => {
    snapshot('Duplicate', rowsRef.current)
    const copy = { ...rowData, financial_item: `${rowData.financial_item} (copy)` }
    const idx  = rowsRef.current.indexOf(rowData)
    applyRows([...rowsRef.current.slice(0,idx+1), copy, ...rowsRef.current.slice(idx+1)])
  }

  // ── Column defs ───────────────────────────────────────────────────
  const colDefs: ColDef[] = useMemo(() => [
    {
      field: 'financial_item', headerName: 'Particulars', pinned: 'left',
      width: 280, editable: false, suppressSizeToFit: true,
      cellRenderer: (p: ICellRendererParams) => (
        <ParticularsRenderer {...p} onToggle={onToggle} onRename={onRename}
          editingRow={editingRow} setEditingRow={setEditingRow} frozen={freezeMode==='frozen'} />
      ),
    },
    {
      field: 'units', headerName: 'Units', width: 120, editable: freezeMode==='editing',
      cellEditor: 'agSelectCellEditor', cellEditorParams: { values: UNIT_OPTS },
      cellStyle: { color: themeMode === 'dark' ? '#707a8a' : '#6e6e73', fontSize: 12, fontWeight: 400 },
      valueFormatter: (p: any) => {
        if (p.value === 'INR Million' && unit === 'crore') return 'INR Crore'
        return p.value ?? ''
      },
    },
    ...years.map(y => ({
      field: y, headerName: y, width: 130,
      editable: (p: any) => freezeMode==='editing' && !p.data?._isComputed && !p.data?._isSection,
      headerComponent: (p: any) => (
        <Stack direction="row" alignItems="center" sx={{ height:'100%', gap:0.5 }}>
          <span style={{ fontSize:13, fontWeight:600, color: themeMode==='dark' ? '#eaecef' : '#4a5568' }}>{y}</span>
          {freezeMode==='editing' && (
            <Box component="span" onClick={(e) => { e.stopPropagation(); setDeleteColDlg(y) }}
              sx={{ opacity:0, '.ag-header-cell:hover &':{opacity:1}, cursor:'pointer', color:'#DC2626', fontSize:11 }}
              title={`Delete ${y}`}>✕</Box>
          )}
        </Stack>
      ),
      cellStyle: (p: any) => {
        const key = `${p.rowIndex}::${y}`
        const selected = selCellsRef.current.has(key)
        const modified = modifiedCells.has(key)
        const hasVal   = p.value != null
        let bg = BG.frozen_empty
        if (freezeMode === 'frozen') {
          const src = p.data?._source as RowSource
          bg = src==='warehouse' ? BG.frozen_warehouse : src==='staged' ? BG.frozen_staged : BG.frozen_empty
        } else if (modified) {
          bg = BG.editing_modified
        } else if (hasVal) {
          bg = BG.editing_value
        } else {
          bg = BG.editing_empty
        }
        return {
          fontWeight: 500,
          background: selected ? SEL_COLOR : bg,
          outline: selected ? SEL_BORDER : undefined,
          outlineOffset: '-1px',
          cursor: freezeMode==='frozen' ? 'default' : 'cell',
        }
      },
      valueFormatter: (p: any) => {
        if (p.value==null || p.value==='') return ''
        const v = unit==='crore' ? p.value/CRORE_TO_MN : p.value
        return Number(v).toLocaleString('en-IN',{maximumFractionDigits:2})
      },
      valueParser: (p: any) => {
        if (p.newValue===''||p.newValue==null) return null
        const num = parseFloat(String(p.newValue).replace(/,/g,''))
        if (isNaN(num)) return null
        return unit==='crore' ? num*CRORE_TO_MN : num
      },
    } as ColDef)),
  ], [years, unit, onToggle, onRename, editingRow, freezeMode, modifiedCells, themeMode, BG, SEL_COLOR, SEL_BORDER])

  // ── Tree rows ─────────────────────────────────────────────────────
  const treeRows = useMemo(() => {
    let result: GRow[]

    if (CATS[activeTab] === 'Altman Z') {
      const cat    = rowsRef.current.filter(r => r.category === 'Altman Z')
      const byItem = new Map<string, GRow>()
      cat.forEach(r => byItem.set(r.financial_item, r))

      result = []
      for (const section of ALTMAN_SECTIONS) {
        result.push({
          financial_item: section.label,
          category: 'Altman Z',
          _isSection: true,
          _depth: 0, _hasChildren: false, _collapsed: false,
          _source: 'empty',
        })
        for (const item of section.items) {
          const row = byItem.get(item)
          if (row) {
            result.push({ ...row, _depth: 1, _hasChildren: false })
          } else {
            const blank: GRow = {
              financial_item: item, category: 'Altman Z',
              units: 'INR Million', sort_order: 0,
              parent_item: null,
              _depth: 1, _hasChildren: false, _collapsed: false, _source: 'empty',
            }
            years.forEach(y => { blank[y] = null })
            result.push(blank)
          }
        }
      }
    } else {
      const cat   = rowsRef.current.filter(r => r.category === CATS[activeTab])
      const built = buildTree(cat)

      const getVal = (item: string, y: string): number => {
        const row = cat.find(r => r.financial_item === item)
        const v = row?.[y]
        return (v != null && !isNaN(Number(v))) ? Number(v) : 0
      }
      const remRow: GRow = {
        financial_item: 'Remaining Expenses',
        category: CATS[activeTab],
        units: 'INR Million',
        sort_order: 9999,
        parent_item: null,
        _depth: 0, _hasChildren: false, _collapsed: false,
        _isComputed: true, _source: 'empty',
      }
      years.forEach(y => {
        const tc = getVal('Total Cost', y)
        if (tc === 0) { remRow[y] = null; return }
        const sub = RE_SUBTRACTORS.reduce((s, item) => s + getVal(item, y), 0)
        remRow[y] = parseFloat((tc - sub).toFixed(4))
      })
      built.push(remRow)
      result = built
    }

    const q = search.trim().toLowerCase()
    if (q) result = result.filter(r => r._isSection || r.financial_item.toLowerCase().includes(q))

    treeRowsRef.current = result
    return result
  }, [rows, activeTab, search, years])

  const canUndo = histIdx.current > 0
  const canRedo = histIdx.current < history.current.length - 1
  const cnt     = cellCount(selRange, years)
  const frozen  = freezeMode === 'frozen'

  if (!companyId) return (
    <Box sx={{display:'flex',alignItems:'center',justifyContent:'center',height:400}}>
      <Typography color="text.secondary">Select a company in the top bar</Typography>
    </Box>
  )

  // ── Render ────────────────────────────────────────────────────────
  return (
    <Box>
      {/* Header */}
      <Stack direction="row" justifyContent="space-between" alignItems="flex-start" mb={0.75} flexWrap="wrap" gap={1}>
        <Box>
          <Typography variant="h5" fontWeight={800} color="text.primary">Data Input</Typography>
          <Typography variant="body2" color="text.secondary">
            {companyId} ·{frozen
              ? ' Data loaded — click Unfreeze to edit'
              : ' Edit mode — drag to select, Ctrl+V to paste, Delete to clear'}
          </Typography>
        </Box>
        <Stack direction="row" spacing={1} alignItems="center" flexWrap="wrap">
          {dirty && !frozen && <Chip label="● Unsaved" size="small" color="warning" sx={{fontWeight:700}}/>}
          {cnt > 0 && <Chip label={`${cnt} selected`} size="small" sx={{bgcolor:'rgba(252,213,53,0.15)',color:'#FCD535',fontWeight:600}}/>}
          <ToggleButtonGroup value={unit} exclusive size="small" onChange={(_,v)=>v&&setUnit(v)}
            sx={{'& .MuiToggleButton-root':{px:1.5,py:0.4,fontSize:12,textTransform:'none'}}}>
            <ToggleButton value="million">₹ Mn</ToggleButton>
            <ToggleButton value="crore">₹ Cr</ToggleButton>
          </ToggleButtonGroup>
        </Stack>
      </Stack>

      {/* Freeze/Unfreeze status bar */}
      {frozen && dataSource !== 'empty' ? (
        <Alert
          severity="info"
          icon={<LockIcon fontSize="small" />}
          sx={{ mb:0.75, py:0.3 }}
          action={
            <Button size="small" startIcon={<LockOpenIcon />}
              onClick={handleUnfreeze} variant="contained"
              sx={{bgcolor:'#FCD535', color:'#181a20', '&:hover':{bgcolor:'#f0b90b'}, ml:1}}>
              Unfreeze
            </Button>
          }
        >
          <strong>🔒 Data loaded from {dataSource === 'warehouse' ? 'warehouse' : 'staging'}.</strong>
          {' '}Read-only. Click Unfreeze to edit and create a new version.
        </Alert>
      ) : !frozen && (
        <Alert severity="warning" icon={<LockOpenIcon fontSize="small" />} sx={{ mb:0.75, py:0.3 }}
          action={
            <Stack direction="row" spacing={0.5}>
              <Button size="small" startIcon={<DiscardIcon />}
                onClick={() => setDiscardDlg(true)} color="warning" variant="outlined">Discard</Button>
              <Button size="small" startIcon={saving ? <CircularProgress size={12}/> : <SaveIcon />}
                onClick={() => doSave(rowsRef.current, true)} variant="contained"
                disabled={saving || !dirty} sx={{bgcolor:'#FCD535', color:'#181a20', '&:hover':{bgcolor:'#f0b90b'}}}>
                {saving ? 'Saving…' : 'Save & Freeze'}
              </Button>
            </Stack>
          }
        >
          <strong>🔓 Edit mode</strong> — grey = original, orange = modified.
          {hadDeletes && ' ⚠ Deleted cells will invalidate dashboard on save.'}
        </Alert>
      )}

      {/* Toolbar — hidden in frozen/read-only mode */}
      {!frozen && <Paper variant="outlined" sx={{mb:0.75,px:1.5,py:0.4,display:'flex',alignItems:'center',
        gap:0.5,flexWrap:'nowrap',overflowX:'auto',bgcolor:'#1e2329',borderColor:'#2b3139'}}>
        <Tooltip title="Undo (Ctrl+Z)"><span>
          <MuiIconButton size="small" onClick={undo} disabled={!canUndo||frozen}
            sx={{color:canUndo&&!frozen?'#eaecef':'#2b3139'}}><UndoIcon fontSize="small"/></MuiIconButton>
        </span></Tooltip>
        <Tooltip title="Redo (Ctrl+Y)"><span>
          <MuiIconButton size="small" onClick={redo} disabled={!canRedo||frozen}
            sx={{color:canRedo&&!frozen?'#eaecef':'#2b3139'}}><RedoIcon fontSize="small"/></MuiIconButton>
        </span></Tooltip>
        <Box sx={{width:'2px',height:20,bgcolor:'#2b3139',mx:0.5}}/>
        <Tooltip title="Copy (Ctrl+C)">
          <MuiIconButton size="small" onClick={()=>copyRange(selRange)} disabled={!selRange}
            sx={{color:'#eaecef'}}><ContentCopyIcon fontSize="small"/></MuiIconButton>
        </Tooltip>
        <Tooltip title="Clear selected (Delete)">
          <MuiIconButton size="small" onClick={()=>deleteRange(selRange)} disabled={!selRange||frozen}
            sx={{color:'#eaecef'}}><DeleteOutlineIcon fontSize="small"/></MuiIconButton>
        </Tooltip>
        <Box sx={{width:'2px',height:20,bgcolor:'#2b3139',mx:0.5}}/>
        <Button size="small" startIcon={<AddIcon sx={{fontSize:'14px !important'}}/>}
          onClick={()=>insertRow()} disabled={frozen}
          sx={{fontSize:11,textTransform:'none',color:frozen?'#2b3139':'#eaecef',px:1}} variant="text">Row</Button>
        <Button size="small" startIcon={<DeleteOutlineIcon sx={{fontSize:'14px !important'}}/>}
          onClick={()=>deleteRow()} disabled={frozen}
          sx={{fontSize:11,textTransform:'none',color:frozen?'#CBD5E1':'#DC2626',px:1}} variant="text">Row</Button>
        <Box sx={{width:'2px',height:20,bgcolor:'#2b3139',mx:0.5}}/>
        <Button size="small" startIcon={<AddIcon sx={{fontSize:'14px !important'}}/>}
          onClick={()=>setAddYearOpen(true)} disabled={frozen}
          sx={{fontSize:11,textTransform:'none',color:frozen?'#2b3139':'#eaecef',px:1}} variant="text">Column</Button>
        <Box sx={{flex:1}}/>
        <Button variant={frozen?'outlined':'contained'} size="small"
          startIcon={analyzing?<CircularProgress size={12} color="inherit"/>:<PlayArrowIcon/>}
          onClick={handleAnalyze} disabled={analyzing}
          sx={{fontSize:12,textTransform:'none',bgcolor:frozen?undefined:'#FCD535', color:frozen?undefined:'#181a20',
            '&:hover':{bgcolor:frozen?undefined:'#f0b90b'}}}>
          {analyzing?'Analyzing…':'Analyze'}
        </Button>
        <Box sx={{flex:0,width:8}}/>
        <TextField size="small" placeholder="Search rows…" value={search}
          onChange={e=>setSearch(e.target.value)}
          InputProps={{
            startAdornment:<InputAdornment position="start"><SearchIcon sx={{fontSize:16,color:'#94A3B8'}}/></InputAdornment>,
            endAdornment:search?<InputAdornment position="end"><MuiIconButton size="small" onClick={()=>setSearch('')}><ClearIcon sx={{fontSize:14}}/></MuiIconButton></InputAdornment>:null,
          }}
          sx={{width:170,'& .MuiInputBase-root':{fontSize:12,height:32}}}
        />
      </Paper>}

      {/* Tabs */}
      <Paper sx={{mb:0.5}}>
        <Tabs value={activeTab} onChange={(_,v)=>setActiveTab(v)}
          sx={{borderBottom:1,borderColor:'divider',minHeight:38}}>
          {CATS.map(cat => <Tab key={cat}
            label={{ 'P&L Consolidated': 'Consolidated', 'P&L Standalone': 'Standalone' }[cat] ?? cat}
            sx={{fontWeight:600,fontSize:12,minHeight:38,textTransform:'none',py:0.5}}/>)}
        </Tabs>
      </Paper>

      {/* Grid */}
      {loading
        ? <Box sx={{display:'flex',flexDirection:'column',alignItems:'center',py:6,gap:2}}>
            <CircularProgress/>
            <Typography color="text.secondary" fontSize={13}>Loading workspace from warehouse…</Typography>
          </Box>
        : (
          <Paper sx={{height:600,overflow:'hidden',borderRadius:1.5,
            opacity: frozen ? 0.92 : 1,
            transition: 'opacity 0.2s',
          }}>
            <div className="ag-theme-alpine" style={{height:'100%',width:'100%'}}>
              <AgGridReact
                ref={(p:any) => { if(p) gridRef.current = p }}
                rowData={treeRows}
                columnDefs={colDefs}
                defaultColDef={{resizable:true}}
                onCellValueChanged={onCellValueChanged}
                onCellContextMenu={(e:any) => { if (!e.data?._isSection && !e.data?._isComputed) setCtxMenu({x:e.event?.clientX||0,y:e.event?.clientY||0,rowData:e.data}) }}
                onCellMouseDown={onCellMouseDown}
                onCellMouseOver={onCellMouseOver}
                suppressClipboardPaste={true}
                enableCellChangeFlash={!frozen}
                undoRedoCellEditing={false}
                rowSelection="multiple"
                rowHeight={34} headerHeight={40} animateRows
                getRowId={(p:any) => p.data._isSection ? `section__${p.data.financial_item}` : `${p.data.financial_item}__${p.data.category}`}
                getRowClass={(p:any) => p.data?._isSection ? 'section-header-row' : p.data?._isComputed ? 'computed-row' : ''}
                getRowStyle={(p:any) => {
                  const item = p.data?.financial_item||''
                  if (themeMode === 'dark') {
                    if (p.data?._isSection) return { background:'#181a20', fontWeight:700 }
                    if (p.data?._isComputed) return {}
                    const bold = ['Total Cost','Revenue from Operations','Total Income','Net Worth','Total Assets'].includes(item)
                    if (bold) return { background:'#0b0e11', fontWeight:700, color:'#FCD535' }
                    if (p.data?._depth===1) return { background:'#1e2329' }
                    if (p.data?._depth===2) return { background:'#1e2329' }
                    return {}
                  } else {
                    if (p.data?._isSection) return { background:'#eff6ff', fontWeight:700 }
                    if (p.data?._isComputed) return { background:'#f9fafb' }
                    const bold = ['Total Cost','Revenue from Operations','Total Income','Net Worth','Total Assets'].includes(item)
                    if (bold) return { background:'#f0fdf4', fontWeight:700, color:'#166534' }
                    if (p.data?._depth===1) return { background:'#fafafa' }
                    if (p.data?._depth===2) return { background:'#fafafa' }
                    return {}
                  }
                }}
              />
              <style>{getGridStyles(themeMode)}</style>
            </div>
          </Paper>
        )
      }
      {saving && <LinearProgress sx={{mt:0.5, borderRadius:1}}/>}

      {/* Footer */}
      <Stack direction="row" justifyContent="space-between" mt={0.8}>
        <Typography variant="caption" color="text.secondary">
          {treeRows.length} rows · {years.length} periods
          {cnt>0&&` · ${cnt} selected`}
          {hadDeletes&&!frozen&&<span style={{color:'#D97706'}}> · ⚠ Has deletions</span>}
        </Typography>
        <Stack direction="row" spacing={1}>
          {/* Legend */}
          {frozen && dataSource!=='empty' && (
            <Stack direction="row" spacing={0.5} alignItems="center">
              <Box sx={{width:10,height:10,bgcolor:BG.frozen_warehouse,border:'1px solid #2b3139',borderRadius:0.5}}/>
              <Typography variant="caption" color="text.secondary" sx={{fontSize:10}}>Warehouse</Typography>
              <Box sx={{width:10,height:10,bgcolor:BG.frozen_staged,border:'1px solid #2b3139',borderRadius:0.5}}/>
              <Typography variant="caption" color="text.secondary" sx={{fontSize:10}}>Staged</Typography>
            </Stack>
          )}
          {!frozen && (
            <Stack direction="row" spacing={0.5} alignItems="center">
              <Box sx={{width:10,height:10,bgcolor:BG.editing_value,border:'1px solid #2b3139',borderRadius:0.5}}/>
              <Typography variant="caption" color="text.secondary" sx={{fontSize:10}}>Original</Typography>
              <Box sx={{width:10,height:10,bgcolor:BG.editing_modified,border:'1px solid #2b3139',borderRadius:0.5}}/>
              <Typography variant="caption" color="text.secondary" sx={{fontSize:10}}>Modified</Typography>
            </Stack>
          )}
        </Stack>
      </Stack>

      {/* Context menu */}
      <Menu open={!!ctxMenu} onClose={()=>setCtxMenu(null)}
        anchorReference="anchorPosition"
        anchorPosition={ctxMenu?{top:ctxMenu.y,left:ctxMenu.x}:undefined}
        PaperProps={{sx:{minWidth:200,boxShadow:'0 4px 20px rgba(0,0,0,0.12)',borderRadius:1.5}}}>
        <Box sx={{px:1.5,py:0.5}}>
          <Typography variant="caption" color="text.secondary" fontWeight={700}>
            {ctxMenu?.rowData?.financial_item}
          </Typography>
        </Box>
        <MuiDivider/>
        <MenuItem onClick={()=>{if(!frozen){setEditingRow(ctxMenu!.rowData.financial_item)}setCtxMenu(null)}} dense disabled={frozen}>
          <ListItemIcon><span style={{fontSize:14}}>✏️</span></ListItemIcon>
          <ListItemText>Rename</ListItemText>
        </MenuItem>
        <MenuItem onClick={()=>{addChildRow(ctxMenu!.rowData);setCtxMenu(null)}} dense
          disabled={frozen||ctxMenu?.rowData?._depth>=MAX_DEPTH-1}>
          <ListItemIcon><SubdirectoryArrowRightIcon fontSize="small" sx={{color:'#FCD535'}}/></ListItemIcon>
          <ListItemText>Add child row</ListItemText>
        </MenuItem>
        <MenuItem onClick={()=>{duplicateRow(ctxMenu!.rowData);setCtxMenu(null)}} dense disabled={frozen}>
          <ListItemIcon><ContentCopyIcon fontSize="small"/></ListItemIcon>
          <ListItemText>Duplicate row</ListItemText>
        </MenuItem>
        {cnt>0&&[
          <MuiDivider key="d"/>,
          <MenuItem key="clr" onClick={()=>{deleteRange(selRange);setCtxMenu(null)}} dense disabled={frozen}>
            <ListItemIcon><DeleteOutlineIcon fontSize="small" sx={{color:'#DC2626'}}/></ListItemIcon>
            <ListItemText sx={{color:'#DC2626'}}>Clear {cnt} cells</ListItemText>
          </MenuItem>
        ]}
        <MuiDivider/>
        <MenuItem onClick={()=>{deleteRow(ctxMenu!.rowData);setCtxMenu(null)}} dense
          sx={{color:'#DC2626'}} disabled={frozen}>
          <ListItemIcon><DeleteOutlineIcon fontSize="small" sx={{color:'#DC2626'}}/></ListItemIcon>
          <ListItemText>Delete row</ListItemText>
        </MenuItem>
      </Menu>

      {/* Add Year */}
      <Dialog open={addYearOpen} onClose={()=>setAddYearOpen(false)} maxWidth="xs" fullWidth>
        <DialogTitle sx={{pb:1}}>Add Period Column</DialogTitle>
        <DialogContent>
          <TextField autoFocus fullWidth label="Period" size="small" value={newYearVal}
            onChange={e=>setNewYearVal(e.target.value)} placeholder="e.g. FY26 or Q1FY26"
            helperText="Adds a blank column — fill values then Analyze" sx={{mt:1}}/>
        </DialogContent>
        <DialogActions sx={{px:2,pb:2}}>
          <Button onClick={()=>setAddYearOpen(false)}>Cancel</Button>
          <Button onClick={handleAddYear} variant="contained" disabled={!newYearVal.trim()}>Add</Button>
        </DialogActions>
      </Dialog>

      {/* Delete Column */}
      <Dialog open={!!deleteColDlg} onClose={()=>setDeleteColDlg(null)} maxWidth="xs" fullWidth>
        <DialogTitle sx={{color:'#DC2626',pb:1}}>Delete Column {deleteColDlg}?</DialogTitle>
        <DialogContent>
          <Typography variant="body2">
            All values in <strong>{deleteColDlg}</strong> will be removed. This invalidates the dashboard.
          </Typography>
        </DialogContent>
        <DialogActions sx={{px:2,pb:2}}>
          <Button onClick={()=>setDeleteColDlg(null)}>Cancel</Button>
          <Button color="error" variant="contained" onClick={()=>deleteColDlg&&deleteColumn(deleteColDlg)}>Delete</Button>
        </DialogActions>
      </Dialog>

      {/* Discard Dialog */}
      <Dialog open={discardDlg} onClose={()=>setDiscardDlg(false)} maxWidth="xs" fullWidth>
        <DialogTitle sx={{color:'#D97706',pb:1}}>Discard changes?</DialogTitle>
        <DialogContent>
          <Typography variant="body2">
            All unsaved edits will be lost and the table will revert to the last saved state.
          </Typography>
        </DialogContent>
        <DialogActions sx={{px:2,pb:2}}>
          <Button onClick={()=>setDiscardDlg(false)}>Keep editing</Button>
          <Button color="warning" variant="contained" onClick={handleDiscard}>Discard</Button>
        </DialogActions>
      </Dialog>

      <Snackbar open={!!snack} autoHideDuration={4000} onClose={()=>setSnack(null)}
        anchorOrigin={{vertical:'bottom',horizontal:'right'}}>
        <Alert severity={snack?.sev} onClose={()=>setSnack(null)} variant="filled">{snack?.msg}</Alert>
      </Snackbar>
    </Box>
  )
}
