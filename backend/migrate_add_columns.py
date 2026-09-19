"""
migrate_add_columns.py
Add sif_potential and risk_level to the reports table, then backfill from risk_score.
Run once: python migrate_add_columns.py
"""
import sqlite3

conn = sqlite3.connect("safety.db")
cur  = conn.cursor()

# Check which columns already exist
cur.execute("PRAGMA table_info(reports)")
existing = {row[1] for row in cur.fetchall()}

if "sif_potential" not in existing:
    cur.execute(
        "ALTER TABLE reports ADD COLUMN sif_potential VARCHAR(3) NOT NULL DEFAULT 'NO'"
    )
    print("Added column: sif_potential")

if "risk_level" not in existing:
    cur.execute(
        "ALTER TABLE reports ADD COLUMN risk_level VARCHAR(10) NOT NULL DEFAULT 'LOW'"
    )
    print("Added column: risk_level")

conn.commit()

# Backfill existing rows using the risk_score already stored
cur.execute("SELECT id, risk_score FROM reports")
rows = cur.fetchall()
updated = 0
for report_id, score in rows:
    sif   = "YES" if score >= 70 else "NO"
    if score > 80:
        level = "CRITICAL"
    elif score > 60:
        level = "HIGH"
    elif score > 30:
        level = "MEDIUM"
    else:
        level = "LOW"
    cur.execute(
        "UPDATE reports SET sif_potential = ?, risk_level = ? WHERE id = ?",
        (sif, level, report_id),
    )
    updated += 1

conn.commit()
print(f"Backfilled {updated} rows")

# Show verification
cur.execute("SELECT id, risk_score, sif_potential, risk_level FROM reports LIMIT 6")
print("\nSample rows after migration:")
for r in cur.fetchall():
    print(f"  id={r[0]}  score={r[1]}  sif={r[2]}  level={r[3]}")

conn.close()
print("\nMigration complete.")
