import React, { useState, useEffect, createContext, useContext } from 'react'
import { createTheme, ThemeProvider, CssBaseline } from '@mui/material'
import { BrowserRouter, Routes, Route, Navigate } from 'react-router-dom'
import AppShell from './components/layout/AppShell'
import InputPage from './components/input/InputPage'
import DashboardPage from './components/dashboard/DashboardPage'
import PeerPage from './components/dashboard/PeerPage'
import ExportPage from './components/export/ExportPage'
import { fetchCompanies, Company } from './api/client'

export interface GlobalFilter {
  company: string
  periodType: 'annual' | 'quarterly'
  period: string
  reportType: 'consolidated' | 'standalone'
}

export const FilterContext = createContext<{
  filter: GlobalFilter
  setFilter: (f: Partial<GlobalFilter>) => void
  companies: Company[]
  refreshCompanies: () => void
}>({
  filter: { company: '', periodType: 'annual', period: 'FY25', reportType: 'consolidated' },
  setFilter: () => {},
  companies: [],
  refreshCompanies: () => {},
})

export const useFilter = () => useContext(FilterContext)

// ── Theme context ─────────────────────────────────────────────────────────────
export interface ThemeModeCtx { mode: 'dark' | 'light'; toggleTheme: () => void }
export const ThemeModeContext = createContext<ThemeModeCtx>({ mode: 'dark', toggleTheme: () => {} })
export const useThemeMode = () => useContext(ThemeModeContext)

// ── Dark theme typography (Binance) ──────────────────────────────────────────
const sharedTypography = {
  fontFamily: 'Inter, -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif',
  fontWeightLight:   400,
  fontWeightRegular: 400,
  fontWeightMedium:  500,
  fontWeightBold:    700,
}

// ── Apple typography (SF Pro — light theme only) ──────────────────────────────
const appleTypography = {
  fontFamily: '"SF Pro Text", system-ui, -apple-system, BlinkMacSystemFont, sans-serif',
  fontWeightLight:   300,
  fontWeightRegular: 400,
  fontWeightMedium:  600,
  fontWeightBold:    700,
  h1: { fontFamily: '"SF Pro Display", system-ui, -apple-system, sans-serif', fontWeight: 600, fontSize: '56px', lineHeight: 1.07, letterSpacing: '-0.28px' },
  h2: { fontFamily: '"SF Pro Display", system-ui, -apple-system, sans-serif', fontWeight: 600, fontSize: '40px', lineHeight: 1.10, letterSpacing: 0 },
  h3: { fontFamily: '"SF Pro Display", system-ui, -apple-system, sans-serif', fontWeight: 600, fontSize: '34px', lineHeight: 1.47, letterSpacing: '-0.374px' },
  h4: { fontFamily: '"SF Pro Display", system-ui, -apple-system, sans-serif', fontWeight: 600, fontSize: '28px', lineHeight: 1.14, letterSpacing: '0.196px' },
  h5: { fontFamily: '"SF Pro Display", system-ui, -apple-system, sans-serif', fontWeight: 600, fontSize: '21px', lineHeight: 1.19, letterSpacing: '0.231px' },
  h6: { fontFamily: '"SF Pro Text", system-ui, -apple-system, sans-serif',    fontWeight: 600, fontSize: '17px', lineHeight: 1.24, letterSpacing: '-0.374px' },
  body1:   { fontSize: '17px', lineHeight: 1.47, letterSpacing: '-0.374px' },
  body2:   { fontSize: '14px', lineHeight: 1.43, letterSpacing: '-0.224px' },
  button:  { fontSize: '17px', fontWeight: 400,  lineHeight: 1.0,  letterSpacing: 0 },
  caption: { fontSize: '14px', fontWeight: 400,  lineHeight: 1.43, letterSpacing: '-0.224px' },
  subtitle1: { fontSize: '17px', fontWeight: 600, lineHeight: 1.24, letterSpacing: '-0.374px' },
  subtitle2: { fontSize: '14px', fontWeight: 600, lineHeight: 1.29, letterSpacing: '-0.224px' },
  overline: { fontSize: '12px', fontWeight: 400, lineHeight: 1.0,  letterSpacing: '-0.12px' },
}

// ── Dark theme (Binance) ──────────────────────────────────────────────────────
const darkTheme = createTheme({
  palette: {
    mode: 'dark',
    primary:    { main: '#FCD535', contrastText: '#181a20' },
    secondary:  { main: '#2b3139', contrastText: '#eaecef' },
    background: { default: '#0b0e11', paper: '#1e2329' },
    text: { primary: '#ffffff', secondary: '#b0b8c1' },
    success: { main: '#0ecb81' },
    error:   { main: '#f6465d' },
    divider: '#2b3139',
  },
  typography: sharedTypography,
  components: {
    MuiButton: {
      styleOverrides: {
        root: { textTransform: 'none', fontWeight: 600, borderRadius: 6, transition: 'background-color 0.2s' },
        containedPrimary: { color: '#181a20', '&:hover': { backgroundColor: '#f0b90b' } },
      },
    },
    MuiCard: {
      styleOverrides: {
        root: { borderRadius: 8, boxShadow: 'none', backgroundImage: 'none', border: '1px solid #2b3139', backgroundColor: '#1e2329' },
      },
    },
    MuiPaper: { styleOverrides: { root: { boxShadow: 'none', backgroundImage: 'none' } } },
    MuiOutlinedInput: {
      styleOverrides: {
        root: {
          borderRadius: 6,
          '& .MuiOutlinedInput-notchedOutline': { borderColor: '#2b3139' },
          '&:hover .MuiOutlinedInput-notchedOutline': { borderColor: '#929aa5' },
          '&.Mui-focused .MuiOutlinedInput-notchedOutline': { borderColor: '#FCD535' },
        },
      },
    },
    MuiChip:      { styleOverrides: { root: { borderRadius: 6, fontWeight: 500 } } },
    MuiTableCell: { styleOverrides: { root: { borderBottom: '1px solid #2b3139' } } },
    MuiDivider:   { styleOverrides: { root: { borderColor: '#2b3139' } } },
    MuiMenuItem: {
      styleOverrides: {
        root: {
          '&.Mui-selected': { backgroundColor: 'rgba(252,213,53,0.12)', '&:hover': { backgroundColor: 'rgba(252,213,53,0.18)' } },
          '&:hover': { backgroundColor: '#2b3139' },
        },
      },
    },
    MuiDialog: { styleOverrides: { paper: { backgroundColor: '#1e2329', border: '1px solid #2b3139' } } },
  },
})

// ── Light theme (Apple design system) ────────────────────────────────────────
const lightTheme = createTheme({
  palette: {
    mode: 'light',
    primary:    { main: '#0066cc', contrastText: '#ffffff', dark: '#0071e3' },
    secondary:  { main: '#f5f5f7', contrastText: '#1d1d1f' },
    background: { default: '#f5f5f7', paper: '#ffffff' },
    text: { primary: '#1d1d1f', secondary: '#6e6e73' },
    success: { main: '#1d8348' },
    error:   { main: '#d0021b' },
    warning: { main: '#b7741a' },
    divider: '#e0e0e0',
  },
  typography: appleTypography,
  components: {
    MuiButton: {
      styleOverrides: {
        root: {
          textTransform: 'none',
          fontWeight: 400,
          borderRadius: 9999,
          transition: 'all 0.12s ease',
          boxShadow: 'none',
          '&:active': { transform: 'scale(0.96)' },
          '&:hover': { boxShadow: 'none' },
        },
        containedPrimary: {
          backgroundColor: '#0066cc',
          color: '#ffffff',
          padding: '11px 22px',
          '&:hover': { backgroundColor: '#0071e3', boxShadow: 'none' },
        },
        outlinedPrimary: {
          borderColor: '#0066cc',
          color: '#0066cc',
          '&:hover': { backgroundColor: 'rgba(0,102,204,0.06)' },
        },
      },
    },
    MuiCard: {
      styleOverrides: {
        root: {
          borderRadius: 18,
          boxShadow: 'none',
          backgroundImage: 'none',
          border: '1px solid #e0e0e0',
          backgroundColor: '#ffffff',
        },
      },
    },
    MuiPaper: {
      styleOverrides: {
        root: { backgroundImage: 'none', boxShadow: 'none' },
        elevation1: { boxShadow: 'none', border: '1px solid #e0e0e0' },
        elevation2: { boxShadow: 'none', border: '1px solid #e0e0e0' },
        elevation3: { boxShadow: '0 4px 20px rgba(0,0,0,0.10)' },
      },
    },
    MuiOutlinedInput: {
      styleOverrides: {
        root: {
          borderRadius: 9999,
          backgroundColor: '#ffffff',
          '& .MuiOutlinedInput-notchedOutline': { borderColor: 'rgba(0,0,0,0.12)' },
          '&:hover .MuiOutlinedInput-notchedOutline': { borderColor: '#0066cc' },
          '&.Mui-focused .MuiOutlinedInput-notchedOutline': { borderColor: '#0066cc', borderWidth: 2 },
        },
        input: { padding: '10px 18px', fontSize: '15px', letterSpacing: '-0.224px' },
      },
    },
    MuiChip: {
      styleOverrides: {
        root: { borderRadius: 9999, fontWeight: 400, fontSize: '14px', letterSpacing: '-0.224px' },
        colorPrimary: { backgroundColor: 'rgba(0,102,204,0.10)', color: '#0066cc' },
      },
    },
    MuiTableCell: {
      styleOverrides: {
        root: { borderBottom: '1px solid #e0e0e0', color: '#1d1d1f', fontSize: '14px' },
        head: { color: '#6e6e73', fontWeight: 600, fontSize: '12px', letterSpacing: '-0.12px' },
      },
    },
    MuiDivider:   { styleOverrides: { root: { borderColor: '#e0e0e0' } } },
    MuiMenuItem: {
      styleOverrides: {
        root: {
          fontSize: '15px',
          letterSpacing: '-0.224px',
          '&.Mui-selected': { backgroundColor: 'rgba(0,102,204,0.08)', '&:hover': { backgroundColor: 'rgba(0,102,204,0.12)' } },
          '&:hover': { backgroundColor: '#f5f5f7' },
        },
      },
    },
    MuiDialog: {
      styleOverrides: {
        paper: {
          backgroundColor: '#ffffff',
          border: '1px solid #e0e0e0',
          borderRadius: 18,
          boxShadow: '0 20px 60px rgba(0,0,0,0.18)',
        },
      },
    },
    MuiDrawer: {
      styleOverrides: { paper: { backgroundColor: '#000000', borderRight: 'none' } },
    },
    MuiTab: {
      styleOverrides: {
        root: {
          color: '#6e6e73',
          textTransform: 'none',
          fontSize: '15px',
          letterSpacing: '-0.224px',
          '&.Mui-selected': { color: '#0066cc', fontWeight: 600 },
        },
      },
    },
    MuiTabs: {
      styleOverrides: { indicator: { backgroundColor: '#0066cc', height: 2, borderRadius: 2 } },
    },
    MuiToggleButton: {
      styleOverrides: {
        root: {
          color: '#6e6e73',
          borderColor: '#e0e0e0',
          textTransform: 'none',
          fontSize: '14px',
          letterSpacing: '-0.224px',
          borderRadius: '9999px !important',
          '&.Mui-selected': { backgroundColor: '#0066cc', color: '#ffffff', borderColor: '#0066cc' },
          '&.Mui-selected:hover': { backgroundColor: '#0071e3' },
        },
      },
    },
    MuiTooltip: {
      styleOverrides: {
        tooltip: {
          backgroundColor: '#1d1d1f',
          color: '#ffffff',
          fontSize: '13px',
          borderRadius: 8,
          padding: '6px 12px',
        },
      },
    },
  },
})

// Derive period list from type
export function getPeriods(type: 'annual' | 'quarterly'): string[] {
  const out: string[] = []
  if (type === 'annual') {
    for (let y = 30; y >= 19; y--) out.push(`FY${String(y).padStart(2,'0')}`)
    return out
  }
  for (let y = 30; y >= 19; y--) {
    for (let q = 1; q <= 4; q++) out.push(`Q${q}FY${String(y).padStart(2,'0')}`)
  }
  return out
}

export default function App() {
  const [companies, setCompanies] = useState<Company[]>([])
  const [filter, setFilterState] = useState<GlobalFilter>({
    company: '', periodType: 'annual', period: 'FY25', reportType: 'consolidated',
  })
  const [tick, setTick] = useState(0)
  const [themeMode, setThemeMode] = useState<'dark' | 'light'>(() => {
    return (localStorage.getItem('finintel-theme') as 'dark' | 'light') || 'dark'
  })

  // Apply data-theme attribute for CSS selectors
  useEffect(() => {
    document.documentElement.setAttribute('data-theme', themeMode)
    localStorage.setItem('finintel-theme', themeMode)
  }, [themeMode])

  const toggleTheme = () => setThemeMode(m => m === 'dark' ? 'light' : 'dark')

  useEffect(() => {
    fetchCompanies()
      .then(data => {
        setCompanies(data)
        if (data.length > 0 && !filter.company)
          setFilterState(f => ({ ...f, company: data[0].company_id }))
      })
      .catch(console.error)
  }, [tick])

  const setFilter = (partial: Partial<GlobalFilter>) =>
    setFilterState(f => ({ ...f, ...partial }))

  return (
    <ThemeModeContext.Provider value={{ mode: themeMode, toggleTheme }}>
      <FilterContext.Provider value={{ filter, setFilter, companies, refreshCompanies: () => setTick(t => t+1) }}>
        <ThemeProvider theme={themeMode === 'dark' ? darkTheme : lightTheme}>
          <CssBaseline />
          <BrowserRouter>
            <AppShell>
              <Routes>
                <Route path="/" element={<Navigate to="/input" replace />} />
                <Route path="/input"     element={<InputPage />} />
                <Route path="/dashboard" element={<DashboardPage />} />
                <Route path="/peer"      element={<PeerPage />} />
                <Route path="/export"    element={<ExportPage />} />
              </Routes>
            </AppShell>
          </BrowserRouter>
        </ThemeProvider>
      </FilterContext.Provider>
    </ThemeModeContext.Provider>
  )
}
