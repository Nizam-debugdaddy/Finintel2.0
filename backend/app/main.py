"""
FinIntel Web Platform — FastAPI main application.

Production mode: FastAPI serves the built React frontend from frontend/dist.
Single port (8000) — no separate Node dev server needed.

Dev mode: Run with FININTEL_DEV=1 to skip static file serving and use
the Vite dev server on port 3000 alongside.
"""
import os
from pathlib import Path
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from contextlib import asynccontextmanager

from app.config import settings
from app.db.sqlite_db import init_db
from app.routers import (
    company, financial_input, calculate,
    dashboard, export, query, version, notes, peer
)

# Resolve frontend/dist relative to this file's location
# backend/app/main.py -> backend/ -> finintel/ -> frontend/dist
_BACKEND_DIR  = Path(__file__).resolve().parent.parent   # backend/
_PROJECT_ROOT = _BACKEND_DIR.parent                       # finintel/
_DIST_DIR     = _PROJECT_ROOT / "frontend" / "dist"

DEV_MODE = os.environ.get("FININTEL_DEV", "").strip() == "1"


@asynccontextmanager
async def lifespan(app: FastAPI):
    await init_db()
    yield


app = FastAPI(
    title="FinIntel Financial Analytics Platform",
    version="2.0.0",
    description="Web-based financial analytics: Cost Structure + Altman Z-Score",
    lifespan=lifespan,
    # In production the React SPA handles its own routing — hide /docs if desired
    docs_url="/api/docs",
    redoc_url="/api/redoc",
    openapi_url="/api/openapi.json",
)

# CORS: frontend (Vercel) and backend (Railway) are on different origins,
# so this is load-bearing in production — configured via ALLOWED_ORIGINS.
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.ALLOWED_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ── API routes ────────────────────────────────────────────────────────────────
app.include_router(company.router,         prefix="/company",         tags=["Company"])
app.include_router(financial_input.router, prefix="/financial-input", tags=["Financial Input"])
app.include_router(calculate.router,       prefix="/calculate",        tags=["Calculate"])
app.include_router(dashboard.router,       prefix="/dashboard",        tags=["Dashboard"])
app.include_router(export.router,          prefix="/export",           tags=["Export"])
app.include_router(query.router,           prefix="/query",            tags=["Query"])
app.include_router(version.router,         prefix="/version",          tags=["Version"])
app.include_router(notes.router,           prefix="/notes",            tags=["Notes"])
app.include_router(peer.router,             prefix="/peer",             tags=["Peer"])


@app.get("/health")
def health():
    return {"status": "ok", "platform": "FinIntel v2.0",
            "mode": "dev" if DEV_MODE else "production",
            "dist_exists": _DIST_DIR.exists()}


# ── Static frontend (production only) ────────────────────────────────────────
# Mount Vite's built assets AFTER all API routes so /company, /dashboard etc.
# are never intercepted by the static file handler.
# The catch-all route below returns index.html for every non-API path so that
# React Router can handle /dashboard, /input, /peer, /export client-side.

if not DEV_MODE:
    if _DIST_DIR.exists():
        # Serve Vite build assets (JS, CSS, images) from /assets/*
        app.mount(
            "/assets",
            StaticFiles(directory=str(_DIST_DIR / "assets")),
            name="assets",
        )

        # All API prefixes — these must NOT be caught by the SPA fallback.
        # /peer/* is both a React route (/peer = Peer Comparison page) AND an API prefix
        # (/peer/cost-structure, /peer/multi-metric). The trick: API paths always have
        # a second segment (e.g. /peer/cost-structure) while the React page is just /peer.
        # Prefixes that are ONLY an API namespace (no React page) — always 404 here.
        _API_ONLY = {
            "company", "financial-input", "calculate",
            "query", "version", "notes", "health", "api",
        }
        # Prefixes that are BOTH a React page (at the bare path) AND an API namespace
        # (at sub-paths): /dashboard, /export, /peer. The bare path MUST serve index.html
        # so the SPA route — and a hard-refresh while sitting on it — works. Only a
        # sub-path that reached this fallback (i.e. didn't match a real API route) is a
        # genuine 404. Real API routes are matched by their routers BEFORE this fallback.
        _DUAL_ROUTE = {"dashboard", "export", "peer"}

        @app.get("/{full_path:path}", include_in_schema=False)
        async def spa_fallback(full_path: str, request: Request):
            """
            Catch-all: serve index.html for React Router paths.
            Excludes:
              - All main API prefixes (company, dashboard, etc.)
              - /peer/cost-structure, /peer/multi-metric, /peer/export/*
              - Static asset files (contain a dot in the last segment)
            """
            from fastapi import HTTPException
            segments = full_path.strip("/").split("/")
            first = segments[0] if segments else ""
            second = segments[1] if len(segments) > 1 else ""

            # API-only prefix → genuine 404 (never serve the SPA to an API client)
            if first in _API_ONLY:
                raise HTTPException(404, f"API endpoint not found: /{full_path}")

            # Dual prefix WITH a sub-path → an API call that matched no route → 404.
            # Bare /dashboard, /export, /peer fall through and serve index.html, so the
            # React routes (and hard-refresh on them) work.
            if first in _DUAL_ROUTE and second:
                raise HTTPException(404, f"API endpoint not found: /{full_path}")

            # Static files with extensions → 404 (they should be in /assets/)
            if "." in segments[-1]:
                raise HTTPException(404, f"Static asset not found: /{full_path}")

            # Everything else → React Router (index.html).
            # index.html must NEVER be cached by the browser: it points at the
            # content-hashed JS bundle (index-<hash>.js), so a stale cached index.html
            # keeps loading an OLD bundle — the recurring "I don't see my changes" bug.
            # no-store forces the browser to re-fetch index.html every load, which then
            # pulls the current bundle. The hashed /assets/* files stay fully cacheable.
            return FileResponse(
                str(_DIST_DIR / "index.html"),
                headers={
                    "Cache-Control": "no-store, no-cache, must-revalidate, max-age=0",
                    "Pragma":        "no-cache",
                    "Expires":       "0",
                },
            )
    else:
        @app.get("/{full_path:path}", include_in_schema=False)
        async def no_dist(full_path: str):
            from fastapi.responses import HTMLResponse
            return HTMLResponse(
                """<!DOCTYPE html><html><body style="font-family:Arial;padding:40px;color:#0B2545">
                <h2>⚠ Frontend not built yet</h2>
                <p>Run <strong>Build_UI.bat</strong> (or <code>npm run build</code> inside
                <code>frontend/</code>) then restart the server.</p>
                <p>API is live at <a href="/api/docs">/api/docs</a></p>
                </body></html>""",
                status_code=503,
            )
