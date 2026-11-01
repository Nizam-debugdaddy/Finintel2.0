"""
Analyst CLI for the financial data platform.

Examples:
  python -m cli.platform_cli init
  python -m cli.platform_cli ingest --file raw/SUN/FY25/standardized_input.xlsx --company SUN
  python -m cli.platform_cli history --company SUN
  python -m cli.platform_cli trend --company SUN --item "Revenue from Operations"
  python -m cli.platform_cli peers --sector Pharma --item "PAT" --year FY25
  python -m cli.platform_cli template --name sector_trend --params sector=Pharma item="EBITDA"
  python -m cli.platform_cli analyze --company SUN
  python -m cli.platform_cli revisions --company SUN
  python -m cli.platform_cli list-templates
"""

from __future__ import annotations
import argparse
import sys
from pathlib import Path

import pandas as pd

# Make src importable when invoked from project root
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from utils import Paths, get_logger
from storage import Warehouse
from ingestion import IngestionPipeline
from retrieval import QueryEngine
from analytics_integration import AnalyticsRunner

logger = get_logger("cli")


# ── Command handlers ────────────────────────────────────────────────

def cmd_init(args, paths: Paths):
    """Seed warehouse master tables from config CSVs."""
    wh = Warehouse(paths)
    seed_cm = paths.config / "company_master_seed.csv"
    seed_sm = paths.config / "sector_mapping_seed.csv"
    if seed_cm.exists():
        df = pd.read_csv(seed_cm)
        wh.upsert_company_master(df)
        print(f"Seeded {len(df)} companies from {seed_cm.name}")
    else:
        print(f"Missing {seed_cm}, skipping company master seed")
    if seed_sm.exists():
        df = pd.read_csv(seed_sm)
        wh.upsert_sector_mapping(df)
        print(f"Seeded {len(df)} sector mappings from {seed_sm.name}")


def cmd_ingest(args, paths: Paths):
    pipe = IngestionPipeline(paths)
    summary = pipe.ingest(
        source_file=args.file,
        company_id=args.company,
        company_name=args.company_name,
        ticker=args.ticker,
    )
    print("Ingestion summary:")
    for k, v in summary.items():
        print(f"  {k}: {v}")


def cmd_history(args, paths: Paths):
    eng = QueryEngine(paths)
    df = eng.get_company_history(args.company, category=args.category)
    print(df.to_string(index=False))


def cmd_trend(args, paths: Paths):
    eng = QueryEngine(paths)
    df = eng.get_item_trend(args.company, args.item, category=args.category)
    print(df.to_string(index=False))


def cmd_peers(args, paths: Paths):
    eng = QueryEngine(paths)
    df = eng.get_peer_compare(args.sector, args.item, args.year)
    print(df.to_string(index=False))


def cmd_template(args, paths: Paths):
    eng = QueryEngine(paths)
    params = {}
    for kv in (args.params or []):
        if "=" not in kv:
            print(f"Bad --params arg '{kv}' (expected key=value)"); return
        k, v = kv.split("=", 1)
        params[k.strip()] = v.strip()
    df = eng.run_template(args.name, params)
    print(df.to_string(index=False))


def cmd_list_templates(args, paths: Paths):
    eng = QueryEngine(paths)
    names = eng.list_templates()
    if not names:
        print("(no templates)")
        return
    print("Available templates:")
    for n in names:
        print(f"  - {n}")


def cmd_revisions(args, paths: Paths):
    eng = QueryEngine(paths)
    df = eng.run_template("revisions", {"company_id": args.company})
    if df.empty:
        print(f"No revisions found for {args.company}")
    else:
        print(df.to_string(index=False))


def cmd_analyze(args, paths: Paths):
    runner = AnalyticsRunner(paths)
    out = runner.run_for_company(args.company)
    print(f"Analytics output: {out}")


def cmd_audit(args, paths: Paths):
    eng = QueryEngine(paths)
    df = eng.get_latest_filings(limit=args.limit)
    print(df.to_string(index=False))


# ── Argparse wiring ─────────────────────────────────────────────────

def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="platform", description="Financial Data Platform CLI")
    p.add_argument("--root", default=".", help="Project root (default: cwd)")
    sub = p.add_subparsers(dest="cmd", required=True)

    sub.add_parser("init", help="Seed company master + sector mapping from config CSVs")

    pi = sub.add_parser("ingest", help="Ingest one source file")
    pi.add_argument("--file", required=True)
    pi.add_argument("--company", required=True, help="company_id (e.g. SUN)")
    pi.add_argument("--company-name", default=None)
    pi.add_argument("--ticker", default=None)

    ph = sub.add_parser("history", help="Show all latest data for one company")
    ph.add_argument("--company", required=True)
    ph.add_argument("--category", default=None)

    pt = sub.add_parser("trend", help="Show trend of one item over years")
    pt.add_argument("--company", required=True)
    pt.add_argument("--item", required=True)
    pt.add_argument("--category", default=None,
                    help="Optional: filter to one category (P&L Consolidated, Altman Z, etc.)")

    pp = sub.add_parser("peers", help="Peer compare in a sector for one item / year")
    pp.add_argument("--sector", required=True)
    pp.add_argument("--item", required=True)
    pp.add_argument("--year", required=True)

    pl = sub.add_parser("template", help="Run a saved query template")
    pl.add_argument("--name", required=True)
    pl.add_argument("--params", nargs="*", help="key=value pairs")

    sub.add_parser("list-templates", help="List available query templates")

    pr = sub.add_parser("revisions", help="Show revision history for a company")
    pr.add_argument("--company", required=True)

    pa = sub.add_parser("analyze", help="Run cost-structure + Altman analytics on a company")
    pa.add_argument("--company", required=True)

    pau = sub.add_parser("audit", help="Show latest ingestion runs")
    pau.add_argument("--limit", type=int, default=20)

    return p


# ── Main ─────────────────────────────────────────────────────────────

def main():
    parser = build_parser()
    args = parser.parse_args()
    paths = Paths(args.root).ensure()

    dispatch = {
        "init":           cmd_init,
        "ingest":         cmd_ingest,
        "history":        cmd_history,
        "trend":          cmd_trend,
        "peers":          cmd_peers,
        "template":       cmd_template,
        "list-templates": cmd_list_templates,
        "revisions":      cmd_revisions,
        "analyze":        cmd_analyze,
        "audit":          cmd_audit,
    }
    dispatch[args.cmd](args, paths)


if __name__ == "__main__":
    main()
