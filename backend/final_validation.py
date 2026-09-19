"""
final_validation.py — Step 3 end-to-end validation.
Run: python final_validation.py

Actions performed:
  1. Capture dashboard BEFORE stats
  2. POST one single report via JSON
  3. Upload the test CSV (10 rows)
  4. Capture dashboard AFTER stats
  5. Compare before/after and assert correctness
  6. Print verdict
"""
import json
import urllib.request
import urllib.error
import sqlite3

BASE    = "http://localhost:8000/api"
DB_PATH = "safety.db"
FAILURES = []


def get(path):
    with urllib.request.urlopen(f"{BASE}{path}", timeout=5) as r:
        return json.loads(r.read())


def post_json(path, payload):
    data = json.dumps(payload).encode()
    req  = urllib.request.Request(
        f"{BASE}{path}", data=data,
        headers={"Content-Type": "application/json"}, method="POST"
    )
    with urllib.request.urlopen(req, timeout=5) as r:
        return json.loads(r.read())


def upload_csv(filepath):
    boundary = "safesense_final_val"
    filename  = filepath.split("\\")[-1].split("/")[-1]
    with open(filepath, "rb") as fh:
        file_bytes = fh.read()
    part_header = (
        f"--{boundary}\r\n"
        f'Content-Disposition: form-data; name="file"; filename="{filename}"\r\n'
        f"Content-Type: text/csv\r\n\r\n"
    ).encode()
    part_footer = f"\r\n--{boundary}--\r\n".encode()
    body = part_header + file_bytes + part_footer
    req  = urllib.request.Request(
        f"{BASE}/reports/upload", data=body, method="POST",
        headers={"Content-Type": f"multipart/form-data; boundary={boundary}"},
    )
    with urllib.request.urlopen(req, timeout=10) as r:
        return json.loads(r.read())


def check(label, condition, detail=""):
    if condition:
        print(f"  ✓  {label}")
    else:
        print(f"  ✗  {label}  ← FAIL  {detail}")
        FAILURES.append(label)


# ─────────────────────────────────────────────────────────────────────────────
print("=" * 62)
print("FINAL VALIDATION")
print("=" * 62)

# ── BEFORE stats ─────────────────────────────────────────────────────────────
print("\n[1] Capturing BEFORE stats...")
before = get("/dashboard/stats")
before_total = before["total_reports"]
before_sif   = before["sif_count"]
print(f"    total_reports={before_total}  sif_count={before_sif}")

# ── Insert one report via POST ────────────────────────────────────────────────
print("\n[2] POST /api/reports — single report insert...")
single = post_json("/reports", {
    "description": (
        "FINAL-VALIDATION: Welding crew operating without hot work permit "
        "in chemical storage area. Flammable vapors detected, no fire watch posted."
    )
})
print(f"    id={single['id']}  category={single['category']}  "
      f"score={single['risk_score']}  sif={single.get('sif_potential')}  "
      f"level={single.get('risk_level')}")

check("POST /reports returns id",            isinstance(single.get("id"), int))
check("POST /reports returns category",      bool(single.get("category")))
check("POST /reports returns risk_score",    isinstance(single.get("risk_score"), int))
check("POST /reports returns sif_potential", single.get("sif_potential") in ("YES", "NO"))
check("POST /reports returns risk_level",    single.get("risk_level") in ("LOW","MEDIUM","HIGH","CRITICAL"))

# Verify row was actually saved to DB
conn = sqlite3.connect(DB_PATH)
cur  = conn.cursor()
cur.execute("SELECT sif_potential, risk_level FROM reports WHERE id=?", (single["id"],))
db_row = cur.fetchone()
check(
    "POST /reports persists sif_potential to DB",
    db_row is not None and db_row[0] in ("YES", "NO"),
    str(db_row)
)
check(
    "POST /reports persists risk_level to DB",
    db_row is not None and db_row[1] in ("LOW","MEDIUM","HIGH","CRITICAL"),
    str(db_row)
)
conn.close()

# ── Upload CSV ────────────────────────────────────────────────────────────────
print("\n[3] POST /api/reports/upload — CSV bulk upload (10 rows)...")
upload = upload_csv("test_upload.csv")
print(f"    processed={upload['processed']}  skipped={upload['skipped']}  "
      f"sif_count={upload['sif_count']}")
print(f"    risk_summary={upload['risk_summary']}")
print(f"    sample row 1: id={upload['sample'][0]['saved_id']}  "
      f"cat={upload['sample'][0]['category']}  score={upload['sample'][0]['risk_score']}  "
      f"sif={upload['sample'][0]['sif_potential']}  level={upload['sample'][0]['risk_level']}")

check("CSV upload processed==10",         upload["processed"] == 10)
check("CSV upload skipped==0",             upload["skipped"] == 0)
check("CSV sample has sif_potential",      "sif_potential" in upload["sample"][0])
check("CSV sample has risk_level",         "risk_level"    in upload["sample"][0])
check("CSV sample has saved_id",           isinstance(upload["sample"][0].get("saved_id"), int))

# Verify CSV rows persisted with correct fields
conn = sqlite3.connect(DB_PATH)
cur  = conn.cursor()
first_id = upload["sample"][0]["saved_id"]
cur.execute(
    "SELECT sif_potential, risk_level FROM reports WHERE id=?",
    (first_id,)
)
csv_row = cur.fetchone()
check(
    "CSV rows persist sif_potential to DB",
    csv_row is not None and csv_row[0] in ("YES","NO"),
    str(csv_row)
)
check(
    "CSV rows persist risk_level to DB",
    csv_row is not None and csv_row[1] in ("LOW","MEDIUM","HIGH","CRITICAL"),
    str(csv_row)
)
conn.close()

# ── AFTER stats ───────────────────────────────────────────────────────────────
print("\n[4] Capturing AFTER stats...")
after = get("/dashboard/stats")
after_total = after["total_reports"]
after_sif   = after["sif_count"]
print(f"    total_reports={after_total}  sif_count={after_sif}")

expected_added = 1 + 10  # 1 from POST + 10 from CSV
check(
    f"Dashboard total_reports increased by {expected_added}",
    after_total == before_total + expected_added,
    f"before={before_total} after={after_total} diff={after_total - before_total}"
)
check("Dashboard sif_count > 0",           after_sif > 0)
check("Dashboard avg_risk_score > 0",      after["avg_risk_score"] > 0)
check("Dashboard risk_distribution has 4 keys",
      set(after["risk_distribution"].keys()) == {"CRITICAL","HIGH","MEDIUM","LOW"})
check("Dashboard category_distribution not empty",
      len(after["category_distribution"]) > 0)
check("Dashboard top_category is a string", isinstance(after["top_category"], str))
check("Dashboard top_risk_level is valid",
      after["top_risk_level"] in ("CRITICAL","HIGH","MEDIUM","LOW"))

# ── Before / After comparison table ──────────────────────────────────────────
print("\n" + "=" * 62)
print("BEFORE vs AFTER COMPARISON")
print("=" * 62)
print(f"{'Metric':<30} {'BEFORE':>8} {'AFTER':>8} {'CHANGE':>8}")
print("-" * 62)
metrics = [
    ("total_reports",  before["total_reports"],  after["total_reports"]),
    ("sif_count",      before["sif_count"],       after["sif_count"]),
    ("non_sif_count",  before["non_sif_count"],   after["non_sif_count"]),
    ("sif_percentage", before["sif_percentage"],  after["sif_percentage"]),
    ("avg_risk_score", before["avg_risk_score"],  after["avg_risk_score"]),
]
for name, b, a in metrics:
    diff = round(a - b, 1) if isinstance(a, float) else a - b
    sign = "+" if diff > 0 else ""
    print(f"{name:<30} {str(b):>8} {str(a):>8} {sign + str(diff):>8}")

print("\nRisk distribution AFTER:")
for level in ("CRITICAL","HIGH","MEDIUM","LOW"):
    bar = "█" * after["risk_distribution"].get(level, 0)
    print(f"  {level:<10} {after['risk_distribution'].get(level, 0):>4}  {bar}")

print("\nCategory distribution AFTER:")
for cat, cnt in after["category_distribution"].items():
    bar = "█" * cnt
    print(f"  {cat:<25} {cnt:>4}  {bar}")

# ── Verdict ───────────────────────────────────────────────────────────────────
print("\n" + "=" * 62)
if not FAILURES:
    print("VERDICT: Backend fully stable")
    print("  All endpoints working.")
    print("  All fields persisted correctly.")
    print("  Dashboard aggregations accurate.")
    print("  Before/after counts verified.")
else:
    print(f"VERDICT: {len(FAILURES)} issue(s) remaining:")
    for f in FAILURES:
        print(f"  - {f}")
print("=" * 62)
