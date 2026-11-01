"""
delete_company.py — permanently remove ONE company's data (same as the portal's
"Delete Company" button, but run from the command line).

USAGE (run from the backend/ folder, with the server STOPPED):
    python delete_company.py "ACCORDD ORGANICS"

It removes:
  1. the warehouse Parquet partition   (analyzed dashboard data)
  2. the generated Excel output         (if any)
  3. SQLite metadata + staging          (dropdown entry, sectors, versions,
                                         typed input grid, notes, export log)

Stop the server before running, then restart it afterwards so DuckDB re-reads
the warehouse.
"""
import sqlite3, shutil, sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent   # backend/

def main():
    company = (sys.argv[1] if len(sys.argv) > 1
               else input("Company ID to delete (exact, case-sensitive): ").strip())
    if not company:
        print("No company id given — aborting."); return

    confirm = input(f'Permanently delete ALL data for "{company}"? type yes: ').strip().lower()
    if confirm != "yes":
        print("Aborted."); return

    # 1. Warehouse parquet partition (analyzed data)
    part = ROOT / "warehouse" / "financials" / f"company_id={company}"
    if part.exists():
        shutil.rmtree(part)
        print(f"  [warehouse] deleted partition folder: {part}")
    else:
        print(f"  [warehouse] no partition folder for '{company}'")

    # 2. Generated Excel output (optional)
    xlsx = ROOT / "output" / f"Output_Analysis_{company}.xlsx"
    if xlsx.exists():
        xlsx.unlink(); print(f"  [output]    deleted {xlsx.name}")

    # 3. SQLite metadata + staging
    db = ROOT / "metadata.db"
    con = sqlite3.connect(str(db))
    for table in ("financial_inputs", "versions", "sectors",
                  "analyst_notes", "export_log", "companies"):
        try:
            n = con.execute(f"DELETE FROM {table} WHERE company_id=?", (company,)).rowcount
            print(f"  [sqlite]    {table}: deleted {n} row(s)")
        except sqlite3.OperationalError as e:
            print(f"  [sqlite]    {table}: skipped ({e})")
    con.commit(); con.close()

    print(f'\nDone. "{company}" fully removed. Restart the server to refresh.')

if __name__ == "__main__":
    main()
