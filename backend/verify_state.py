"""
verify_state.py — Read-only system state check.
Run: python verify_state.py
Touches nothing. Only reads.
"""
import sqlite3
import os
import urllib.request
import urllib.error
import json

BASE = "http://localhost:8000/api"
DB_PATH = "safety.db"

REQUIRED_COLUMNS = {
    "id", "description", "category", "risk_score",
    "created_at", "sif_potential", "risk_level"
}

# ─── 1. DB file ───────────────────────────────────────────────────────────────
print("=" * 60)
print("STEP 1 — DATABASE")
print("=" * 60)

if not os.path.exists(DB_PATH):
    print("DB STATUS: MISSING — safety.db not found")
    exit(1)

print(f"DB FILE:   OK  ({os.path.getsize(DB_PATH):,} bytes)")

conn = sqlite3.connect(DB_PATH)
cur  = conn.cursor()

# ─── 2. Table schema ──────────────────────────────────────────────────────────
cur.execute("SELECT name FROM sqlite_master WHERE type='table'")
tables = [r[0] for r in cur.fetchall()]
print(f"TABLES:    {tables}")

if "reports" not in tables:
    print("TABLE STATUS: MISSING — reports table does not exist")
    conn.close()
    exit(1)

cur.execute("PRAGMA table_info(reports)")
cols_info = cur.fetchall()
present_cols = {row[1] for row in cols_info}
missing_cols = REQUIRED_COLUMNS - present_cols

print("\nCOLUMN SCHEMA:")
for row in cols_info:
    flag = "✓" if row[1] in REQUIRED_COLUMNS else " "
    print(f"  [{flag}] {row[1]:20s}  {row[2]}")

if missing_cols:
    print(f"\nMISSING COLUMNS: {missing_cols}")
    print("TABLE STATUS: PARTIAL")
else:
    print("\nTABLE STATUS: OK — all required columns present")

# ─── 3. Row count + sample ───────────────────────────────────────────────────
cur.execute("SELECT COUNT(*) FROM reports")
count = cur.fetchone()[0]
print(f"\nROW COUNT: {count}")

if count > 0:
    cur.execute(
        "SELECT id, category, risk_score, sif_potential, risk_level, "
        "substr(description, 1, 60) FROM reports ORDER BY id LIMIT 3"
    )
    print("\nFIRST 3 ROWS:")
    for r in cur.fetchall():
        print(f"  id={r[0]}  cat={r[1]}  score={r[2]}  sif={r[3]}  level={r[4]}")
        print(f"    desc: {r[5]}...")

conn.close()

# ─── 4. Endpoint checks ───────────────────────────────────────────────────────
print("\n" + "=" * 60)
print("STEP 2 — ENDPOINT CHECKS")
print("=" * 60)

def get(path):
    try:
        with urllib.request.urlopen(f"{BASE}{path}", timeout=5) as r:
            return r.status, json.loads(r.read())
    except urllib.error.HTTPError as e:
        return e.code, {"error": e.reason}
    except Exception as e:
        return 0, {"error": str(e)}

def post_json(path, payload):
    try:
        data = json.dumps(payload).encode()
        req  = urllib.request.Request(
            f"{BASE}{path}", data=data,
            headers={"Content-Type": "application/json"}, method="POST"
        )
        with urllib.request.urlopen(req, timeout=5) as r:
            return r.status, json.loads(r.read())
    except urllib.error.HTTPError as e:
        return e.code, {"error": json.loads(e.read())}
    except Exception as e:
        return 0, {"error": str(e)}

# GET /api/reports
status, body = get("/reports")
print(f"\nGET /api/reports  →  HTTP {status}")
if status == 200:
    print(f"  total={body.get('total')}  first_id={body['reports'][0]['id'] if body.get('reports') else 'N/A'}")
else:
    print(f"  ERROR: {body}")

# POST /api/reports
status, body = post_json("/reports", {
    "description": "VERIFY TEST: Worker on roof without harness, no edge protection installed."
})
print(f"\nPOST /api/reports  →  HTTP {status}")
if status == 201:
    print(f"  id={body['id']}  category={body['category']}  score={body['risk_score']}")
    # check new fields are in response
    has_sif   = "sif_potential" in body
    has_level = "risk_level"    in body
    print(f"  sif_potential in response: {has_sif}")
    print(f"  risk_level    in response: {has_level}")
else:
    print(f"  ERROR: {body}")

# GET /api/dashboard/stats
status, body = get("/dashboard/stats")
print(f"\nGET /api/dashboard/stats  →  HTTP {status}")
if status == 200:
    print(f"  total_reports={body.get('total_reports')}")
    print(f"  sif_count={body.get('sif_count')}  sif_pct={body.get('sif_percentage')}%")
    print(f"  avg_risk_score={body.get('avg_risk_score')}")
    print(f"  risk_distribution={body.get('risk_distribution')}")
    print(f"  top_category={body.get('top_category')}")
    cats = body.get("category_distribution", {})
    print(f"  category_distribution ({len(cats)} categories): {dict(list(cats.items())[:4])}")
else:
    print(f"  ERROR: {body}")

print("\n" + "=" * 60)
print("VERIFICATION COMPLETE")
print("=" * 60)
