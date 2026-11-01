# FinIntel — Enterprise Financial Analytics Platform v2.0

Web-based redesign of the Python Financial Analytics Desktop Platform.

## What This Is

A full-stack web application that wraps the existing Cost Structure Analysis and
Altman Z-Score engines in a browser-based interface. Analysts enter data directly
in the browser — no Excel upload required — and get live dashboards, charts, and
exportable reports.

**Existing engines are untouched.** Only the input/output layer changed.

---

## Quick Start (Local)

### Prerequisites
- Python 3.11+
- Node.js 20+

### 1. Backend

```bash
cd backend
pip install -r requirements.txt
PYTHONPATH=src uvicorn app.main:app --reload --port 8000
```

Backend runs at: http://localhost:8000  
API docs (Swagger): http://localhost:8000/docs

### 2. Frontend

```bash
cd frontend
npm install --legacy-peer-deps
npm run dev
```

Frontend runs at: http://localhost:3000

### 3. Or run both at once

```bash
chmod +x start.sh
./start.sh
```

---

## Quick Start (Docker)

```bash
docker compose up --build
```

- Frontend: http://localhost:3000  
- Backend API: http://localhost:8000  
- API Docs: http://localhost:8000/docs

---

## Features

### Data Input (AG Grid)
- Browser-based editable spreadsheet — paste directly from Excel
- Autosave every 800ms after any cell change
- Undo/Redo (50-step history)
- Three input sheets: Altman Z, P&L Consolidated, P&L Standalone
- Row validation and error highlighting
- Click **Analyze** to run all engines and populate dashboard

### Dashboard
- KPI cards: Revenue, EBITDA, PAT, Total Assets, Net Worth, Current Ratio, Working Capital
- Altman Z gauge with Safe/Grey/Distress zones
- Revenue & EBITDA trend chart (Plotly)
- Cost structure pie chart
- PAT trend line

### Peer Comparison
- Compare all companies in a sector on any financial metric
- Sector ranking table (Revenue, EBITDA, PAT, Total Assets)
- Highlighted bar for selected company

### Advanced Analytics
- CAGR calculation over full data range
- 3-period rolling average
- YoY growth table and bar chart
- Anomaly detection (Z-score based, flags outliers >1.5σ)

### Export
- **Excel**: Full Output_Analysis.xlsx with live formulas (uses existing ExcelWriter)
- **PowerPoint**: 5-slide summary (Title, KPIs, Revenue chart, Cost pie, Altman Z)
- **PDF**: Executive summary with KPI table and Altman Z interpretation

### Company Management
- Add new companies via GUI dialog
- Multi-sector assignment (many-to-many)
- Version history per company/period

---

## Architecture

```
browser (React + TypeScript + MUI + AG Grid + Plotly)
    ↕ REST API
FastAPI (Python 3.11)
    ↕ wraps unchanged engines
Cost Structure Engine + Altman Z Engine + ExcelWriter
    ↕ reads/writes
DuckDB + Parquet warehouse (same as desktop)
    +
SQLite (metadata: companies, sectors, input staging, versions, audit)
```

---

## Project Structure

```
finintel/
├── backend/
│   ├── app/
│   │   ├── main.py               FastAPI app factory
│   │   ├── config.py             Path settings
│   │   ├── db/sqlite_db.py       SQLite + auto-seed from Parquet
│   │   ├── routers/              7 route files
│   │   └── services/             analytics, ppt, pdf services
│   ├── legacy_engines/           UNCHANGED from desktop
│   ├── src/                      UNCHANGED from desktop
│   ├── warehouse/                Parquet warehouse (shared with desktop)
│   └── mappings/                 Line-item mappings
├── frontend/
│   └── src/
│       ├── App.tsx               Routes + theme
│       ├── api/client.ts         All API calls + types
│       └── components/
│           ├── layout/AppShell   Sidebar + nav + company selector
│           ├── input/InputPage   AG Grid data entry
│           ├── dashboard/        Dashboard, Peer, Advanced Analytics
│           └── export/           Excel/PPT/PDF export
├── docker-compose.yml
└── start.sh
```

---

## API Endpoints

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | /company | List all companies |
| POST | /company | Add company |
| GET | /company/sectors/list | List sectors |
| GET | /financial-input/template/{id} | Get input template |
| POST | /financial-input/bulk | Bulk save from grid |
| POST | /calculate/{company}/{period} | Run engines |
| POST | /calculate/warehouse/{company} | Run from existing data |
| GET | /dashboard/{company} | Full dashboard JSON |
| GET | /dashboard/peer/{sector}/{item}/{period} | Peer comparison |
| GET | /dashboard/sector/{sector}/ranking | Sector ranking |
| POST | /export/excel/{company} | Download Excel |
| POST | /export/ppt/{company} | Download PowerPoint |
| POST | /export/pdf/{company} | Download PDF |

---

## Migration from Desktop

Existing warehouse data works immediately — no migration needed.

1. Copy `warehouse/` folder into `backend/warehouse/`
2. Copy `legacy_engines/` into `backend/legacy_engines/`
3. Copy `mappings/` into `backend/mappings/`
4. Start the platform — SQLite auto-seeds from Parquet on first run

---

## Adding a New Company

**Via GUI:** Click `+ Add Company` in the sidebar → fill form → submit.

**Via API:**
```bash
curl -X POST http://localhost:8000/company \
  -H "Content-Type: application/json" \
  -d '{"company_id":"CIPLA","company_name":"Cipla Ltd","ticker":"CIPLA.NS","sector":"Pharma"}'
```

---

## Next Phases

- **Phase 2**: Quarterly period support (Q1FY25, Q2FY25...)
- **Phase 3**: Dynamic cost sub-split hierarchy editor
- **Phase 4**: Additional bankruptcy models (Ohlson O-Score)
- **Phase 5**: Authentication + multi-user support
