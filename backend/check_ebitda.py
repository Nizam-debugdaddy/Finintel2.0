import duckdb, pathlib
wh = str(pathlib.Path('warehouse/financials').resolve()).replace('\\','/')
con = duckdb.connect()
con.execute(f"CREATE VIEW fin AS SELECT * FROM read_parquet('{wh}/**/*.parquet', hive_partitioning=true)")
rows = con.execute("""
SELECT company_id, year, financial_item, financial_category, value
FROM fin
WHERE company_id='CIPLA' AND year='FY25'
  AND financial_item IN ('EBITDA','Revenue from Operations')
  AND is_active=true
ORDER BY financial_item, financial_category
""").fetchall()
print("=== CIPLA FY25 EBITDA & Revenue ===")
for r in rows: print(r)

# Also check DRL
rows2 = con.execute("""
SELECT company_id, year, financial_item, financial_category, value
FROM fin
WHERE company_id='DRL' AND year='FY25'
  AND financial_item IN ('EBITDA','Revenue from Operations')
  AND is_active=true
ORDER BY financial_item, financial_category
""").fetchall()
print("\n=== DRL FY25 EBITDA & Revenue ===")
for r in rows2: print(r)
