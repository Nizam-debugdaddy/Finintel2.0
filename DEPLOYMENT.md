# FinIntel — Deployment Guide

## Quick Start (Production)

**One-time setup → then just double-click to launch every day.**

### Step 1 — Prerequisites (install once)

| Tool | Download | Why |
|---|---|---|
| Python 3.11+ | https://python.org | Runs the backend |
| Node.js 20+ | https://nodejs.org | Builds the frontend (one-time) |

During Python install: **check "Add Python to PATH"**.

### Step 2 — First launch

Double-click `Launch_FinIntel.bat`

It will automatically:
1. Verify Python is installed
2. Install Python packages if missing (`pip install -r requirements.txt`)
3. Build the React frontend if `frontend/dist` is missing (takes ~2 minutes first time)
4. Start the server on `http://localhost:8000`
5. Open your browser

**Every subsequent launch:** double-click `Launch_FinIntel.bat` — completes in ~5 seconds.

---

## Files Reference

| File | Purpose |
|---|---|
| `Launch_FinIntel.bat` | Start the platform (double-click daily) |
| `Stop_FinIntel.bat` | Stop the server |
| `Build_UI.bat` | Rebuild frontend after editing `frontend/src/` |
| `Rollback_UI.bat` | Restore previous frontend if a build breaks things |
| `Dev_Mode.bat` | Start both servers with hot reload (for developers) |

---

## Architecture in Production Mode

```
User opens browser → localhost:8000
       │
       ▼
FastAPI (uvicorn) on port 8000
       │
       ├── /company, /dashboard, /calculate ...  → Python API handlers
       │
       ├── /assets/*                              → Vite-built JS/CSS (StaticFiles)
       │
       └── / /input /dashboard /peer /export ...  → index.html (React Router)
```

No separate frontend port. Everything on **:8000**.

---

## Updating the UI

When you edit any file in `frontend/src/`:

```
1. Edit frontend/src/components/...
2. Double-click Build_UI.bat          ← rebuilds in ~60 seconds
3. Double-click Launch_FinIntel.bat   ← (or restart if already running)
4. Hard refresh browser: Ctrl+Shift+R
```

`Build_UI.bat` automatically backs up the old build before replacing it.
If the new build has errors it restores the old build automatically.

---

## Folder Structure

```
finintel/
├── Launch_FinIntel.bat      ← DOUBLE-CLICK TO START
├── Stop_FinIntel.bat
├── Build_UI.bat
├── Rollback_UI.bat
├── Dev_Mode.bat
├── DEPLOYMENT.md            ← this file
│
├── backend/
│   ├── app/                 ← FastAPI application
│   │   └── main.py          ← serves frontend + API
│   ├── src/                 ← warehouse engine (DO NOT MODIFY)
│   ├── warehouse/           ← Parquet data files (DO NOT DELETE)
│   ├── legacy_engines/      ← Cost Structure + Altman Z engines
│   ├── mappings/
│   ├── output/              ← Excel/PDF exports saved here
│   └── requirements.txt
│
├── frontend/
│   ├── src/                 ← React source (edit here)
│   ├── dist/                ← Built output (served by FastAPI) — auto-generated
│   ├── node_modules/        ← npm packages — auto-generated
│   └── package.json
│
└── frontend_dist_backup/    ← Previous build (created by Build_UI.bat)
```

---

## Data Safety

**Never delete these folders:**

| Folder | Contains |
|---|---|
| `backend/warehouse/` | Parquet financial data — all your company data |
| `backend/output/` | Generated Excel, PDF exports |
| `backend/metadata.db` | Company list, versions, audit log |

The `frontend/dist/` and `frontend/node_modules/` folders are **fully regenerable** — deleting them is safe, `Build_UI.bat` recreates them.

---

## Ports

| Port | Service | Notes |
|---|---|---|
| 8000 | FinIntel (prod) | Backend + Frontend on same port |
| 3000 | Vite dev server | Dev Mode only — not used in production |

If port 8000 is occupied by another application:
1. Open `Launch_FinIntel.bat` in Notepad
2. Change `set "PORT=8000"` to `set "PORT=8001"`
3. Open `backend/app/main.py` — no change needed (port is set at launch time)

---

## Rollback Plan

| Scenario | Fix |
|---|---|
| UI broken after `Build_UI.bat` | Run `Rollback_UI.bat` → restores previous working build |
| Backend crashes on startup | Check `finintel_server.log` in root folder |
| Port 8000 in use | Run `Stop_FinIntel.bat` then re-launch |
| Python packages missing | `cd backend && pip install -r requirements.txt` |
| Node packages missing | `cd frontend && npm install --legacy-peer-deps` |
| `frontend/dist` missing | Run `Build_UI.bat` |

---

## Dev Mode (for developers)

Run `Dev_Mode.bat` to start with hot reload:
- Backend on `:8000` with `--reload` (auto-restarts on Python file changes)
- Frontend on `:3000` with Vite HMR (instant browser update on save)
- Open `http://localhost:3000` (not 8000 — Vite proxies API calls)

---

## Startup Log

The server writes logs to `finintel_server.log` in the root folder.
Open it in Notepad if something doesn't work.

---

## Creating a Desktop Shortcut (optional)

1. Right-click `Launch_FinIntel.bat` → Create shortcut
2. Move shortcut to Desktop
3. Right-click shortcut → Properties → Change Icon → browse to a `.ico` file
4. Double-click shortcut to launch

