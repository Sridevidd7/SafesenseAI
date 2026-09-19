import sqlite3
import hashlib
import os

DB_PATH = os.path.join(os.path.dirname(__file__), "safety.db")

def compute_report_hash(description: str, date: str = "", location: str = "") -> str:
    norm_desc = " ".join((description or "").strip().lower().split())
    norm_date = (date or "").strip().lower()
    norm_loc  = (location or "").strip().lower()
    raw = f"{norm_desc}|{norm_date}|{norm_loc}"
    return hashlib.md5(raw.encode("utf-8")).hexdigest()

def run_deduplication():
    print(f"Connecting to database at {DB_PATH}...")
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    cursor.execute("PRAGMA table_info(reports);")
    columns = [col[1] for col in cursor.fetchall()]
    print(f"Existing columns in 'reports': {columns}")

    if "report_hash" not in columns:
        print("Adding column 'report_hash' to 'reports' table...")
        cursor.execute("ALTER TABLE reports ADD COLUMN report_hash TEXT;")
        conn.commit()

    cursor.execute("SELECT id, description FROM reports;")
    rows = cursor.fetchall()
    total_before = len(rows)
    print(f"Total reports before cleanup: {total_before}")

    update_batch = []
    for row_id, description in rows:
        r_hash = compute_report_hash(description)
        update_batch.append((r_hash, row_id))

    cursor.executemany("UPDATE reports SET report_hash = ? WHERE id = ?;", update_batch)
    conn.commit()
    print(f"Backfilled report_hash for {len(update_batch)} rows.")

    cursor.execute("""
        DELETE FROM reports
        WHERE id NOT IN (
            SELECT MIN(id)
            FROM reports
            GROUP BY report_hash
        );
    """)
    conn.commit()

    cursor.execute("SELECT COUNT(*) FROM reports;")
    total_after = cursor.fetchone()[0]
    duplicates_removed = total_before - total_after
    print(f"Duplicates removed: {duplicates_removed}")
    print(f"Total distinct reports remaining: {total_after}")

    cursor.execute("""
        CREATE UNIQUE INDEX IF NOT EXISTS ix_reports_report_hash ON reports(report_hash);
    """)
    conn.commit()
    print("Created UNIQUE INDEX 'ix_reports_report_hash' on reports(report_hash).")

    conn.close()
    print("Deduplication and migration completed successfully.")

if __name__ == "__main__":
    run_deduplication()
