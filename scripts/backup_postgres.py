#!/usr/bin/env python3
"""
scripts/backup_postgres.py — Production PostgreSQL backup & restore utility (Phase 7).

Provides automated, verified logical backups of the SafeSense AI PostgreSQL database:
- Extracts relational and vector tables into a compressed, timestamped JSON archive.
- Generates a SHA-256 checksum file to ensure backup integrity.
- Provides restore functionality with safety checks and dry-run verification.

Usage:
    # 1. Create a backup
    python scripts/backup_postgres.py --backup [--output-dir DIR]

    # 2. Verify a backup archive without writing
    python scripts/backup_postgres.py --verify-archive BACKUP_FILE

    # 3. Restore from a backup archive (requires explicit target confirmation)
    python scripts/backup_postgres.py --restore BACKUP_FILE --target-url postgresql://...
"""
from __future__ import annotations

import argparse
import gzip
import hashlib
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List

TABLE_ORDER = [
    "alembic_version",
    "uploaded_files",
    "reports",
    "actions",
    "reviews",
    "report_embeddings",
]


def _sha256_file(filepath: Path) -> str:
    """Compute SHA-256 hash of a file."""
    h = hashlib.sha256()
    with open(filepath, "rb") as f:
        while chunk := f.read(65536):
            h.update(chunk)
    return h.hexdigest()


def create_backup(db_url: str, output_dir: Path) -> Path:
    """Create a compressed logical backup of all SafeSense tables."""
    import psycopg

    output_dir.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%SZ")
    archive_path = output_dir / f"safesense_backup_{timestamp}.json.gz"
    checksum_path = output_dir / f"safesense_backup_{timestamp}.sha256"

    print(f"[*] Connecting to database to extract backup...")
    data: Dict[str, Any] = {
        "metadata": {
            "timestamp": timestamp,
            "format_version": "1.0",
            "source_type": "postgresql",
            "tables": TABLE_ORDER,
        },
        "tables": {},
    }

    with psycopg.connect(db_url) as conn:
        with conn.cursor() as cur:
            for tbl in TABLE_ORDER:
                try:
                    cur.execute(f"SELECT * FROM {tbl};")
                    cols = [desc[0] for desc in cur.description]
                    rows = cur.fetchall()
                    serialized_rows = []
                    for r in rows:
                        serialized_row = {}
                        for col, val in zip(cols, r):
                            # Convert datetime or non-serializable objects to ISO strings
                            if hasattr(val, "isoformat"):
                                serialized_row[col] = val.isoformat()
                            elif isinstance(val, (bytes, bytearray)):
                                serialized_row[col] = val.hex()
                            else:
                                serialized_row[col] = val
                        serialized_rows.append(serialized_row)
                    data["tables"][tbl] = serialized_rows
                    print(f"    - Table '{tbl}': {len(serialized_rows)} rows backed up.")
                except Exception as exc:
                    print(f"    - Note: Table '{tbl}' query failed: {exc}")
                    data["tables"][tbl] = []

    # Write compressed gzip json
    print(f"[*] Writing compressed archive to {archive_path}...")
    json_bytes = json.dumps(data, indent=2).encode("utf-8")
    with gzip.open(archive_path, "wb") as f_out:
        f_out.write(json_bytes)

    # Write checksum file
    sha256_hash = _sha256_file(archive_path)
    checksum_path.write_text(f"{sha256_hash}  {archive_path.name}\n", encoding="utf-8")

    print(f"[OK] Backup complete! SHA-256: {sha256_hash}")
    print(f"    Archive:  {archive_path}")
    print(f"    Checksum: {checksum_path}")
    return archive_path


def verify_archive(archive_path: Path) -> Dict[str, Any]:
    """Verify archive integrity and return metadata."""
    if not archive_path.exists():
        raise FileNotFoundError(f"Archive not found: {archive_path}")

    # Check companion checksum if exists
    checksum_file = archive_path.parent / (archive_path.name.replace(".json.gz", ".sha256"))
    if not checksum_file.exists():
        checksum_file = archive_path.with_suffix(".sha256")

    if checksum_file.exists():
        expected_hash = checksum_file.read_text(encoding="utf-8").split()[0].strip()
        computed_hash = _sha256_file(archive_path)
        if expected_hash.lower() != computed_hash.lower():
            raise ValueError(f"Checksum mismatch! Expected {expected_hash}, computed {computed_hash}")
        print(f"[OK] SHA-256 checksum verified: {computed_hash}")
    else:
        print("[!] Warning: Companion .sha256 file not found, skipping hash check.")

    with gzip.open(archive_path, "rb") as f_in:
        data = json.loads(f_in.read().decode("utf-8"))

    meta = data.get("metadata", {})
    tables = data.get("tables", {})
    print(f"[*] Backup metadata: created={meta.get('timestamp')} format={meta.get('format_version')}")
    for tbl, rows in tables.items():
        print(f"    - Table '{tbl}': {len(rows)} rows")

    return data


def restore_backup(archive_path: Path, target_url: str, dry_run: bool = True) -> None:
    """Restore database tables from a verified backup archive."""
    import psycopg

    data = verify_archive(archive_path)
    tables = data.get("tables", {})

    if dry_run:
        print("\n[i] DRY-RUN MODE: The backup archive is valid. No data was written to the target.")
        print("    To perform live restore, pass '--no-dry-run'.")
        return

    print(f"\n[*] Restoring data into target database: {target_url}...")
    with psycopg.connect(target_url) as conn:
        with conn.cursor() as cur:
            # Disable FK constraints or restore in dependency order
            for tbl in TABLE_ORDER:
                rows = tables.get(tbl, [])
                if not rows:
                    continue
                cols = list(rows[0].keys())
                col_names = ", ".join(cols)
                placeholders = ", ".join(["%s"] * len(cols))
                query = f"INSERT INTO {tbl} ({col_names}) VALUES ({placeholders}) ON CONFLICT DO NOTHING;"
                val_tuples = [[row[c] for c in cols] for row in rows]
                cur.executemany(query, val_tuples)
                print(f"    [OK] Restored {len(val_tuples)} rows into '{tbl}'.")
        conn.commit()

    print("[OK] Database restore successfully completed!")


def main() -> int:
    parser = argparse.ArgumentParser(description="SafeSense AI PostgreSQL Backup & Restore Tool")
    parser.add_argument("--backup", action="store_true", help="Perform logical backup of PostgreSQL tables")
    parser.add_argument("--verify-archive", type=Path, help="Verify archive integrity and print table counts")
    parser.add_argument("--restore", type=Path, help="Restore from specified backup archive")
    parser.add_argument("--target-url", type=str, help="Target PostgreSQL connection string (defaults to DATABASE_URL)")
    parser.add_argument("--output-dir", type=Path, default=Path("backups"), help="Directory to save backup archives")
    parser.add_argument("--no-dry-run", action="store_true", help="Execute live restore (modifies database)")

    args = parser.parse_args()

    db_url = args.target_url or os.getenv("DATABASE_URL")
    if not db_url and (args.backup or (args.restore and args.no_dry_run)):
        print("Error: DATABASE_URL environment variable or --target-url must be set.", file=sys.stderr)
        return 1

    # Normalize url from postgresql+psycopg:// to postgresql://
    if db_url and db_url.startswith("postgresql+psycopg://"):
        db_url = db_url.replace("postgresql+psycopg://", "postgresql://", 1)

    try:
        if args.backup:
            create_backup(db_url, args.output_dir)
        elif args.verify_archive:
            verify_archive(args.verify_archive)
        elif args.restore:
            restore_backup(args.restore, db_url, dry_run=not args.no_dry_run)
        else:
            parser.print_help()
            return 1
        return 0
    except Exception as exc:
        print(f"Execution failed: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
