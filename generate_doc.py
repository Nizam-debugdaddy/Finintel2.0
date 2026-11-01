"""
generate_doc.py — Generates the FinIntel Project Documentation Word document.
Run from the finintel\ root: python generate_doc.py
Output: FinIntel_Project_Documentation.docx
"""

from docx import Document
from docx.shared import Pt, Inches, RGBColor, Cm
from docx.enum.text import WD_ALIGN_PARAGRAPH, WD_LINE_SPACING
from docx.enum.table import WD_TABLE_ALIGNMENT, WD_ALIGN_VERTICAL
from docx.oxml.ns import qn
from docx.oxml import OxmlElement
import datetime, os

# ── Color palette ──────────────────────────────────────────────────────────────
DARK_BLUE   = RGBColor(0x1A, 0x37, 0x6C)   # Navy headings
MID_BLUE    = RGBColor(0x2E, 0x64, 0xA8)   # Sub-headings
ACCENT      = RGBColor(0xD9, 0x77, 0x06)   # Amber accent (matches FinIntel UI)
WHITE       = RGBColor(0xFF, 0xFF, 0xFF)
LIGHT_GREY  = RGBColor(0xF2, 0xF2, 0xF2)
MID_GREY    = RGBColor(0xCC, 0xCC, 0xCC)
DARK_GREY   = RGBColor(0x44, 0x44, 0x44)
TABLE_HEAD  = RGBColor(0x1A, 0x37, 0x6C)
TABLE_ALT   = RGBColor(0xEA, 0xF1, 0xFB)

# ── Helpers ────────────────────────────────────────────────────────────────────
def set_cell_bg(cell, rgb: RGBColor):
    tc   = cell._tc
    tcPr = tc.get_or_add_tcPr()
    shd  = OxmlElement('w:shd')
    hex_color = f'{rgb[0]:02X}{rgb[1]:02X}{rgb[2]:02X}'
    shd.set(qn('w:val'),   'clear')
    shd.set(qn('w:color'), 'auto')
    shd.set(qn('w:fill'),  hex_color)
    tcPr.append(shd)

def set_cell_border(cell, border_color='CCCCCC', size=4):
    tc   = cell._tc
    tcPr = tc.get_or_add_tcPr()
    tcBorders = OxmlElement('w:tcBorders')
    for side in ('top','left','bottom','right'):
        b = OxmlElement(f'w:{side}')
        b.set(qn('w:val'),   'single')
        b.set(qn('w:sz'),    str(size))
        b.set(qn('w:space'), '0')
        b.set(qn('w:color'), border_color)
        tcBorders.append(b)
    tcPr.append(tcBorders)

def add_page_break(doc):
    doc.add_page_break()

def heading1(doc, text, numbered=None):
    p = doc.add_paragraph()
    p.paragraph_format.space_before = Pt(14)
    p.paragraph_format.space_after  = Pt(4)
    if numbered:
        run0 = p.add_run(f'{numbered}.  ')
        run0.font.size  = Pt(16)
        run0.font.bold  = True
        run0.font.color.rgb = ACCENT
    run = p.add_run(text)
    run.font.size  = Pt(16)
    run.font.bold  = True
    run.font.color.rgb = DARK_BLUE
    # Bottom border
    pPr  = p._p.get_or_add_pPr()
    pBdr = OxmlElement('w:pBdr')
    bot  = OxmlElement('w:bottom')
    bot.set(qn('w:val'),   'single')
    bot.set(qn('w:sz'),    '6')
    bot.set(qn('w:space'), '1')
    bot.set(qn('w:color'), '1A376C')
    pBdr.append(bot)
    pPr.append(pBdr)
    return p

def heading2(doc, text):
    p = doc.add_paragraph()
    p.paragraph_format.space_before = Pt(10)
    p.paragraph_format.space_after  = Pt(3)
    run = p.add_run(text)
    run.font.size  = Pt(13)
    run.font.bold  = True
    run.font.color.rgb = MID_BLUE
    return p

def heading3(doc, text):
    p = doc.add_paragraph()
    p.paragraph_format.space_before = Pt(8)
    p.paragraph_format.space_after  = Pt(2)
    run = p.add_run(text)
    run.font.size  = Pt(12)
    run.font.bold  = True
    run.font.color.rgb = DARK_GREY
    return p

def body(doc, text, space_after=Pt(6)):
    p = doc.add_paragraph()
    p.paragraph_format.space_before = Pt(0)
    p.paragraph_format.space_after  = space_after
    p.paragraph_format.line_spacing_rule = WD_LINE_SPACING.ONE_POINT_FIVE
    run = p.add_run(text)
    run.font.size  = Pt(11)
    run.font.color.rgb = DARK_GREY
    return p

def bullet(doc, text, level=0):
    p = doc.add_paragraph(style='List Bullet')
    p.paragraph_format.left_indent  = Inches(0.25 + level * 0.25)
    p.paragraph_format.space_before = Pt(1)
    p.paragraph_format.space_after  = Pt(2)
    run = p.add_run(text)
    run.font.size  = Pt(11)
    run.font.color.rgb = DARK_GREY
    return p

def info_box(doc, label, text):
    """Amber-accent side-label info box."""
    table = doc.add_table(rows=1, cols=2)
    table.style = 'Table Grid'
    table.alignment = WD_TABLE_ALIGNMENT.LEFT
    table.autofit  = False
    w = table.columns[0].width
    table.columns[0].width = Inches(1.4)
    table.columns[1].width = Inches(5.6)
    c0, c1 = table.rows[0].cells
    set_cell_bg(c0, ACCENT)
    set_cell_bg(c1, RGBColor(0xFF, 0xFB, 0xEB))
    p0 = c0.paragraphs[0]
    p0.alignment = WD_ALIGN_PARAGRAPH.CENTER
    r0 = p0.add_run(label)
    r0.font.bold  = True
    r0.font.size  = Pt(10)
    r0.font.color.rgb = WHITE
    p1 = c1.paragraphs[0]
    r1 = p1.add_run(text)
    r1.font.size  = Pt(10.5)
    r1.font.color.rgb = RGBColor(0x78, 0x35, 0x0F)
    doc.add_paragraph().paragraph_format.space_after = Pt(4)

def styled_table(doc, headers, rows, col_widths=None):
    tbl = doc.add_table(rows=1 + len(rows), cols=len(headers))
    tbl.style = 'Table Grid'
    tbl.alignment = WD_TABLE_ALIGNMENT.LEFT

    # Header row
    hdr = tbl.rows[0]
    for i, h in enumerate(headers):
        c = hdr.cells[i]
        set_cell_bg(c, TABLE_HEAD)
        p = c.paragraphs[0]
        p.alignment = WD_ALIGN_PARAGRAPH.CENTER
        r = p.add_run(h)
        r.font.bold  = True
        r.font.size  = Pt(10)
        r.font.color.rgb = WHITE
        if col_widths:
            c.width = Inches(col_widths[i])

    # Data rows
    for ri, row in enumerate(rows):
        tr = tbl.rows[ri + 1]
        bg = TABLE_ALT if ri % 2 == 0 else WHITE
        for ci, cell_text in enumerate(row):
            c = tr.cells[ci]
            set_cell_bg(c, bg)
            p = c.paragraphs[0]
            p.alignment = WD_ALIGN_PARAGRAPH.LEFT
            r = p.add_run(str(cell_text))
            r.font.size  = Pt(10)
            r.font.color.rgb = DARK_GREY
            if col_widths:
                c.width = Inches(col_widths[ci])

    doc.add_paragraph().paragraph_format.space_after = Pt(6)
    return tbl

def code_block(doc, lines):
    for line in lines:
        p = doc.add_paragraph()
        p.paragraph_format.left_indent  = Inches(0.3)
        p.paragraph_format.space_before = Pt(0)
        p.paragraph_format.space_after  = Pt(0)
        run = p.add_run(line)
        run.font.name  = 'Courier New'
        run.font.size  = Pt(9)
        run.font.color.rgb = RGBColor(0x1E, 0x40, 0xAF)
    doc.add_paragraph().paragraph_format.space_after = Pt(6)

# ══════════════════════════════════════════════════════════════════════════════
# BUILD DOCUMENT
# ══════════════════════════════════════════════════════════════════════════════
doc = Document()

# ── Page margins ──────────────────────────────────────────────────────────────
for section in doc.sections:
    section.top_margin    = Cm(2.5)
    section.bottom_margin = Cm(2.5)
    section.left_margin   = Cm(2.8)
    section.right_margin  = Cm(2.8)

# ── Default font ──────────────────────────────────────────────────────────────
style = doc.styles['Normal']
style.font.name = 'Calibri'
style.font.size = Pt(11)

# ══════════════════════════════════════════════════════════════════════════════
# COVER PAGE
# ══════════════════════════════════════════════════════════════════════════════
p = doc.add_paragraph()
p.paragraph_format.space_before = Pt(60)
p.paragraph_format.space_after  = Pt(4)
p.alignment = WD_ALIGN_PARAGRAPH.CENTER
run = p.add_run('FinIntel')
run.font.size  = Pt(48)
run.font.bold  = True
run.font.color.rgb = DARK_BLUE

p2 = doc.add_paragraph()
p2.alignment = WD_ALIGN_PARAGRAPH.CENTER
p2.paragraph_format.space_after = Pt(6)
r2 = p2.add_run('Financial Intelligence & Analytics Platform')
r2.font.size  = Pt(20)
r2.font.bold  = False
r2.font.color.rgb = MID_BLUE

p3 = doc.add_paragraph()
p3.alignment = WD_ALIGN_PARAGRAPH.CENTER
p3.paragraph_format.space_after = Pt(40)
r3 = p3.add_run('Version 2.0')
r3.font.size  = Pt(14)
r3.font.color.rgb = ACCENT

# Divider line via table
sep = doc.add_table(rows=1, cols=1)
sep.style = 'Table Grid'
set_cell_bg(sep.rows[0].cells[0], DARK_BLUE)
sep.rows[0].cells[0].height = Cm(0.15)
sep.rows[0].cells[0].paragraphs[0].add_run('')

doc.add_paragraph().paragraph_format.space_after = Pt(20)

meta_rows = [
    ('Document Type',  'Project Documentation — Technical & Functional'),
    ('Classification', 'Internal / Confidential'),
    ('Prepared For',   'Management & Technical Teams'),
    ('Date',           datetime.date.today().strftime('%B %d, %Y')),
    ('Platform',       'Windows 10 / 11 · Python 3.11 · React 18 · FastAPI'),
]
for lbl, val in meta_rows:
    pm = doc.add_paragraph()
    pm.alignment = WD_ALIGN_PARAGRAPH.CENTER
    pm.paragraph_format.space_after = Pt(4)
    rl = pm.add_run(f'{lbl}:  ')
    rl.font.bold  = True
    rl.font.size  = Pt(11)
    rl.font.color.rgb = DARK_BLUE
    rv = pm.add_run(val)
    rv.font.size  = Pt(11)
    rv.font.color.rgb = DARK_GREY

add_page_break(doc)

# ══════════════════════════════════════════════════════════════════════════════
# TABLE OF CONTENTS (manual)
# ══════════════════════════════════════════════════════════════════════════════
heading1(doc, 'Table of Contents')
toc_items = [
    ('1', 'Executive Summary'),
    ('2', 'Project Context & Background'),
    ('3', 'Objectives'),
    ('4', 'Technical Architecture'),
    ('5', 'Data Architecture & Storage'),
    ('6', 'System Workflow'),
    ('7', 'Folder Structure'),
    ('8', 'Features & Modules'),
    ('9', 'User Manual'),
    ('10', 'Export & Reporting'),
    ('11', 'Peer Comparison Module'),
    ('12', 'Business Impact'),
    ('13', 'Deployment & Setup'),
    ('14', 'Future Roadmap'),
]
for num, title in toc_items:
    p = doc.add_paragraph()
    p.paragraph_format.space_before = Pt(1)
    p.paragraph_format.space_after  = Pt(3)
    run = p.add_run(f'  {num}.   {title}')
    run.font.size  = Pt(11)
    run.font.color.rgb = DARK_GREY

add_page_break(doc)

# ══════════════════════════════════════════════════════════════════════════════
# 1. EXECUTIVE SUMMARY
# ══════════════════════════════════════════════════════════════════════════════
heading1(doc, 'Executive Summary', numbered='1')
body(doc,
    'FinIntel (Financial Intelligence Platform) is an enterprise-grade, browser-based financial '
    'analytics system designed for investment analysts and finance professionals. Built in-house, '
    'it consolidates multi-year financial data entry, automated ratio computation, cost structure '
    'decomposition, bankruptcy risk modelling, and executive reporting into a single integrated platform.')
body(doc,
    'The platform replaces a legacy desktop Python application with a modern web interface — enabling '
    'concurrent multi-user access, interactive dashboards, sector-based peer comparison, and one-click '
    'export to Excel, PowerPoint, and PDF — all without requiring analyst familiarity with code or '
    'database tools.')

info_box(doc, 'KEY STAT',
    'FinIntel v2.0 reduces a typical analyst reporting cycle from 4–6 hours to under 30 minutes, '
    'covering data entry, full analysis computation, peer benchmarking, and professional report generation.')

styled_table(doc,
    ['Metric', 'Detail'],
    [
        ['Platform Type',    'Full-Stack Web Application (Single-Port, Self-Contained)'],
        ['Frontend',         'React 18 + TypeScript + MUI v5 + AG Grid + Plotly.js'],
        ['Backend',          'Python 3.11 + FastAPI + Uvicorn (ASGI)'],
        ['Analytics Engine', 'DuckDB + Apache Parquet (columnar data warehouse)'],
        ['Metadata Store',   'SQLite (companies, staging, audit, notes)'],
        ['Export Formats',   'Microsoft Excel (.xlsx) · PowerPoint (.pptx) · PDF'],
        ['Access',           'Browser — http://localhost:8000 (no internet required)'],
        ['Current Companies','DRL · CIPLA · SUN · AUROBINDO · HETERO · INTAS · ACCORDD · IPCA LABS'],
    ],
    col_widths=[2.0, 5.0]
)

add_page_break(doc)

# ══════════════════════════════════════════════════════════════════════════════
# 2. PROJECT CONTEXT & BACKGROUND
# ══════════════════════════════════════════════════════════════════════════════
heading1(doc, 'Project Context & Background', numbered='2')
body(doc,
    'Financial analysis in investment banking and equity research typically involves manually '
    'building Excel models, running standalone Python scripts, and compiling outputs across '
    'multiple files — a fragmented process that is time-consuming, error-prone, and difficult '
    'to share or audit.')
body(doc,
    'The predecessor to FinIntel was a desktop Python application that automated Cost Structure '
    'and Altman Z-Score computations from Excel input files. While functionally correct, it had '
    'significant operational limitations:')
bullet(doc, 'Single-user desktop tool — no concurrent access or sharing')
bullet(doc, 'Required manual Excel file preparation before each analysis run')
bullet(doc, 'No interactive dashboards or visual drill-down')
bullet(doc, 'No peer comparison across multiple companies')
bullet(doc, 'Outputs were static Excel files with no export customisation')
bullet(doc, 'No audit trail of who changed what and when')

heading2(doc, '2.1  Why FinIntel Was Built')
body(doc,
    'FinIntel was developed to solve these gaps by wrapping the legacy analytical engines '
    '(unchanged, to preserve calculation integrity) inside a modern web application architecture. '
    'The key design principles were:')
bullet(doc, 'Zero disruption to existing calculations — legacy engines remain unmodified')
bullet(doc, 'Browser-based access — no local Python environment required for end users')
bullet(doc, 'Spreadsheet-style data entry — familiar Excel-like AG Grid interface')
bullet(doc, 'Real-time computation — analysis runs in seconds, not minutes')
bullet(doc, 'Audit-complete — every input change, analysis run, and export is logged')

heading2(doc, '2.2  Industry Context — Pharma Sector')
body(doc,
    'The platform is currently deployed for pharmaceutical sector analysis in India, covering '
    'eight listed companies across formulations, API, and specialty verticals. It is structured '
    'for easy extension to other sectors. Key pharma-specific metrics tracked include RM cost as '
    '% of revenue, power and fuel intensity, R&D and export cost dynamics, and finance cost '
    'coverage — all of which feed directly into cost structure benchmarking.')

add_page_break(doc)

# ══════════════════════════════════════════════════════════════════════════════
# 3. OBJECTIVES
# ══════════════════════════════════════════════════════════════════════════════
heading1(doc, 'Objectives', numbered='3')

heading2(doc, '3.1  Primary Objectives')
bullet(doc, 'Provide a centralised browser-based platform for financial data entry and analysis')
bullet(doc, 'Automate Cost Structure decomposition across 10 cost segments as % of revenue')
bullet(doc, 'Compute Altman Z-Score bankruptcy risk with full 5-component decomposition')
bullet(doc, 'Enable multi-year trend analysis (FY19–FY25) for revenue, EBITDA, PAT, and ratios')
bullet(doc, 'Support side-by-side peer comparison across companies within the same sector')
bullet(doc, 'Generate professional client-ready reports in Excel, PowerPoint, and PDF')

heading2(doc, '3.2  Secondary Objectives')
bullet(doc, 'Maintain complete audit trail of all data changes and export events')
bullet(doc, 'Support both Consolidated and Standalone P&L for dual-book reporting')
bullet(doc, 'Enable health-score composite ranking for quick portfolio screening')
bullet(doc, 'Provide auto-generated management insights alongside visual charts')
bullet(doc, 'Reduce analyst reporting cycle time from hours to minutes')

heading2(doc, '3.3  Non-Goals (Current Version)')
bullet(doc, 'No live market data feed or real-time price integration')
bullet(doc, 'No multi-user authentication or role-based access control (planned v3)')
bullet(doc, 'No quarterly period analysis (planned v2 extension)')
bullet(doc, 'No cloud/SaaS deployment (single-machine localhost deployment)')

add_page_break(doc)

# ══════════════════════════════════════════════════════════════════════════════
# 4. TECHNICAL ARCHITECTURE
# ══════════════════════════════════════════════════════════════════════════════
heading1(doc, 'Technical Architecture', numbered='4')
body(doc,
    'FinIntel follows a three-tier architecture: a React single-page application (SPA) frontend, '
    'a FastAPI REST backend, and a dual-store data layer (SQLite for metadata + DuckDB/Parquet '
    'for analytics). All three tiers are served from a single port (8000) in production.')

heading2(doc, '4.1  Architecture Diagram')
code_block(doc, [
    '┌─────────────────────────────────────────────────────────────┐',
    '│                     Browser (localhost:8000)                 │',
    '│   React 18 SPA  ·  MUI v5  ·  AG Grid  ·  Plotly.js        │',
    '└───────────────────────────┬─────────────────────────────────┘',
    '                            │  HTTP / REST (JSON)',
    '┌───────────────────────────▼─────────────────────────────────┐',
    '│              FastAPI  (Uvicorn ASGI · port 8000)            │',
    '│  ┌──────────┐ ┌──────────┐ ┌──────────┐ ┌──────────────┐  │',
    '│  │/company  │ │/financial│ │/dashboard│ │/export       │  │',
    '│  │/calculate│ │-input    │ │/peer     │ │/query        │  │',
    '│  └────┬─────┘ └────┬─────┘ └────┬─────┘ └──────┬───────┘  │',
    '│       └────────────┴────────────┘               │          │',
    '│                    │                             │          │',
    '│          ┌─────────▼──────────┐     ┌───────────▼──────┐  │',
    '│          │  AnalyticsService  │     │  Export Services  │  │',
    '│          │  (Engine Wrapper)  │     │  PPT · PDF · XLSX │  │',
    '│          └─────────┬──────────┘     └──────────────────┘  │',
    '│                    │                                        │',
    '│   ┌────────────────┴─────────────────────┐                │',
    '│   │                Data Layer             │                │',
    '│   │  SQLite (metadata.db)                │                │',
    '│   │  · companies · sectors · staging      │                │',
    '│   │  · versions  · notes  · audit_log     │                │',
    '│   │                                       │                │',
    '│   │  DuckDB + Parquet Warehouse           │                │',
    '│   │  · /warehouse/financials/             │                │',
    '│   │    company_id=X / year=FY## / *.pq    │                │',
    '│   └───────────────────────────────────────┘                │',
    '└─────────────────────────────────────────────────────────────┘',
])

heading2(doc, '4.2  Frontend Stack')
styled_table(doc,
    ['Technology', 'Version', 'Role'],
    [
        ['React',         '18.2',  'UI component framework'],
        ['TypeScript',    '5.3',   'Type-safe JavaScript'],
        ['Material-UI',   '5.15',  'UI component library (buttons, tables, modals)'],
        ['AG Grid',       '31.0',  'Spreadsheet-style data entry grid'],
        ['Plotly.js',     '2.27',  'Interactive charts (bar, gauge, trend)'],
        ['React Router',  '6.21',  'Client-side SPA routing'],
        ['Axios',         '1.6',   'HTTP API client'],
        ['Vite',          '5.0',   'Build tool (fast HMR in dev, optimised bundle in prod)'],
        ['Emotion',       '11.11', 'CSS-in-JS for MUI theming'],
    ],
    col_widths=[1.8, 1.0, 4.2]
)

heading2(doc, '4.3  Backend Stack')
styled_table(doc,
    ['Technology', 'Version', 'Role'],
    [
        ['Python',         '3.11+',  'Runtime language'],
        ['FastAPI',        '0.110+', 'REST API framework with auto OpenAPI docs'],
        ['Uvicorn',        '0.29+',  'ASGI web server (production-grade async)'],
        ['DuckDB',         '0.10+',  'In-process analytics query engine'],
        ['Apache Parquet', '–',      'Columnar file format for warehouse storage'],
        ['PyArrow',        '14.0+',  'Parquet I/O and data interchange'],
        ['Pandas',         '2.0+',   'Data manipulation and transformation'],
        ['SQLite/aiosqlite','0.20+', 'Async metadata and staging store'],
        ['python-pptx',    '0.6.21', 'PowerPoint report generation'],
        ['openpyxl',       '3.1+',   'Excel read / write'],
        ['ReportLab',      '4.0+',   'PDF generation'],
        ['Pydantic',       '2.0+',   'Request/response data validation'],
    ],
    col_widths=[2.0, 1.2, 3.8]
)

add_page_break(doc)

# ══════════════════════════════════════════════════════════════════════════════
# 5. DATA ARCHITECTURE
# ══════════════════════════════════════════════════════════════════════════════
heading1(doc, 'Data Architecture & Storage', numbered='5')

heading2(doc, '5.1  Dual-Store Design')
body(doc,
    'FinIntel uses two complementary databases to separate mutable analyst work from immutable '
    'analytical results:')
bullet(doc, 'SQLite (metadata.db) — fast, transactional store for analyst inputs, company master, '
       'versions, notes, and audit logs. Used during data entry phase (before Analyze is clicked).')
bullet(doc, 'DuckDB + Parquet Warehouse — high-performance columnar store for all processed '
       'financial data. Written once per "Analyze" run; read many times for dashboards and exports.')

heading2(doc, '5.2  SQLite Schema')
styled_table(doc,
    ['Table', 'Key Columns', 'Purpose'],
    [
        ['companies',        'company_id (PK), company_name, ticker, isin, active_flag',    'Company master registry'],
        ['sectors',          'company_id (FK), sector, sub_sector  [UNIQUE per company]',   'Many-to-many sector mapping'],
        ['financial_inputs', 'company_id, period_label, financial_item, category, value',   'Analyst staging (pre-analyze)'],
        ['versions',         'company_id, period_label, version_num, is_active, note',      'Analysis version history'],
        ['analyst_notes',    'company_id, period_label, note, page, created_at',            'Free-text analyst annotations'],
        ['audit_log',        'event_type, company_id, period_label, rows_affected, detail', 'Full change audit trail'],
        ['export_log',       'company_id, format, status, file_path, created_at',           'Export history per company'],
    ],
    col_widths=[1.6, 2.8, 2.6]
)

heading2(doc, '5.3  Parquet Warehouse Layout')
code_block(doc, [
    'backend/warehouse/',
    '├── financials/',
    '│   ├── company_id=DRL/          ← URL-encoded company name',
    '│   │   ├── year=FY20/',
    '│   │   │   └── <ingestion_id>-0.parquet',
    '│   │   ├── year=FY21/',
    '│   │   │   └── <ingestion_id>-0.parquet',
    '│   │   └── year=FY25/',
    '│   ├── company_id=CIPLA/',
    '│   └── ... (one folder per company)',
    '├── company_master.parquet',
    '├── sector_mapping.parquet',
    '└── audit_log.parquet',
])
body(doc,
    'Each Parquet file stores all financial line items for one company-year combination. '
    'DuckDB scans only the relevant partitions (predicate pushdown), making dashboard queries '
    'sub-second even across 10+ companies and 6+ years of data.')

heading2(doc, '5.4  Caching Layer')
styled_table(doc,
    ['Cache', 'TTL', 'Invalidated By'],
    [
        ['Dashboard KPIs',           '120 seconds', 'POST /calculate/all  or  data write'],
        ['Cost Trend (multi-year)',   '90 seconds',  'POST /calculate/all'],
        ['Financial Ratios',         '90 seconds',  'POST /calculate/all'],
        ['DuckDB engine refresh',    '30 seconds',  'Any warehouse write (throttled)'],
    ],
    col_widths=[2.4, 1.6, 3.0]
)

add_page_break(doc)

# ══════════════════════════════════════════════════════════════════════════════
# 6. SYSTEM WORKFLOW
# ══════════════════════════════════════════════════════════════════════════════
heading1(doc, 'System Workflow', numbered='6')

heading2(doc, '6.1  Standard Data-to-Dashboard Workflow')
code_block(doc, [
    'Step 1 ── Select Company',
    '          Analyst opens browser → selects company from dropdown',
    '          System loads workspace (SQLite staging + Parquet warehouse overlay)',
    '',
    'Step 2 ── Enter / Edit Financial Data',
    '          AG Grid spreadsheet populates with existing data',
    '          Analyst edits cells (autosaved to SQLite every 800 ms)',
    '          Supports copy-paste from Excel, 50-step undo/redo',
    '',
    'Step 3 ── Run Analysis (Click "Analyze")',
    '          POST /calculate/all/{company_id}',
    '          ├── Reads all staged rows from SQLite',
    '          ├── Ingests to Parquet warehouse (single batch write)',
    '          ├── Clears DuckDB cache (forces re-read of new data)',
    '          ├── Runs Cost Structure engine (all years in one pass)',
    '          └── Runs Altman Z-Score engine (5-component decomposition)',
    '',
    'Step 4 ── View Dashboard',
    '          GET /dashboard/{company_id}/full  (4 sections in parallel)',
    '          ├── KPI cards (Revenue, EBITDA, PAT, Assets, Altman Z)',
    '          ├── Multi-year trend charts (line + bar)',
    '          ├── Cost structure stacked bar (% of Revenue)',
    '          └── Financial ratios table',
    '',
    'Step 5 ── Export Report',
    '          POST /export/excel  or  /export/ppt  or  /export/pdf',
    '          File downloaded to browser · Entry written to export_log',
])

heading2(doc, '6.2  Peer Comparison Workflow')
code_block(doc, [
    'Step 1 ── Navigate to Peer Comparison page',
    'Step 2 ── Select sector (e.g., "Pharma")',
    'Step 3 ── Choose companies to compare (multi-select checkbox)',
    'Step 4 ── Select period (FY20–FY25)',
    'Step 5 ── View side-by-side Cost Structure chart (% Revenue or % Total Cost)',
    'Step 6 ── Auto-generated insight: best performer, RM range, avg EBITDA',
    'Step 7 ── Switch to Multi-Company Trend Comparison (select metric + year range)',
    'Step 8 ── Export comparison PPT or PNG',
])

heading2(doc, '6.3  Data States')
styled_table(doc,
    ['State', 'Storage', 'When', 'Visible In UI'],
    [
        ['Staged',     'SQLite (financial_inputs)', 'After analyst edits cells',  'Input grid (orange indicator)'],
        ['Warehouse',  'Parquet + DuckDB',          'After clicking "Analyze"',   'Dashboard, Charts, Exports'],
        ['Tombstoned', 'SQLite (NULL value)',        'After analyst deletes a row','Blank cell (hides warehouse value)'],
        ['Inactive',   'Parquet (is_active=False)',  'After invalidate run',       'Excluded from all queries'],
    ],
    col_widths=[1.4, 1.8, 2.0, 1.8]
)

add_page_break(doc)

# ══════════════════════════════════════════════════════════════════════════════
# 7. FOLDER STRUCTURE
# ══════════════════════════════════════════════════════════════════════════════
heading1(doc, 'Folder Structure', numbered='7')

heading2(doc, '7.1  Root Directory')
code_block(doc, [
    'finintel/',
    '├── Launch_FinIntel.bat          ← Double-click to start (production)',
    '├── Build_UI.bat                 ← Rebuild React frontend after code changes',
    '├── Dev_Mode.bat                 ← Start in development mode (hot reload)',
    '├── Stop_FinIntel.bat            ← Stop the running server',
    '├── Rollback_UI.bat              ← Restore previous frontend build',
    '├── docker-compose.yml           ← Docker deployment configuration',
    '├── README.md                    ← Feature overview',
    '├── DEPLOYMENT.md                ← Operational deployment guide',
    '├── finintel_server.log          ← Runtime server log',
    '├── backend/                     ← Python FastAPI application',
    '└── frontend/                    ← React TypeScript application',
])

heading2(doc, '7.2  Backend Structure')
code_block(doc, [
    'backend/',
    '├── app/',
    '│   ├── main.py                  ← FastAPI entry point, router registration, static serving',
    '│   ├── config.py                ← Path constants (warehouse dir, metadata.db location)',
    '│   ├── db/',
    '│   │   └── sqlite_db.py         ← SQLite schema creation + async connection factory',
    '│   ├── models/',
    '│   │   └── schemas.py           ← Pydantic request/response models',
    '│   ├── routers/',
    '│   │   ├── company.py           ← Company CRUD + sector management',
    '│   │   ├── financial_input.py   ← Data entry, workspace, bulk save',
    '│   │   ├── calculate.py         ← Analyze, ingest, invalidate, repair',
    '│   │   ├── dashboard.py         ← KPIs, Altman Z, cost trend, ratios, peer',
    '│   │   ├── export.py            ← Excel, PowerPoint, PDF generation',
    '│   │   ├── peer.py              ← Cost structure peer comparison',
    '│   │   ├── query.py             ← Raw SQL and history endpoints',
    '│   │   ├── version.py           ← Version history per company',
    '│   │   └── notes.py             ← Analyst notes CRUD',
    '│   └── services/',
    '│       ├── analytics_service.py ← Core engine wrapper + DuckDB queries',
    '│       ├── service_factory.py   ← Singleton caching + throttled refresh',
    '│       ├── ppt_service.py       ← Dashboard PowerPoint generation',
    '│       └── chart_builder.py     ← matplotlib PNG chart rendering',
    '├── legacy_engines/              ← Original Python engines (DO NOT MODIFY)',
    '│   ├── cost_structure_analysis.py',
    '│   └── bankruptcy_analysis.py',
    '├── warehouse/                   ← Parquet data warehouse (DO NOT DELETE)',
    '│   └── financials/company_id=X/year=FY##/',
    '├── output/                      ← Generated Excel exports',
    '├── mappings/',
    '│   └── line_item_mapping.json   ← Financial item name aliases',
    '├── metadata.db                  ← SQLite database (auto-created)',
    '└── requirements.txt             ← Python package dependencies',
])

heading2(doc, '7.3  Frontend Structure')
code_block(doc, [
    'frontend/',
    '├── src/',
    '│   ├── App.tsx                  ← Routes, theme context, company selector state',
    '│   ├── api/',
    '│   │   └── client.ts            ← All Axios API calls + TypeScript type definitions',
    '│   └── components/',
    '│       ├── layout/',
    '│       │   └── AppShell.tsx     ← Sidebar navigation, company dropdown, theme toggle',
    '│       ├── input/',
    '│       │   └── InputPage.tsx    ← AG Grid spreadsheet data entry (3 sheets)',
    '│       ├── dashboard/',
    '│       │   ├── DashboardPage.tsx    ← KPIs, Altman Z, cost structure, ratios',
    '│       │   ├── PeerPage.tsx         ← Sector peer comparison + trend analysis',
    '│       │   └── AdvancedAnalytics.tsx← CAGR, rolling avg, anomaly detection',
    '│       ├── export/',
    '│       │   └── ExportPage.tsx   ← Excel/PPT/PDF download UI + export history',
    '│       └── charts/',
    '│           ├── CostStructureChart.tsx  ← SVG stacked bar (% Revenue)',
    '│           ├── PeerRankedBars.tsx      ← Plotly horizontal ranked bar',
    '│           └── PeerYearlyBars.tsx      ← Year-over-year bar comparison',
    '├── dist/                        ← Vite production build output (auto-generated)',
    '├── node_modules/                ← npm packages (auto-installed, 500 MB)',
    '├── package.json                 ← npm dependencies and build scripts',
    '├── vite.config.ts               ← Vite build + dev server proxy configuration',
    '└── tsconfig.json                ← TypeScript compiler configuration',
])

add_page_break(doc)

# ══════════════════════════════════════════════════════════════════════════════
# 8. FEATURES & MODULES
# ══════════════════════════════════════════════════════════════════════════════
heading1(doc, 'Features & Modules', numbered='8')

heading2(doc, '8.1  Data Input Module')
body(doc,
    'The Data Input module provides an Excel-like browser spreadsheet powered by AG Grid '
    'Community Edition. It supports three input categories across a unified grid interface:')
styled_table(doc,
    ['Sheet', 'Items Captured', 'Usage'],
    [
        ['Altman Z-Score',      'Working Capital, Total Assets, Retained Earnings, EBIT, Net Worth, Total Liabilities, Revenue', 'Bankruptcy risk computation'],
        ['P&L Consolidated',    'Revenue, Raw Materials, Consumables, Power & Fuel, Transportation, Manpower, Finance Costs, Depreciation, Other Expenses, EBITDA, PAT', 'Cost structure + profitability (group-level)'],
        ['P&L Standalone',      'Same line items as Consolidated', 'Standalone entity analysis'],
    ],
    col_widths=[1.8, 3.2, 2.0]
)
bullet(doc, 'Autosave: Every 800 ms, changes pushed to SQLite staging automatically')
bullet(doc, 'Undo/Redo: 50-step history within the session')
bullet(doc, 'Excel paste: Ctrl+V from clipboard — multi-cell range supported')
bullet(doc, 'Year range: FY19 through FY25 (7 annual periods per sheet)')
bullet(doc, 'Source indicators: "W" = Warehouse, "S" = Staged, blank = empty')

heading2(doc, '8.2  Dashboard Module')
body(doc,
    'The Dashboard provides a single-screen financial summary for the selected company and period:')
styled_table(doc,
    ['Section', 'Content'],
    [
        ['KPI Cards',           'Revenue (₹Cr), EBITDA (₹Cr + Margin %), PAT (₹Cr + Margin %), Total Assets, Net Worth, Current Ratio, Working Capital, YoY Growth indicators'],
        ['Altman Z-Score',      'Gauge chart with Safe / Grey Zone / Distress bands; 5-component breakdown (X1–X5); trend table across years'],
        ['Trend Charts',        'Multi-year bar chart (Revenue, EBITDA, PAT); YoY growth overlay'],
        ['Cost Structure',      'Stacked bar chart (% of Revenue across 10 cost segments); leader lines for small segments (<5%); N-Year Avg bar'],
        ['Financial Ratios',    'Current Ratio, DSCR, Debt-to-Asset, Interest Coverage, Cash Conversion Cycle, Creditor/Debtor/Inventory Days, ROE'],
        ['Auto-Generated Insight','Single-sentence summary: RM%, PBT%, Revenue CAGR over displayed period'],
    ],
    col_widths=[2.0, 5.0]
)

heading2(doc, '8.3  Cost Structure Analysis')
body(doc,
    'The Cost Structure Analysis is the centrepiece analytical module. It decomposes annual '
    'revenue into 10 cost segments, producing percentage-of-revenue breakdowns that enable '
    'operating efficiency benchmarking across years and peers:')
styled_table(doc,
    ['Cost Segment', 'Definition'],
    [
        ['Raw Material Cost',         'Direct material procurement cost'],
        ['Consumables',               'Indirect materials and packing materials'],
        ['Power & Fuel',              'Energy consumption costs'],
        ['Transportation',            'Inbound and outbound logistics'],
        ['Manpower',                  'Employee benefit expenses'],
        ['Finance Costs',             'Interest and borrowing charges'],
        ['Depreciation & Amortisation','D&A on fixed and intangible assets'],
        ['Remaining Expenses',        'Other operating expenses not categorised above'],
        ['Rest in Other Expenses',    'Residual non-operating costs'],
        ['Operational PBT',           'Revenue minus all above costs = Profit Before Tax proxy'],
    ],
    col_widths=[2.8, 4.2]
)

heading2(doc, '8.4  Altman Z-Score Module')
body(doc,
    'Computes the Altman Z-Score (1968 model) for manufacturing companies, classifying bankruptcy '
    'risk into three zones:')
styled_table(doc,
    ['Zone', 'Z-Score Range', 'Interpretation'],
    [
        ['Safe Zone',     'Z > 2.99',          'Low bankruptcy risk — financially sound'],
        ['Grey Zone',     '1.81 < Z ≤ 2.99',   'Moderate risk — monitor closely'],
        ['Distress Zone', 'Z ≤ 1.81',          'High bankruptcy risk — requires immediate review'],
    ],
    col_widths=[1.8, 1.8, 3.4]
)
body(doc, 'The five sub-metrics (X1–X5) are shown individually, allowing analysts to pinpoint '
     'which dimension (liquidity, leverage, profitability, etc.) is driving the score.')

add_page_break(doc)

# ══════════════════════════════════════════════════════════════════════════════
# 9. USER MANUAL
# ══════════════════════════════════════════════════════════════════════════════
heading1(doc, 'User Manual', numbered='9')

heading2(doc, '9.1  Launching the Platform')
bullet(doc, 'Double-click Launch_FinIntel.bat in the finintel/ folder')
bullet(doc, 'First launch only: Python packages are installed automatically (2–3 minutes)')
bullet(doc, 'Browser opens automatically at http://localhost:8000')
bullet(doc, 'To stop: double-click Stop_FinIntel.bat or close the "FinIntel Server" terminal window')

heading2(doc, '9.2  Adding a New Company')
bullet(doc, 'Click the company dropdown in the top-left sidebar')
bullet(doc, 'Click "Add Company" → enter company name and sector')
bullet(doc, 'Company ID is auto-generated (uppercase). Click Save.')
bullet(doc, 'The company now appears in the dropdown and is ready for data entry')

heading2(doc, '9.3  Entering Financial Data')
bullet(doc, 'Select the company from the dropdown')
bullet(doc, 'Click "Data Input" in the left navigation')
bullet(doc, 'The grid pre-populates with any existing warehouse data')
bullet(doc, 'Select the input sheet tab: Altman Z / P&L Consolidated / P&L Standalone')
bullet(doc, 'Click any cell and type the value (in ₹ Millions unless noted)')
bullet(doc, 'Paste directly from Excel using Ctrl+V for multi-year data')
bullet(doc, 'Data saves automatically — no Save button needed')
bullet(doc, 'Undo mistakes with Ctrl+Z (up to 50 steps)')

heading2(doc, '9.4  Running the Analysis')
bullet(doc, 'After entering data, click the "Analyze" button (top right of Data Input page)')
bullet(doc, 'A progress spinner appears while the engines run (typically 3–8 seconds)')
bullet(doc, 'On completion, the platform auto-navigates to the Dashboard')
bullet(doc, 'All KPIs, charts, and ratios update to reflect the new analysis')

heading2(doc, '9.5  Reading the Dashboard')
body(doc, 'The dashboard is laid out top-to-bottom as follows:')
bullet(doc, 'Top row: KPI cards (Revenue, EBITDA, PAT, Assets, Net Worth, Ratios)')
bullet(doc, 'Second row: Altman Z-Score gauge + 5-component decomposition table')
bullet(doc, 'Third row: Multi-year revenue and profitability trend chart')
bullet(doc, 'Fourth row: Cost Structure stacked bar (select Consolidated or Standalone via toggle)')
bullet(doc, 'Fifth row: Auto-generated insight (RM%, PBT%, Revenue CAGR)')
bullet(doc, 'Sixth row: Financial Ratios table (liquidity, efficiency, solvency)')
body(doc, 'Use the "Years shown" dropdown to control how many FY bars appear in the cost chart (1–6 years).')

heading2(doc, '9.6  Peer Comparison')
bullet(doc, 'Click "Peer Comparison" in the left navigation')
bullet(doc, 'Select a sector (e.g., Pharma) — companies in that sector auto-populate')
bullet(doc, 'Select multiple companies using the checkbox list')
bullet(doc, 'Select the period (FY20–FY25) and click "Load"')
bullet(doc, 'Section 1 shows the Cost Structure side-by-side chart')
bullet(doc, 'Toggle between "% Revenue" and "% Total Cost" for different views')
bullet(doc, 'Section 2 shows ranked bar charts for any financial metric by year')
bullet(doc, 'Select metric from the dropdown (Revenue, EBITDA, Altman Z, etc.)')
bullet(doc, 'Section 3 shows the Altman Z-Score summary table across all companies and years')

heading2(doc, '9.7  Switching Report Type')
body(doc,
    'Every financial view supports Consolidated and Standalone modes. '
    'Use the "Consolidated / Standalone" toggle at the top of the Dashboard or '
    'Cost Structure chart to switch between the two P&L books. '
    'The company dropdown remembers the last-used mode per session.')

add_page_break(doc)

# ══════════════════════════════════════════════════════════════════════════════
# 10. EXPORT & REPORTING
# ══════════════════════════════════════════════════════════════════════════════
heading1(doc, 'Export & Reporting', numbered='10')
body(doc,
    'FinIntel generates three professional export formats directly from the browser. '
    'All exports are logged in the audit trail with timestamp, format, and status.')

heading2(doc, '10.1  Excel Export (.xlsx)')
bullet(doc, 'Contains full financial data, KPI summary, cost structure breakdown, and Altman Z decomposition')
bullet(doc, 'Uses the legacy ExcelWriter engine — output is identical to the original desktop tool')
bullet(doc, 'Formatted with colour-coded headers, percentage formatting, and named sheets')
bullet(doc, 'Accessible via Dashboard → Export button → "Excel"')

heading2(doc, '10.2  PowerPoint Export (.pptx)')
body(doc, 'The PPT export generates a 13.33" × 7.5" widescreen presentation with:')
styled_table(doc,
    ['Slide / Section', 'Content'],
    [
        ['Title',           'Company name, report type (Consolidated/Standalone), period range'],
        ['Insight',         'Auto-generated management commentary sentence'],
        ['Revenue Label',   'Revenue in ₹ Cr above each bar (scaled appropriately)'],
        ['Chart',           'Native stacked column chart (100% scale or dynamic scale for loss years)'],
        ['Leader Lines',    'Arrow + % label for cost segments < 5% of revenue (external to bar)'],
        ['Legend',          '2-row colour-coded segment legend (font 11pt)'],
        ['Footer',          'Data source + confidentiality notice'],
    ],
    col_widths=[2.0, 5.0]
)
bullet(doc, 'Available in Dashboard (single company) and Peer Comparison (multi-company)')
bullet(doc, 'Peer PPT shows all selected companies as separate bars for the selected period')

heading2(doc, '10.3  PDF Export')
bullet(doc, 'Executive summary: KPI table + Altman Z interpretation + cost summary')
bullet(doc, 'Generated with ReportLab — clean, printer-ready format')
bullet(doc, 'Includes company header, date, and period stamp')

add_page_break(doc)

# ══════════════════════════════════════════════════════════════════════════════
# 11. PEER COMPARISON MODULE
# ══════════════════════════════════════════════════════════════════════════════
heading1(doc, 'Peer Comparison Module', numbered='11')
body(doc,
    'The Peer Comparison module enables benchmarking across multiple companies '
    'within the same sector simultaneously, supporting three analytical views:')

heading2(doc, '11.1  Cost Structure Comparison')
body(doc,
    'Displays each selected company as a stacked bar chart for the chosen period. '
    'Segments are colour-coded consistently across all companies. '
    'An "Industry Average" bar is appended automatically as the rightmost bar. '
    'Toggle between "% of Revenue" and "% of Total Cost" for different cost perspectives.')

heading2(doc, '11.2  Multi-Company Trend Comparison')
body(doc,
    'Shows ranked horizontal bar charts — one card per fiscal year — for any selected '
    'financial metric. Companies are sorted by rank (highest value = darkest brown, '
    'lowest = lightest yellow) within each year card. '
    'Companies with no data for a given year are automatically excluded from that year\'s card. '
    'Supported metrics include:')
bullet(doc, 'Financial Size: Revenue from Operations, Total Assets, Net Worth, PAT, EBITDA')
bullet(doc, 'Profitability: EBITDA Margin, PAT Margin, ROE')
bullet(doc, 'Efficiency: Cash Conversion Cycle, Inventory Days, Debtor Days, Creditor Days')
bullet(doc, 'Risk: Altman Z Score, Current Ratio, DSCR, Interest Coverage, Debt-to-Asset Ratio')

heading2(doc, '11.3  Altman Z-Score Summary Table')
body(doc,
    'A cross-company × cross-year matrix showing Altman Z scores for all selected companies '
    'across FY20–FY25. Cells below 1.81 (Distress Zone) are highlighted in red for '
    'immediate visual identification of at-risk companies.')

add_page_break(doc)

# ══════════════════════════════════════════════════════════════════════════════
# 12. BUSINESS IMPACT
# ══════════════════════════════════════════════════════════════════════════════
heading1(doc, 'Business Impact', numbered='12')

heading2(doc, '12.1  Analyst Efficiency')
styled_table(doc,
    ['Task', 'Before FinIntel', 'With FinIntel', 'Time Saving'],
    [
        ['Data Entry',                '60–90 min (manual Excel model)',      '15–20 min (AG Grid paste)',           '~75%'],
        ['Cost Structure Analysis',   '30–45 min (run script, fix errors)',  '3–8 sec (one click)',                 '~99%'],
        ['Peer Comparison Chart',     '60–90 min (multi-file VLOOKUP)',      '< 1 min (select + Load)',             '~98%'],
        ['PowerPoint Deck',           '90–120 min (format charts manually)', '< 1 min (PPT button)',                '~98%'],
        ['Full Report (Excel+PPT)',   '4–6 hours',                           '20–30 minutes',                      '~85%'],
        ['Altman Z-Score Computation','30–45 min (manual formula)',           'Automatic on Analyze',               '~99%'],
    ],
    col_widths=[2.2, 1.8, 1.8, 1.2]
)

heading2(doc, '12.2  Quality & Governance Improvements')
bullet(doc, 'Single source of truth — all analysts work from the same warehouse, eliminating version conflicts')
bullet(doc, 'Audit trail — every cell change, analysis run, and export is timestamped and logged')
bullet(doc, 'Reproducibility — any prior period can be re-run exactly, with version history maintained')
bullet(doc, 'Error reduction — automated computation eliminates manual Excel formula errors')
bullet(doc, 'Standardised outputs — every PPT/Excel follows the same professional template')

heading2(doc, '12.3  Decision Support')
bullet(doc, 'Auto-generated insights surface key findings without manual text writing')
bullet(doc, 'Distress zone highlighting (Altman Z < 1.81) enables rapid credit risk screening')
bullet(doc, 'Health score composite (Growth 25% + Profitability 35% + Bankruptcy Risk 40%) supports portfolio ranking')
bullet(doc, 'Year-over-year cost structure trends reveal operating leverage and procurement efficiency changes')
bullet(doc, 'Peer RM intensity benchmarking identifies outliers in procurement cost management')

heading2(doc, '12.4  Scalability')
body(doc,
    'FinIntel is designed to scale from the current 8-company pharma dataset to 50+ companies '
    'across multiple sectors with no architectural changes. Adding a company requires only '
    'entering its name in the portal — the warehouse partitions are created automatically '
    'on the first Analyze run. Sector groups can be created on-the-fly without any configuration.')

add_page_break(doc)

# ══════════════════════════════════════════════════════════════════════════════
# 13. DEPLOYMENT & SETUP
# ══════════════════════════════════════════════════════════════════════════════
heading1(doc, 'Deployment & Setup', numbered='13')

heading2(doc, '13.1  System Requirements')
styled_table(doc,
    ['Component', 'Minimum', 'Recommended'],
    [
        ['Operating System', 'Windows 10',        'Windows 10 / 11 (64-bit)'],
        ['Python',           '3.10',              '3.11 or 3.12'],
        ['RAM',              '4 GB',              '8 GB'],
        ['Disk Space',       '2 GB',              '5 GB (for warehouse growth)'],
        ['Browser',          'Chrome / Edge',     'Chrome / Edge (latest)'],
        ['Node.js',          'Not required',      '20 LTS (only needed to modify UI code)'],
    ],
    col_widths=[2.0, 2.0, 3.0]
)

heading2(doc, '13.2  First-Time Installation')
bullet(doc, 'Step 1: Install Python 3.11 from python.org — tick "Add Python to PATH"')
bullet(doc, 'Step 2: Copy the finintel/ folder to the target machine')
bullet(doc, 'Step 3: Double-click Launch_FinIntel.bat')
bullet(doc, 'Step 4: Wait 2–3 minutes on first run (pip installs packages automatically)')
bullet(doc, 'Step 5: Browser opens at http://localhost:8000')

heading2(doc, '13.3  Files to Transfer Between Machines')
body(doc, 'Copy the full finintel/ folder, EXCLUDING these regenerable items:')
styled_table(doc,
    ['Exclude', 'Reason'],
    [
        ['frontend/node_modules/', '~500 MB — reinstalled automatically by Launch.bat'],
        ['backend/__pycache__/',   'Python bytecode — auto-regenerated at runtime'],
        ['backend/logs/',          'Runtime logs — machine-specific'],
        ['*.log files',            'Runtime logs'],
    ],
    col_widths=[2.4, 4.6]
)

info_box(doc, 'CRITICAL',
    'Never delete backend/warehouse/ — it contains all processed financial data. '
    'Never delete backend/metadata.db — it contains company master, notes, and audit logs. '
    'frontend/dist/ is the pre-built UI; include it to avoid needing Node.js on the target machine.')

heading2(doc, '13.4  Development Mode')
body(doc,
    'Double-click Dev_Mode.bat to start with hot-reload. The backend runs on port 8000 '
    'and the Vite dev server runs on port 3000 with automatic proxy to the backend. '
    'Code changes to frontend/src/ reflect instantly in the browser without a full rebuild.')

heading2(doc, '13.5  Rebuilding the Frontend')
body(doc,
    'After making code changes to frontend/src/, run Build_UI.bat to regenerate the '
    'production bundle in frontend/dist/. The build takes ~1–2 minutes. '
    'Note: Node.js 18–22 LTS is required; Node 25 is not compatible with the current build configuration.')

add_page_break(doc)

# ══════════════════════════════════════════════════════════════════════════════
# 14. FUTURE ROADMAP
# ══════════════════════════════════════════════════════════════════════════════
heading1(doc, 'Future Roadmap', numbered='14')
styled_table(doc,
    ['Phase', 'Feature', 'Priority', 'Estimated Effort'],
    [
        ['Phase 2', 'Quarterly period support (Q1FY24–Q4FY25)',                 'High',   '2–3 weeks'],
        ['Phase 2', 'Multi-user authentication + role-based access (Admin/Viewer)', 'High', '3–4 weeks'],
        ['Phase 3', 'Dynamic cost sub-split hierarchy editor (user-configurable segments)', 'Medium', '2 weeks'],
        ['Phase 3', 'Additional bankruptcy models (Ohlson O-Score, Zmijewski)',  'Medium', '1–2 weeks'],
        ['Phase 3', 'Automatic due-diligence ratio computation (DRL/DSCR/NWC)', 'Medium', '1 week'],
        ['Phase 4', 'Live market data integration (Yahoo Finance / NSE API)',     'Low',    '4–6 weeks'],
        ['Phase 4', 'Cloud deployment (Docker + Azure / AWS)',                    'Low',    '2–3 weeks'],
        ['Phase 4', 'PDF report with embedded charts (matplotlib rendering)',      'Low',    '1 week'],
        ['Phase 5', 'AI-powered commentary generation (LLM integration)',         'Future', 'TBD'],
        ['Phase 5', 'Scenario modelling (what-if analysis on cost segments)',      'Future', 'TBD'],
    ],
    col_widths=[1.0, 3.2, 1.0, 1.8]
)

body(doc,
    'The platform architecture is designed for incremental extension — new analytics modules '
    'can be added as FastAPI routers without disrupting existing functionality. '
    'The Parquet warehouse schema supports additional financial items and periods '
    'without schema migration.')

# ── Final page: API quick reference ───────────────────────────────────────────
add_page_break(doc)
heading1(doc, 'Appendix — API Quick Reference')
heading2(doc, 'Core Endpoints')
styled_table(doc,
    ['Method', 'Endpoint', 'Purpose'],
    [
        ['GET',  '/company',                         'List all companies'],
        ['POST', '/company',                         'Create company'],
        ['GET',  '/financial-input/workspace/{id}',  'Load data grid (warehouse + staged)'],
        ['POST', '/financial-input/bulk',            'Save grid rows'],
        ['POST', '/calculate/all/{id}',              'Run full analysis'],
        ['GET',  '/dashboard/{id}/full',             'Get all 4 dashboard sections'],
        ['GET',  '/dashboard/{id}/cost-trend',       'Multi-year cost structure data'],
        ['POST', '/peer/cost-structure',             'Peer cost comparison data'],
        ['POST', '/export/cost-structure-ppt',       'Generate cost structure PPT'],
        ['POST', '/export/excel/{id}',               'Download Excel report'],
        ['GET',  '/health',                          'Server health check'],
        ['GET',  '/api/docs',                        'Interactive Swagger API docs'],
    ],
    col_widths=[0.7, 2.9, 3.4]
)

body(doc,
    'Full interactive API documentation is available at http://localhost:8000/api/docs '
    'when the server is running. All endpoints accept and return JSON unless returning '
    'a binary file (Excel, PPT, PDF).')

# ── Footer note ───────────────────────────────────────────────────────────────
doc.add_paragraph()
p_end = doc.add_paragraph()
p_end.alignment = WD_ALIGN_PARAGRAPH.CENTER
p_end.paragraph_format.space_before = Pt(30)
r_end = p_end.add_run(
    f'FinIntel v2.0  ·  Financial Intelligence Platform  ·  '
    f'Document generated {datetime.date.today().strftime("%B %Y")}  ·  Internal & Confidential'
)
r_end.font.size  = Pt(9)
r_end.font.color.rgb = RGBColor(0xAA, 0xAA, 0xAA)

# ── Save ──────────────────────────────────────────────────────────────────────
out_path = os.path.join(os.path.dirname(__file__), 'FinIntel_Project_Documentation.docx')
doc.save(out_path)
print(f'Document saved: {out_path}')
